"""
Tests for app.services.realtime.openai_adapter.OpenAIRealtimeAdapter.

All websocket I/O is faked (FakeWS below) -- no real network or OpenAI API
calls, so this suite runs with no external services or internet access.
pytest-asyncio isn't a project dependency, so async code paths are driven
with a plain asyncio.run() per test, matching this repo's existing
plain-pytest style (see tests/test_coach.py).
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import websockets.exceptions as ws_exc
import websockets.frames as ws_frames

from app.services.realtime import openai_adapter as oa
from app.services.realtime.base import ProviderConnectError
from app.services.realtime.events import (
    Interrupted,
    ProviderError,
    ResponseDone,
    SessionReady,
    TranscriptDelta,
    TranscriptFinal,
)


class FakeWS:
    """Stands in for websockets' WebSocketClientProtocol: async .send()/.close()
    plus async iteration over a preset list of text frames."""

    def __init__(self, messages=None, raise_at_end=None):
        self._messages = list(messages or [])
        self._raise_at_end = raise_at_end
        self.sent = []
        self.closed = False

    async def send(self, message):
        self.sent.append(message)

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._messages:
            return self._messages.pop(0)
        if self._raise_at_end is not None:
            exc, self._raise_at_end = self._raise_at_end, None
            raise exc
        raise StopAsyncIteration


def _adapter(**overrides):
    kwargs = dict(system_prompt="You are a patient.", voice="alloy", api_key="sk-test", model="gpt-realtime")
    kwargs.update(overrides)
    return oa.OpenAIRealtimeAdapter(**kwargs)


def _run(coro):
    return asyncio.run(coro)


async def _collect_events(adapter, n=None):
    events = []
    async for item in adapter.receive_events():
        events.append(item)
        if n is not None and len(events) >= n:
            break
    return events


# ── connect() ─────────────────────────────────────────────────────────

def test_connect_success_sends_session_update(monkeypatch):
    fake_ws = FakeWS()

    async def fake_connect(url, **kwargs):
        assert kwargs["extra_headers"]["Authorization"] == "Bearer sk-test"
        assert "model=gpt-realtime" in url
        return fake_ws

    monkeypatch.setattr(oa.ws_lib, "connect", fake_connect)
    adapter = _adapter()

    _run(adapter.connect())

    assert adapter._ws is fake_ws
    sent = json.loads(fake_ws.sent[0])
    assert sent["type"] == "session.update"
    assert sent["session"]["type"] == "realtime"
    assert sent["session"]["instructions"] == "You are a patient."
    assert sent["session"]["audio"]["output"]["voice"] == "alloy"
    assert sent["session"]["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert sent["session"]["audio"]["output"]["format"] == {"type": "audio/pcm", "rate": 24000}


def test_connect_failure_raises_provider_connect_error(monkeypatch):
    async def fake_connect(url, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(oa.ws_lib, "connect", fake_connect)

    with pytest.raises(ProviderConnectError):
        _run(_adapter().connect())


def test_connect_failure_redacts_api_key(monkeypatch):
    secret = "sk-verysecretlongvalue1234567890abcdef"

    async def fake_connect(url, **kwargs):
        raise OSError(f"handshake failed, token={secret}")

    monkeypatch.setattr(oa.ws_lib, "connect", fake_connect)

    with pytest.raises(ProviderConnectError) as exc_info:
        _run(_adapter().connect())
    assert secret not in str(exc_info.value)
    assert "REDACTED" in str(exc_info.value)


# ── send_audio / cancel_response / disconnect ────────────────────────

def test_send_audio_encodes_base64():
    fake_ws = FakeWS()
    adapter = _adapter()
    adapter._ws = fake_ws

    _run(adapter.send_audio(b"\x01\x02\x03"))

    sent = json.loads(fake_ws.sent[0])
    assert sent["type"] == "input_audio_buffer.append"
    assert base64.b64decode(sent["audio"]) == b"\x01\x02\x03"


def test_send_audio_is_noop_before_connect():
    _run(_adapter().send_audio(b"\x01"))  # must not raise


def test_cancel_response_noop_when_nothing_in_progress():
    fake_ws = FakeWS()
    adapter = _adapter()
    adapter._ws = fake_ws
    adapter._response_in_progress = False

    _run(adapter.cancel_response())

    assert fake_ws.sent == []


def test_cancel_response_sends_when_in_progress():
    fake_ws = FakeWS()
    adapter = _adapter()
    adapter._ws = fake_ws
    adapter._response_in_progress = True

    _run(adapter.cancel_response())

    assert json.loads(fake_ws.sent[0]) == {"type": "response.cancel"}


def test_disconnect_is_idempotent_and_safe_when_never_connected():
    adapter = _adapter()
    _run(adapter.disconnect())  # never connected -- must not raise

    fake_ws = FakeWS()
    adapter._ws = fake_ws
    _run(adapter.disconnect())
    assert fake_ws.closed
    assert adapter._ws is None

    _run(adapter.disconnect())  # already disconnected -- must not raise


# ── receive_events() translation ──────────────────────────────────────

def test_receive_events_empty_when_never_connected():
    assert _run(_collect_events(_adapter())) == []


def test_receive_events_audio_delta_and_transcript_delta():
    messages = [
        json.dumps({"type": "response.output_audio.delta", "delta": base64.b64encode(b"\x09\x08").decode()}),
        json.dumps({"type": "response.output_audio_transcript.delta", "delta": "Hel"}),
    ]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter, n=3))

    assert events[0] == SessionReady(provider="openai")
    assert events[1] == b"\x09\x08"
    assert events[2] == TranscriptDelta(role="patient", delta="Hel")


def test_receive_events_nurse_transcript_final():
    messages = [json.dumps({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "I have a headache",
    })]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter, n=2))

    assert events[1] == TranscriptFinal(role="nurse", transcript="I have a headache")


def test_receive_events_response_lifecycle_and_interrupt():
    messages = [
        json.dumps({"type": "response.created"}),
        json.dumps({"type": "input_audio_buffer.speech_started"}),
        json.dumps({"type": "response.done"}),
    ]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter))

    assert adapter._response_in_progress is False
    assert Interrupted() in events
    assert ResponseDone() in events


def test_receive_events_recoverable_error():
    messages = [json.dumps({"type": "error", "error": {"message": "bad request", "code": "invalid"}})]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter, n=2))

    err = events[1]
    assert isinstance(err, ProviderError)
    assert err.recoverable is True
    assert err.message == "bad request"
    assert err.code == "invalid"


def test_receive_events_swallows_benign_cancel_race():
    messages = [
        json.dumps({"type": "error", "error": {"message": "Cancellation failed: no active response found", "code": "response_cancel_not_active"}}),
        json.dumps({"type": "response.done"}),
    ]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter))

    assert not any(isinstance(e, ProviderError) for e in events)
    assert ResponseDone() in events


def test_receive_events_connection_closed_is_unrecoverable():
    close_exc = ws_exc.ConnectionClosed(ws_frames.Close(1006, "abnormal"), None)
    adapter = _adapter()
    adapter._ws = FakeWS(raise_at_end=close_exc)

    events = _run(_collect_events(adapter, n=2))

    err = events[1]
    assert isinstance(err, ProviderError)
    assert err.recoverable is False
