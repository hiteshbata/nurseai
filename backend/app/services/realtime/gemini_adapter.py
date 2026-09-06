"""
Gemini Live API adapter (BidiGenerateContent over WebSocket).

Protocol shapes below were verified against Google's official Live API
WebSocket reference (ai.google.dev/api/live) at implementation time:
  - top-level client envelope is exactly one of
    {"setup": ...} | {"clientContent": ...} | {"realtimeInput": ...} | {"toolResponse": ...}
  - top-level server envelope: {"setupComplete": ...} | {"serverContent": ...} | {"goAway": ...} | ...
  - all field names are camelCase (proto-JSON mapping), not snake_case.

Two things are explicitly flagged as unverified in
capabilities.GEMINI_LIVE_CAPABILITIES.unverified and should be re-checked
against a live session before this adapter is trusted in production:
  1. Whether inputTranscription/outputTranscription text arrives as
     incremental fragments or a repeated cumulative string. This adapter
     assumes incremental fragments (concatenates them) for output, and
     buffers nurse input fragments until turnComplete -- if that assumption
     is wrong, nurse/patient transcripts will look duplicated or garbled and
     the concatenation logic below needs to switch to "replace" instead of
     "append".
  2. The full prebuilt voice name catalog (GEMINI_VOICE_BY_GENDER below
     only uses two names confirmed common across Gemini Live docs/samples).
"""
from __future__ import annotations

import base64
import json
import logging
from typing import AsyncIterator

import websockets as ws_lib
import websockets.exceptions as ws_exc

from app.services.realtime.base import ProviderConnectError, RealtimeProviderAdapter
from app.services.realtime.capabilities import GEMINI_LIVE_CAPABILITIES
from app.services.realtime.events import (
    Interrupted,
    ProviderError,
    RealtimeEvent,
    ResponseDone,
    SessionReady,
    TranscriptDelta,
    TranscriptFinal,
)

logger = logging.getLogger(__name__)

# websockets logs the full connect URI (incl. ?key=...) at DEBUG; keep that
# logger above DEBUG so the API key never lands in logs regardless of root
# log level.
logging.getLogger("websockets.client").setLevel(logging.INFO)

GEMINI_LIVE_WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)

# See module docstring item 2 -- confirm the full catalog in Google AI
# Studio before adding more names or relying on gender-accurate mapping.
GEMINI_VOICE_BY_GENDER = {
    "male": "Puck",
    "female": "Kore",
}
GEMINI_DEFAULT_VOICE = "Aoede"


def _redact(text: str) -> str:
    import re
    return re.sub(r'(?i)(key|api[_-]?key|token|secret)(["\s:=]+)([A-Za-z0-9_-]{20,})', r'\1\2***REDACTED***', text)


def map_gender_to_gemini_voice(gender: str | None) -> str:
    return GEMINI_VOICE_BY_GENDER.get(gender or "", GEMINI_DEFAULT_VOICE)


