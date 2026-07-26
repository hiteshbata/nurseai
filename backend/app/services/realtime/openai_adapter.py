"""
OpenAI Realtime API adapter.

Speaks the GA wire protocol (OpenAI removed the Beta interface --
`OpenAI-Beta: realtime=v1` header -- on 2026-05-12; connecting with it now
hard-fails with "The Realtime Beta API is no longer supported"). Audio/turn
config lives under session.audio.input/output instead of top-level
voice/input_audio_format, audio format is an object ({"type":"audio/pcm",
"rate":24000}) instead of the bare string "pcm16", and the output audio
events are namespaced response.output_audio(_transcript).delta instead of
response.audio(_transcript).delta. Input-side events (input_audio_buffer.*,
conversation.item.input_audio_transcription.completed) and session lifecycle
events (response.created/done, error) are unchanged from Beta.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import AsyncIterator

import websockets as ws_lib
import websockets.exceptions as ws_exc

from app.services.realtime.base import ProviderConnectError, RealtimeProviderAdapter
from app.services.realtime.capabilities import OPENAI_REALTIME_CAPABILITIES
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

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"


def _redact(text: str) -> str:
    import re
    return re.sub(r'(?i)(key|api[_-]?key|token|secret)(["\s:=]+)([A-Za-z0-9_-]{20,})', r'\1\2***REDACTED***', text)


class OpenAIRealtimeAdapter(RealtimeProviderAdapter):
    capabilities = OPENAI_REALTIME_CAPABILITIES

    def __init__(self, *, system_prompt: str, voice: str, api_key: str, model: str) -> None:
        super().__init__(system_prompt=system_prompt, voice=voice, api_key=api_key)
        self.model = model
        self._ws: ws_lib.WebSocketClientProtocol | None = None
        self._response_in_progress = False

    async def connect(self) -> None:
        url = f"{OPENAI_REALTIME_URL}?model={self.model}"
        try:
            self._ws = await ws_lib.connect(
                url,
                extra_headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
                close_timeout=1,
                open_timeout=30,
                max_size=None,
            )
        except Exception as e:
            raise ProviderConnectError(f"{type(e).__name__}: {_redact(str(e)[:500])}") from e

        await self._ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": self.system_prompt,
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500,
                        },
                        "transcription": {"model": "whisper-1"},
                    },
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": self.voice,
                    },
                },
                "output_modalities": ["audio"],
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
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm16_bytes).decode("ascii"),
        }))

    async def cancel_response(self) -> None:
        if self._ws is None or not self._response_in_progress:
            return
        try:
            await self._ws.send(json.dumps({"type": "response.cancel"}))
        except ws_exc.ConnectionClosed:
            pass

    async def receive_events(self) -> AsyncIterator[RealtimeEvent | bytes]:
        if self._ws is None:
            return
        yield SessionReady(provider="openai")
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    continue
                event = json.loads(message)
                event_type = event.get("type")

                if event_type == "response.output_audio.delta":
                    audio_b64 = event.get("delta")
                    if audio_b64:
                        yield base64.b64decode(audio_b64)

                elif event_type == "response.output_audio_transcript.delta":
                    yield TranscriptDelta(role="patient", delta=event.get("delta", ""))

                elif event_type == "conversation.item.input_audio_transcription.completed":
                    yield TranscriptFinal(role="nurse", transcript=event.get("transcript", ""))

                elif event_type == "response.created":
                    self._response_in_progress = True

                elif event_type == "response.done":
                    self._response_in_progress = False
                    yield ResponseDone()

                elif event_type == "input_audio_buffer.speech_started":
                    yield Interrupted()

                elif event_type == "error":
                    error_detail = event.get("error", {})
                    if error_detail.get("code") == "response_cancel_not_active":
                        # Benign race, not a real failure: cancel_response() fires on every
                        # barge-in, but GA's server_vad routinely auto-cancels/finishes the
                        # response before our explicit response.cancel arrives. The interrupt
                        # already succeeded either way -- surfacing this as ProviderError was
                        # tearing down the whole session (frontend treats any error as fatal).
                        continue
                    logger.error("[OPENAI_REALTIME_ERROR] %s", _redact(json.dumps(event)[:500]))
                    yield ProviderError(
                        message=error_detail.get("message", "Realtime error"),
                        code=error_detail.get("code"),
                        recoverable=True,
                    )
        except ws_exc.ConnectionClosed as e:
            logger.warning("OpenAI realtime connection closed: code=%s reason=%s", e.code, e.reason)
            yield ProviderError(message="OpenAI realtime connection closed", code=str(e.code), recoverable=False)
        except Exception as e:
            logger.error("OpenAI realtime receive_events error: type=%s detail=%s", type(e).__name__, str(e)[:500])
            yield ProviderError(message="Realtime connection error", recoverable=False)
