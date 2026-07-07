"""
Tests for app.services.realtime.gemini_adapter.GeminiLiveAdapter.

All websocket I/O is faked -- no real network or Gemini Live API calls, so
this suite runs with no external services or internet access. Same
plain-asyncio.run() style as test_realtime_openai_adapter.py (no
pytest-asyncio dependency in this project).
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

from app.services.realtime import gemini_adapter as ga
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
    kwargs = dict(system_prompt="You are a patient.", voice="Kore", api_key="test-key", model="models/gemini-2.0-flash-live-001")
    kwargs.update(overrides)
    return ga.GeminiLiveAdapter(**kwargs)


def _run(coro):
    return asyncio.run(coro)


async def _collect_events(adapter, n=None):
    events = []
    async for item in adapter.receive_events():
        events.append(item)
        if n is not None and len(events) >= n:
            break
    return events


# ── gender-to-voice mapping ───────────────────────────────────────────

def test_map_gender_to_gemini_voice_known_genders():
    assert ga.map_gender_to_gemini_voice("male") == "Puck"
    assert ga.map_gender_to_gemini_voice("female") == "Kore"


def test_map_gender_to_gemini_voice_falls_back_to_default():
    assert ga.map_gender_to_gemini_voice(None) == ga.GEMINI_DEFAULT_VOICE
    assert ga.map_gender_to_gemini_voice("nonbinary") == ga.GEMINI_DEFAULT_VOICE


# ── connect() ─────────────────────────────────────────────────────────

def test_connect_success_sends_setup_message(monkeypatch):
    fake_ws = FakeWS()

    async def fake_connect(url, **kwargs):
        assert "key=test-key" in url
        return fake_ws

    monkeypatch.setattr(ga.ws_lib, "connect", fake_connect)
    adapter = _adapter()

    _run(adapter.connect())

    assert adapter._ws is fake_ws
    sent = json.loads(fake_ws.sent[0])
    setup = sent["setup"]
    assert setup["model"] == "models/gemini-2.0-flash-live-001"
    assert setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert setup["systemInstruction"]["parts"][0]["text"] == "You are a patient."


def test_connect_failure_raises_provider_connect_error(monkeypatch):
    async def fake_connect(url, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(ga.ws_lib, "connect", fake_connect)

    with pytest.raises(ProviderConnectError):
        _run(_adapter().connect())


# ── send_audio / cancel_response / disconnect ────────────────────────

def test_send_audio_encodes_base64_with_correct_mime_rate():
    fake_ws = FakeWS()
    adapter = _adapter()
    adapter._ws = fake_ws

    _run(adapter.send_audio(b"\x01\x02\x03"))

    sent = json.loads(fake_ws.sent[0])
    audio = sent["realtimeInput"]["audio"]
    assert base64.b64decode(audio["data"]) == b"\x01\x02\x03"
    assert audio["mimeType"] == "audio/pcm;rate=16000"


def test_send_audio_is_noop_before_connect():
    _run(_adapter().send_audio(b"\x01"))  # must not raise


def test_cancel_response_is_always_a_noop():
    # Gemini has no client->server cancel message -- its server-side VAD
    # already stops generation before Interrupted is raised. Must be safe
    # to call regardless of connection state.
    _run(_adapter().cancel_response())  # never connected

    fake_ws = FakeWS()
    adapter = _adapter()
    adapter._ws = fake_ws
    _run(adapter.cancel_response())
    assert fake_ws.sent == []


def test_disconnect_is_idempotent_and_safe_when_never_connected():
    adapter = _adapter()
    _run(adapter.disconnect())

    fake_ws = FakeWS()
    adapter._ws = fake_ws
    _run(adapter.disconnect())
    assert fake_ws.closed
    assert adapter._ws is None

    _run(adapter.disconnect())


# ── receive_events() translation ──────────────────────────────────────

def test_receive_events_empty_when_never_connected():
    assert _run(_collect_events(_adapter())) == []


def test_receive_events_setup_complete_yields_session_ready():
    messages = [json.dumps({"setupComplete": {}})]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter))

    assert events == [SessionReady(provider="gemini")]


def test_receive_events_go_away_is_unrecoverable():
    messages = [json.dumps({"goAway": {"timeLeft": "10s"}})]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter))

    err = events[0]
    assert isinstance(err, ProviderError)
    assert err.recoverable is False
    assert err.code == "GO_AWAY"


def test_receive_events_error_is_recoverable():
    messages = [json.dumps({"error": {"message": "quota exceeded"}})]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter))

    err = events[0]
    assert isinstance(err, ProviderError)
    assert err.recoverable is True


def test_receive_events_interrupted_and_audio_and_output_transcript():
    messages = [json.dumps({
        "serverContent": {
            "interrupted": True,
            "modelTurn": {"parts": [{"inlineData": {"data": base64.b64encode(b"\x11\x22").decode()}}]},
            "outputTranscription": {"text": "Hello"},
        },
    })]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter))

    assert Interrupted() in events
    assert b"\x11\x22" in events
    assert TranscriptDelta(role="patient", delta="Hello") in events


def test_receive_events_nurse_transcript_buffers_until_turn_complete():
    messages = [
        json.dumps({"serverContent": {"inputTranscription": {"text": "I have "}}}),
        json.dumps({"serverContent": {"inputTranscription": {"text": "a fever"}}}),
        json.dumps({"serverContent": {"turnComplete": True}}),
    ]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter))

    assert TranscriptFinal(role="nurse", transcript="I have a fever") in events
    assert ResponseDone() in events
    assert adapter._nurse_transcript_buffer == ""  # reset after flushing


def test_receive_events_turn_complete_with_blank_buffer_skips_transcript_final():
    messages = [json.dumps({"serverContent": {"turnComplete": True}})]
    adapter = _adapter()
    adapter._ws = FakeWS(messages=messages)

    events = _run(_collect_events(adapter))

    assert not any(isinstance(e, TranscriptFinal) for e in events)
    assert ResponseDone() in events


def test_receive_events_connection_closed_is_unrecoverable():
    close_exc = ws_exc.ConnectionClosed(ws_frames.Close(1006, "abnormal"), None)
    adapter = _adapter()
    adapter._ws = FakeWS(raise_at_end=close_exc)

    events = _run(_collect_events(adapter))

    err = events[0]
    assert isinstance(err, ProviderError)
    assert err.recoverable is False