class GeminiLiveAdapter(RealtimeProviderAdapter):
    capabilities = GEMINI_LIVE_CAPABILITIES

    def __init__(self, *, system_prompt: str, voice: str, api_key: str, model: str) -> None:
        super().__init__(system_prompt=system_prompt, voice=voice, api_key=api_key)
        self.model = model
        self._ws: ws_lib.WebSocketClientProtocol | None = None
        self._nurse_transcript_buffer = ""

    async def connect(self) -> None:
        # Never log this URL raw -- it carries api_key in the query string.
        url = f"{GEMINI_LIVE_WS_URL}?key={self.api_key}"
        try:
            self._ws = await ws_lib.connect(
                url,
                close_timeout=1,
                open_timeout=30,
                max_size=None,
            )
        except Exception as e:
            raise ProviderConnectError(f"{type(e).__name__}: {_redact(str(e)[:500])}") from e

        await self._ws.send(json.dumps({
            "setup": {
                "model": self.model,
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": self.voice},
                        },
                    },
                },
                "systemInstruction": {
                    "parts": [{"text": self.system_prompt}],
                },
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
                "realtimeInputConfig": {
                    "automaticActivityDetection": {"disabled": False},
                },
            },
        }))

    async def disconnect(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def send_audio(self, pcm16_bytes: bytes) -> None:
        if self._ws is None:
            return
        await self._ws.send(json.dumps({
            "realtimeInput": {
                "audio": {
                    "data": base64.b64encode(pcm16_bytes).decode("ascii"),
                    "mimeType": f"audio/pcm;rate={self.capabilities.input_sample_rate}",
                },
            },
        }))

    async def cancel_response(self) -> None:
        # No-op by design: Gemini's automatic VAD auto-cancels the in-flight
        # model turn server-side as soon as it detects the nurse speaking
        # over it -- by the time Interrupted is raised (serverContent.
        # interrupted == true), generation has already stopped. There is no
        # documented client->server "cancel" message for BidiGenerateContent
        # the way OpenAI has response.cancel. See capabilities.
        # explicit_cancel_required=False.
        return

    async def update_instructions(self, instructions: str) -> None:
        # ponytail: BidiGenerateContent's client envelope has no message
        # that replaces systemInstruction after setup (see module docstring
        # and capabilities.GEMINI_LIVE_CAPABILITIES.supports_live_instruction_update)
        # -- honoring this would require reconnecting, which the interface
        # contract explicitly forbids. Documented no-op so the router can
        # call it unconditionally on every provider. Upgrade path: if
        # Google ships a live systemInstruction-update message for Live API,
        # wire it here and flip the capability flag.
        return

    async def receive_events(self) -> AsyncIterator[RealtimeEvent | bytes]:
        if self._ws is None:
            return
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    continue
                event = json.loads(message)

                if "setupComplete" in event:
                    yield SessionReady(provider="gemini")
                    continue

                if "goAway" in event:
                    # Server-initiated notice that the connection will be
                    # force-closed shortly (session/quota time limit). There
                    # is no client-side extension for this on the free
                    # BidiGenerateContent protocol -- treat as unrecoverable
                    # so the router's fallback/reconnect logic engages
                    # before the provider closes the socket out from under it.
                    logger.warning("[GEMINI_LIVE_GOAWAY] %s", json.dumps(event)[:300])
                    yield ProviderError(message="Gemini Live session ending (goAway)", code="GO_AWAY", recoverable=False)
                    continue

                if "error" in event:
                    logger.error("[GEMINI_LIVE_ERROR] %s", _redact(json.dumps(event)[:500]))
                    yield ProviderError(message=str(event.get("error"))[:300], recoverable=True)
                    continue

                server_content = event.get("serverContent")
                if not server_content:
                    continue

                if server_content.get("interrupted"):
                    yield Interrupted()

                model_turn = server_content.get("modelTurn")
                if model_turn:
                    for part in model_turn.get("parts", []):
                        inline_data = part.get("inlineData")
                        if inline_data and inline_data.get("data"):
                            yield base64.b64decode(inline_data["data"])

                output_transcription = server_content.get("outputTranscription")
                if output_transcription and output_transcription.get("text"):
                    # TEMP: remove once the incremental-vs-cumulative
                    # question in capabilities.GEMINI_LIVE_CAPABILITIES.
                    # unverified is confirmed via a manual live session.
                    logger.debug("[GEMINI_LIVE_RAW_OUTPUT_TRANSCRIPT] %r", output_transcription["text"])
                    yield TranscriptDelta(role="patient", delta=output_transcription["text"])

                input_transcription = server_content.get("inputTranscription")
                if input_transcription and input_transcription.get("text"):
                    logger.debug("[GEMINI_LIVE_RAW_INPUT_TRANSCRIPT] %r", input_transcription["text"])
                    self._nurse_transcript_buffer += input_transcription["text"]

                if server_content.get("turnComplete"):
                    if self._nurse_transcript_buffer.strip():
                        yield TranscriptFinal(role="nurse", transcript=self._nurse_transcript_buffer.strip())
                        self._nurse_transcript_buffer = ""
                    yield ResponseDone()
        except ws_exc.ConnectionClosed as e:
            logger.warning("Gemini Live connection closed: code=%s reason=%s", e.code, e.reason)
            yield ProviderError(message="Gemini Live connection closed", code=str(e.code), recoverable=False)
        except Exception as e:
            logger.error("Gemini Live receive_events error: type=%s detail=%s", type(e).__name__, _redact(str(e)[:500]))
            yield ProviderError(message="Realtime connection error", recoverable=False)
