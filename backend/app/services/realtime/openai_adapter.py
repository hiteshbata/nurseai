"""
OpenAI Realtime API adapter.

Wire protocol is unchanged from the pre-refactor speaking_realtime.py --
this is a straight extraction of that proven, already-in-production protocol
handling behind the ProviderAdapter interface, not a rewrite of it. OpenAI
has since published a GA event schema (response.output_audio.delta instead
of response.audio.delta, session.audio.output.* instead of top-level
voice/input_audio_format, etc.) but this adapter deliberately keeps the
older `OpenAI-Beta: realtime=v1` event names, since that's what's been
verified working in this project. Migrating to the GA schema is a
follow-up, tracked separately -- see the rollout notes in the deliverables
doc, not bundled into this refactor so a protocol mismatch can't be
conflated with an architecture regression.
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
                    "OpenAI-Beta": "realtime=v1",
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
                "modalities": ["audio", "text"],
                "instructions": self.system_prompt,
                "voice": self.voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
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

                if event_type == "response.audio.delta":
                    audio_b64 = event.get("delta")
                    if audio_b64:
                        yield base64.b64decode(audio_b64)

                elif event_type == "response.audio_transcript.delta":
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
                    logger.error("[OPENAI_REALTIME_ERROR] %s", _redact(json.dumps(event)[:500]))
                    yield ProviderError(
                        message=event.get("error", {}).get("message", "Realtime error"),
                        code=event.get("error", {}).get("code"),
                        recoverable=True,
                    )
        except ws_exc.ConnectionClosed as e:
            logger.warning("OpenAI realtime connection closed: code=%s reason=%s", e.code, e.reason)
            yield ProviderError(message="OpenAI realtime connection closed", code=str(e.code), recoverable=False)
        except Exception as e:
            logger.error("OpenAI realtime receive_events error: type=%s detail=%s", type(e).__name__, str(e)[:500])
            yield ProviderError(message="Realtime connection error", recoverable=False)
