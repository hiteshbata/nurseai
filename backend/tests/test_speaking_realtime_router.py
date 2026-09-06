"""
Tests for the /speaking/realtime/stream websocket gateway
(app.routers.speaking_realtime.realtime_stream).

realtime_stream() is a plain async function -- it isn't wired through
FastAPI's dependency injection (auth/quota/Supabase are called directly at
module scope), so it can be invoked directly with a fake WebSocket and
monkeypatched module-level collaborators without spinning up an ASGI
server or TestClient. Everything that would normally hit Supabase, Supabase
Auth, or a provider's websocket is faked; no external services or internet
access are used. No pytest-asyncio dependency -- driven via asyncio.run(),
matching this repo's existing plain-pytest style.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException, WebSocketDisconnect

import app.routers.speaking_realtime as srt
import app.services.cost_tracking as cost_tracking
from app.services.realtime.base import ProviderConnectError
from app.services.realtime.events import Interrupted, ProviderError, ResponseDone, TranscriptDelta, TranscriptFinal

_DISCONNECT = object()

DEFAULT_SCENARIO = {
    "id": 42,
    "is_active": True,
    "patient_gender": "female",
    "interlocutor_card": {
        "patient_name": "Mary",
        "age": 68,
        "condition": "chest pain",
        "mood": "anxious",
        "background": "",
        "instructions_for_ai": "Be anxious and guarded.",
        "emotional_triggers": [],
        "questions_to_ask": [],
        "information_to_withhold": [],
    },
}


# ── Fakes ───────────────────────────────────────────────────────────────

class FakeUser:
    def __init__(self, id="user-1", email="nurse@example.com"):
        self.id = id
        self.email = email


class _FakeAuth:
    def __init__(self, user, raises):
        self._user = user
        self._raises = raises

    def get_user(self, token):
        if self._raises:
            raise Exception("invalid token")
        return type("AuthResult", (), {"user": self._user})()


class FakeAuthClient:
    def __init__(self, user=None, raises=False):
        self.auth = _FakeAuth(user, raises)


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, table_name, state):
        self.table_name = table_name
        self.state = state
        self._op = None
        self._payload = None

    def select(self, *_a, **_k):
        self._op = self._op or "select"
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def update(self, row):
        self._op = "update"
        self._payload = row
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        if self.table_name == "scenarios" and self._op == "select":
            return FakeResult(self.state["scenario_rows"])
        if self.table_name == "realtime_session_metrics" and self._op == "insert":
            self.state["metrics_rows"].append(self._payload)
            return FakeResult([self._payload])
        if self.table_name == "session_usage" and self._op == "select":
            return FakeResult([dict(self.state["session_usage_row"])])
        if self.table_name == "session_usage" and self._op == "update":
            self.state["session_usage_row"].update(self._payload)
            self.state["session_usage_updates"].append(self._payload)
            return FakeResult([self._payload])
        if self.table_name == "session_transcripts" and self._op == "select":
            return FakeResult(self.state["prior_transcript_rows"])
        return FakeResult([])


_RPC_ARG_TO_COLUMN = {
    "p_realtime_delta": "realtime_cost_usd",
    "p_azure_delta": "azure_cost_usd",
    "p_scoring_delta": "scoring_cost_usd",
    "p_tts_delta": "tts_cost_usd",
}


class FakeRpc:
    def __init__(self, fn_name, params, state):
        self.fn_name = fn_name
        self.params = params
        self.state = state

    def execute(self):
        if self.fn_name == "increment_session_cost":
            # Mirrors 20260802020000_atomic_session_cost_increment.sql: sum
            # each delta onto session_usage and record the resulting update,
            # same shape as the old direct .update() call this replaced.
            update = {
                col: self.state["session_usage_row"].get(col, 0) + self.params.get(arg, 0)
                for arg, col in _RPC_ARG_TO_COLUMN.items()
            }
            provider = self.params.get("p_provider")
            if provider is not None:
                update["provider"] = provider
            self.state["session_usage_row"].update(update)
            self.state["session_usage_updates"].append(update)
            return FakeResult([update])
        return FakeResult([])


class FakeSupabase:
    def __init__(self, state):
        self.state = state

    def table(self, name):
        return FakeQuery(name, self.state)

    def rpc(self, fn_name, params):
        return FakeRpc(fn_name, params, self.state)


class FakeWebSocket:
    def __init__(self, handshake, audio_chunks=None):
        self._handshake = handshake
        self._audio_queue = asyncio.Queue()
        for chunk in (audio_chunks or []):
            self._audio_queue.put_nowait(chunk)
        self.sent_json = []
        self.sent_bytes = []
        self.closed = None

    async def accept(self):
        pass

    async def receive_json(self):
        return self._handshake

    async def receive_bytes(self):
        item = await self._audio_queue.get()
        if item is _DISCONNECT:
            raise WebSocketDisconnect()
        return item

    async def send_json(self, payload):
        self.sent_json.append(payload)

    async def send_bytes(self, data):
        self.sent_bytes.append(data)

    async def close(self, code=None, reason=None):
        self.closed = (code, reason)


class FakeAdapter:
    """Configured via class attributes right before each realtime_stream()
    call (see _run_stream) since the router constructs the instance
    itself from `get_adapter_class(provider)`."""

    connect_raises = None
    preset_events = ()
    hang_until_disconnect = False
    instances = []

    def __init__(self, *, system_prompt, voice, api_key, model):
        self.system_prompt = system_prompt
        self.voice = voice
        self.api_key = api_key
        self.model = model
        self.sent_audio = []
        self.disconnect_count = 0
        self.cancel_count = 0
        self.instructions_updates = []
        self._stop_event = asyncio.Event()
        self._connect_raises = FakeAdapter.connect_raises
        self._events = list(FakeAdapter.preset_events)
        self._hang = FakeAdapter.hang_until_disconnect
        FakeAdapter.instances.append(self)

    async def connect(self):
        if self._connect_raises:
            raise self._connect_raises

    async def disconnect(self):
        self.disconnect_count += 1
        self._stop_event.set()

    async def send_audio(self, data):
        self.sent_audio.append(data)

    async def cancel_response(self):
        self.cancel_count += 1

    async def update_instructions(self, instructions):
        self.instructions_updates.append(instructions)

    async def receive_events(self):
        if self._hang:
            await self._stop_event.wait()
            return
        for item in self._events:
            yield item


# ── harness ───────────────────────────────────────────────────────────

def _run_stream(
    monkeypatch,
    ws,
    *,
    scenario_rows=None,
    session_id_from_quota=999,
    validate_ok=True,
    auth_user=None,
    auth_raises=False,
    quota_raises=None,
    adapter_connect_raises=None,
    adapter_events=(),
    adapter_hang=False,
    voice_provider="openai",
    openai_key="test-openai-key",
    gemini_key="test-gemini-key",
    warning_seconds=5,
    max_seconds=8,
    prior_transcript_rows=None,
):
    state = {
        "scenario_rows": scenario_rows if scenario_rows is not None else [DEFAULT_SCENARIO],
        "metrics_rows": [],
        "session_usage_row": {"realtime_cost_usd": 0, "azure_cost_usd": 0, "scoring_cost_usd": 0, "tts_cost_usd": 0},
        "session_usage_updates": [],
        "prior_transcript_rows": prior_transcript_rows or [],
    }
    fake_supabase = FakeSupabase(state)
    monkeypatch.setattr(srt, "get_supabase", lambda: fake_supabase)
    monkeypatch.setattr(cost_tracking, "get_supabase", lambda: fake_supabase)
    # _get_voice_provider's 60s TTL cache is a module-level global -- without
    # resetting it, whichever provider an earlier test in this file cached
    # wins for every test that runs within that window, regardless of what
    # this test monkeypatches settings.VOICE_PROVIDER to. Pre-existing
    # flakiness, unrelated to what this test run is actually exercising.
    monkeypatch.setattr(srt, "_voice_provider_cache", None)

    fake_auth_client = FakeAuthClient(user=auth_user, raises=auth_raises)
    monkeypatch.setattr(srt, "get_auth_client", lambda: fake_auth_client)

    def fake_check_and_increment_session(current_user, user_db):
        if quota_raises:
            raise quota_raises
        return {"session_id": session_id_from_quota}

    monkeypatch.setattr(srt, "check_and_increment_session", fake_check_and_increment_session)
    monkeypatch.setattr(srt, "get_user_scoped_client", lambda token: fake_supabase)
    monkeypatch.setattr(srt, "validate_session", lambda user_id, session_id: validate_ok)
    # In-process SlidingWindowRateLimiter is a module-level singleton keyed by
    # user_id (see app.core.rate_limit) -- every test here uses the same
    # default user_id, so without this the 6th+ test in the file trips the
    # real 5-calls/60s limit and gets rate_limited instead of exercising its
    # actual code path.
    monkeypatch.setattr(srt._realtime_stream_rate_limiter, "is_rate_limited", lambda key: False)

    async def fake_run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(srt, "run_sync", fake_run_sync)

    FakeAdapter.connect_raises = adapter_connect_raises
    FakeAdapter.preset_events = tuple(adapter_events)
    FakeAdapter.hang_until_disconnect = adapter_hang
    FakeAdapter.instances = []
    monkeypatch.setattr(srt, "get_adapter_class", lambda provider: FakeAdapter)

    monkeypatch.setattr(srt.settings, "VOICE_PROVIDER", voice_provider)
    monkeypatch.setattr(srt.settings, "OPENAI_API_KEY", openai_key)
    monkeypatch.setattr(srt.settings, "GEMINI_API_KEY", gemini_key)
    monkeypatch.setattr(srt.settings, "REALTIME_SESSION_WARNING_SECONDS", warning_seconds)
    monkeypatch.setattr(srt.settings, "REALTIME_SESSION_MAX_SECONDS", max_seconds)

    # Step 7 (semantic evidence layer): these tests exercise the
    # instructions-push wiring around PatientState changes, not the
    # semantic classifiers' own correctness (see test_semantic_evidence.py
    # for that). Without a real speaking_semantic_evidence purpose
    # configured, hidden_info_hints would call the model, get
    # PurposeNotConfigured, and conservatively treat every candidate as
    # NOT revealed -- silently reproducing the pre-Step-7 "always confirm
    # the keyword match" behavior here keeps these tests focused on what
    # they actually test. Step 12B: "candidate" is computed via
    # _hidden_info_candidate directly (not derive_patient_state's
    # revealed_information, which no longer treats a candidate as revealed
    # on its own -- see patient_state.py). The two concern/resolution
    # classifiers are fire-and-forget background tasks (see
    # _maybe_fire_concern_semantic_checks) so a real no-op default is
    # enough -- no test here asserts on their effect.
    async def fake_hidden_info_hints(card, history, prior=None, **kwargs):
        from app.services.patient_state import SemanticHints, _hidden_info_candidate
        prior = prior or SemanticHints()
        patient_text = " ".join(t.get("content", "") for t in history if t.get("role") == "patient")
        newly_confirmed = {
            item for item in (card.get("information_to_withhold") or [])
            if _hidden_info_candidate(item, patient_text)
        }
        return SemanticHints(
            confirmed_hidden_reveals=frozenset(newly_confirmed) | prior.confirmed_hidden_reveals,
            rejected_hidden_reveals=prior.rejected_hidden_reveals,
            extra_nurse_events=prior.extra_nurse_events,
            resolved_concerns=prior.resolved_concerns,
        )

    monkeypatch.setattr(srt.semantic_evidence, "hidden_info_hints", fake_hidden_info_hints)

    async def fake_classify_nurse_concern_event(*args, **kwargs):
        return None

    async def fake_classify_patient_resolution(*args, **kwargs):
        return None

    monkeypatch.setattr(srt.semantic_evidence, "classify_nurse_concern_event", fake_classify_nurse_concern_event)
    monkeypatch.setattr(srt.semantic_evidence, "classify_patient_resolution", fake_classify_patient_resolution)

    asyncio.run(asyncio.wait_for(srt.realtime_stream(ws), timeout=5))
    return state


def _types(ws):
    return [m["type"] for m in ws.sent_json]


# ── auth / config / quota / scenario error paths ─────────────────────

def test_missing_token_is_unauthorized(monkeypatch):
    ws = FakeWebSocket(handshake={"scenario_id": 42})

    _run_stream(monkeypatch, ws)

    assert ws.sent_json[0]["type"] == "error"
    assert ws.closed == (4401, "Unauthorized")


def test_invalid_token_is_unauthorized(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "bad", "scenario_id": 42})

    _run_stream(monkeypatch, ws, auth_raises=True)

    assert ws.closed == (4401, "Unauthorized")


def test_missing_scenario_id_is_unauthorized(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "tok"})

    _run_stream(monkeypatch, ws, auth_user=FakeUser())

    assert ws.closed == (4401, "Unauthorized")


def test_warmup_mode_skips_quota_and_scenario(monkeypatch):
    """The onboarding voice check (mode: "warmup") must never touch the
    monthly session quota or require a scenario_id -- see is_warmup in
    speaking_realtime.py. This is the regression test for that branch."""
    ws = FakeWebSocket(
        handshake={"token": "tok", "mode": "warmup"},
        audio_chunks=[_DISCONNECT],
    )

    state = _run_stream(monkeypatch, ws, auth_user=FakeUser(), adapter_events=[ResponseDone()])

    ready = next(m for m in ws.sent_json if m["type"] == "session.ready")
    assert ready["session_id"] is None

    assert len(FakeAdapter.instances) == 1
    adapter = FakeAdapter.instances[0]
    assert "onboarding" in adapter.system_prompt.lower()
    assert adapter.voice == "alloy"

    # No session_usage row was ever created or charged for this session --
    # the quota path (check_and_increment_session) must never run for warmup.
    assert state["session_usage_updates"] == []


def test_misconfigured_provider(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42})

    _run_stream(monkeypatch, ws, auth_user=FakeUser(), voice_provider="azure")

    assert ws.sent_json[0]["error"] == "Voice provider misconfigured"
    assert ws.closed is not None


def test_missing_api_key_for_provider(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42})

    _run_stream(monkeypatch, ws, auth_user=FakeUser(), openai_key="")

    assert ws.sent_json[0]["error"] == "openai voice provider not configured"


def test_session_limit_reached(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42})

    _run_stream(
        monkeypatch, ws, auth_user=FakeUser(),
        quota_raises=HTTPException(status_code=429, detail="limit reached"),
    )

    assert ws.sent_json[-1]["error"] == "session_limit_reached"
    assert ws.closed == (4429, "session_limit_reached")


def test_scenario_not_found(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42, "session_id": 7})

    _run_stream(monkeypatch, ws, auth_user=FakeUser(), validate_ok=True, scenario_rows=[])

    assert ws.sent_json[-1]["error"] == "Scenario not found"
    assert ws.closed == (4404, "Scenario not found")


# ── provider connect failure -> fallback ─────────────────────────────

def test_provider_connect_failure_sends_fallback_and_closes(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42, "session_id": 7})

    _run_stream(
        monkeypatch, ws, auth_user=FakeUser(), validate_ok=True,
        adapter_connect_raises=ProviderConnectError("boom"),
    )

    assert ws.sent_json[0]["type"] == "session.ready"
    assert ws.sent_json[0]["session_id"] == 7
    err = ws.sent_json[-1]
    assert err["type"] == "error"
    assert err["error"] == "voice_provider_unavailable"
    assert err["fallback_available"] is True
    assert err["session_id"] == 7
    assert ws.closed == (4503, "provider_unavailable")


# ── successful sessions, per provider ─────────────────────────────────

def test_successful_openai_session_reports_openai_sample_rates(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42, "session_id": 7}, audio_chunks=[_DISCONNECT])

    _run_stream(monkeypatch, ws, auth_user=FakeUser(), voice_provider="openai")

    ready = ws.sent_json[0]
    assert ready["provider"] == "openai"
    assert ready["input_sample_rate"] == 24000
    assert ready["output_sample_rate"] == 24000


def test_successful_gemini_session_reports_gemini_sample_rates(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42, "session_id": 7}, audio_chunks=[_DISCONNECT])

    _run_stream(monkeypatch, ws, auth_user=FakeUser(), voice_provider="gemini")

    ready = ws.sent_json[0]
    assert ready["provider"] == "gemini"
    assert ready["input_sample_rate"] == 16000
    assert ready["output_sample_rate"] == 24000


# ── event forwarding: transcripts, response completion, interruption ─

def test_events_are_forwarded_and_interrupt_triggers_cancel(monkeypatch):
    events = [
        TranscriptDelta(role="patient", delta="Hel"),
        b"\x11\x22",
        Interrupted(),
        TranscriptFinal(role="nurse", transcript="I have chest pain"),
        ResponseDone(),
    ]
    ws = FakeWebSocket(
        handshake={"token": "tok", "scenario_id": 42, "session_id": 7},
        audio_chunks=[b"\x00\x01" * 10, _DISCONNECT],
    )

    state = _run_stream(monkeypatch, ws, auth_user=FakeUser(), adapter_events=events)

    assert {"type": "transcript.delta", "role": "patient", "delta": "Hel"} in ws.sent_json
    assert ws.sent_bytes == [b"\x11\x22"]
    assert {"type": "interrupted"} in ws.sent_json
    assert {"type": "transcript.final", "role": "nurse", "transcript": "I have chest pain"} in ws.sent_json
    assert {"type": "response.done"} in ws.sent_json

    adapter = FakeAdapter.instances[-1]
    assert adapter.cancel_count == 1
    assert adapter.sent_audio == [b"\x00\x01" * 10]

    assert len(state["metrics_rows"]) == 1
    assert state["metrics_rows"][0]["provider"] == "openai"
    assert state["metrics_rows"][0]["interrupted_count"] == 1
    assert state["metrics_rows"][0]["ended_reason"] == "client_closed"
    assert state["session_usage_updates"][-1]["provider"] == "openai"


def test_client_disconnect_ends_session_as_client_closed(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42, "session_id": 7}, audio_chunks=[_DISCONNECT])

    state = _run_stream(monkeypatch, ws, auth_user=FakeUser())

    assert state["metrics_rows"][0]["ended_reason"] == "client_closed"


# ── recoverable vs non-recoverable provider errors ───────────────────

def test_recoverable_error_is_forwarded_without_ending_session(monkeypatch):
    events = [ProviderError(message="hiccup", recoverable=True), ResponseDone()]
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42, "session_id": 7}, audio_chunks=[_DISCONNECT])

    _run_stream(monkeypatch, ws, auth_user=FakeUser(), adapter_events=events)

    error_messages = [m for m in ws.sent_json if m["type"] == "error"]
    assert len(error_messages) == 1
    assert "fallback_available" not in error_messages[0]
    assert {"type": "response.done"} in ws.sent_json


def test_nonrecoverable_error_triggers_fallback_and_ends_session(monkeypatch):
    events = [TranscriptDelta(role="patient", delta="hi"), ProviderError(message="dead", recoverable=False)]
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42, "session_id": 7})  # never disconnects itself

    state = _run_stream(monkeypatch, ws, auth_user=FakeUser(), adapter_events=events)

    error_messages = [m for m in ws.sent_json if m["type"] == "error"]
    fallback_error = error_messages[-1]
    assert fallback_error["fallback_available"] is True
    assert fallback_error["session_id"] == 7
    assert state["metrics_rows"][0]["ended_reason"] == "provider_error"
    assert state["metrics_rows"][0]["error_count"] == 1


# ── session timeout ────────────────────────────────────────────────────

def test_session_timeout_sends_warning_then_ends(monkeypatch):
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42, "session_id": 7})  # no client audio, ever

    state = _run_stream(
        monkeypatch, ws, auth_user=FakeUser(),
        adapter_hang=True,  # provider never yields events either -- only the timer should end this session
        warning_seconds=0.05, max_seconds=0.1,
    )

    assert "session.warning" in _types(ws)
    assert {"type": "session.ended", "reason": "timeout"} in ws.sent_json
    assert state["metrics_rows"][0]["ended_reason"] == "timeout"


# ── JARGON RULE PARITY ───────────────────────────────────────────────
#
# The realtime persona prompt and the legacy pipeline's detect_jargon()
# short-circuit must stop the patient on the same terms. They drifted once
# already: realtime shipped with no jargon handling at all while the landing
# page sold "the AI patient stops you" as a headline feature, so every user in
# the realtime rollout silently lost it. These tests fail if that gap reopens.


def test_realtime_prompt_carries_the_jargon_rule():
    prompt = srt._build_realtime_system_prompt(DEFAULT_SCENARIO.get("nurse_card") or {})

    assert "JARGON RULE (CRITICAL)" in prompt
    # The interrupt must survive rewording, but the patient has to actually ask.
    assert "what does that mean" in prompt.lower()
    # Explaining the term inline must NOT trigger an interrupt, matching
    # detect_jargon()'s explanation-words skip.
    assert "do NOT interrupt" in prompt


def test_realtime_prompt_shares_the_legacy_jargon_term_list():
    from app.services.ai_scoring import MEDICAL_JARGON

    prompt = srt._build_realtime_system_prompt(DEFAULT_SCENARIO.get("nurse_card") or {})

    missing = [term for term in MEDICAL_JARGON if term not in prompt]
    assert not missing, f"realtime prompt is missing legacy jargon terms: {missing}"


def test_realtime_prompt_still_renders_the_patient_card():
    card = {
        "patient_name": "Amit Patel",
        "age": 35,
        "condition": "Type 2 diabetes",
        "instructions_for_ai": "Anxious about self-injection.",
        "emotional_triggers": ["needles"],
        "questions_to_ask": ["Will it hurt?"],
        "information_to_withhold": ["father had complications"],
    }

    prompt = srt._build_realtime_system_prompt(card)

    assert "Amit Patel" in prompt
    assert "Anxious about self-injection." in prompt
    assert "needles" in prompt
    assert "Will it hurt?" in prompt
    # Unrendered f-string braces would mean the card silently never reached the model.
    assert "{" not in prompt and "}" not in prompt


# ── STEP 2: PatientState -> live instructions sync ────────────────────
#
# These cover the actual feedback loop this step exists to build: a
# candidate turn changes PatientState -> the adapter receives an updated
# instructions string -> before the session ends. See
# app.services.patient_state.derive_patient_state for why "medication" in a
# patient turn flips "medication non-compliance" from hidden to revealed.

SCENARIO_WITH_HIDDEN_INFO = {
    "id": 42,
    "is_active": True,
    "patient_gender": "female",
    "interlocutor_card": {
        "patient_name": "Mary",
        "age": 68,
        "condition": "chest pain",
        "mood": "anxious",
        "background": "",
        "instructions_for_ai": "Be anxious and guarded.",
        "emotional_triggers": [],
        "questions_to_ask": [],
        "information_to_withhold": ["medication non-compliance"],
    },
}


def test_patient_turn_revealing_hidden_info_pushes_instructions_update(monkeypatch):
    events = [
        TranscriptDelta(role="patient", delta="I haven't been taking my medication regularly."),
        ResponseDone(),
    ]
    ws = FakeWebSocket(
        handshake={"token": "tok", "scenario_id": 42, "session_id": 7},
        audio_chunks=[_DISCONNECT],
    )

    _run_stream(
        monkeypatch, ws, auth_user=FakeUser(), scenario_rows=[SCENARIO_WITH_HIDDEN_INFO],
        adapter_events=events,
    )

    adapter = FakeAdapter.instances[-1]
    assert len(adapter.instructions_updates) == 1
    updated = adapter.instructions_updates[0]
    assert "medication non-compliance" not in updated.split("Still hidden")[1].split("Concerns you have")[0]
    assert "medication non-compliance" in updated.split("Already revealed")[1]


def test_unchanged_patient_state_does_not_push_duplicate_instructions(monkeypatch):
    # Second ResponseDone flushes an empty patient buffer -- state is
    # identical to what was just pushed, so no second update should fire
    # (requirement: one candidate turn, not multiple duplicate updates).
    events = [
        TranscriptDelta(role="patient", delta="I haven't been taking my medication regularly."),
        ResponseDone(),
        ResponseDone(),
    ]
    ws = FakeWebSocket(
        handshake={"token": "tok", "scenario_id": 42, "session_id": 7},
        audio_chunks=[_DISCONNECT],
    )

    _run_stream(
        monkeypatch, ws, auth_user=FakeUser(), scenario_rows=[SCENARIO_WITH_HIDDEN_INFO],
        adapter_events=events,
    )

    adapter = FakeAdapter.instances[-1]
    assert len(adapter.instructions_updates) == 1


def test_no_scenario_state_change_means_no_instructions_update(monkeypatch):
    # DEFAULT_SCENARIO's card has no information_to_withhold/triggers/
    # concerns, so nothing the patient or nurse says can change PatientState.
    events = [TranscriptDelta(role="patient", delta="Hello there."), ResponseDone()]
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42, "session_id": 7}, audio_chunks=[_DISCONNECT])

    _run_stream(monkeypatch, ws, auth_user=FakeUser(), adapter_events=events)

    adapter = FakeAdapter.instances[-1]
    assert adapter.instructions_updates == []


def test_warmup_session_never_syncs_patient_state(monkeypatch):
    events = [TranscriptDelta(role="patient", delta="Nice to meet you."), ResponseDone()]
    ws = FakeWebSocket(handshake={"token": "tok", "mode": "warmup"}, audio_chunks=[_DISCONNECT])

    _run_stream(monkeypatch, ws, auth_user=FakeUser(), adapter_events=events)

    adapter = FakeAdapter.instances[-1]
    assert adapter.instructions_updates == []


def test_interruption_does_not_break_state_sync(monkeypatch):
    events = [
        TranscriptDelta(role="patient", delta="I haven't been taking my medication"),
        Interrupted(),
        ResponseDone(),
    ]
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42, "session_id": 7}, audio_chunks=[_DISCONNECT])

    _run_stream(
        monkeypatch, ws, auth_user=FakeUser(), scenario_rows=[SCENARIO_WITH_HIDDEN_INFO],
        adapter_events=events,
    )

    adapter = FakeAdapter.instances[-1]
    assert adapter.cancel_count == 1
    # The interrupted patient turn's partial text still flushes into the
    # transcript on ResponseDone -- state sync must still fire normally.
    assert len(adapter.instructions_updates) == 1


def test_fresh_session_starts_with_empty_patient_state(monkeypatch):
    # No session_id supplied by the client -- a brand-new session_usage row
    # is minted, so this can never be a reconnect. The initial system prompt
    # must use the empty/default PatientState, not query session_transcripts.
    ws = FakeWebSocket(handshake={"token": "tok", "scenario_id": 42}, audio_chunks=[_DISCONNECT])

    _run_stream(
        monkeypatch, ws, auth_user=FakeUser(), scenario_rows=[SCENARIO_WITH_HIDDEN_INFO],
        prior_transcript_rows=[{"transcript": [{"role": "patient", "text": "irrelevant, must not be read"}]}],
    )

    adapter = FakeAdapter.instances[-1]
    assert "irrelevant" not in adapter.system_prompt
    assert "medication non-compliance" in adapter.system_prompt.split("Still hidden")[1].split("Concerns you have")[0]


def test_reconnect_restores_patient_state_from_prior_transcript(monkeypatch):
    # Client supplies a session_id that validates -- this is a reconnect to
    # an existing session. A prior connection already persisted a
    # session_transcripts row where the patient revealed the hidden info;
    # the new connection's initial prompt must reflect that, not start blank.
    ws = FakeWebSocket(
        handshake={"token": "tok", "scenario_id": 42, "session_id": 7},
        audio_chunks=[_DISCONNECT],
    )

    _run_stream(
        monkeypatch, ws, auth_user=FakeUser(), validate_ok=True, scenario_rows=[SCENARIO_WITH_HIDDEN_INFO],
        prior_transcript_rows=[{
            "transcript": [
                {"role": "nurse", "text": "Are you taking your medication regularly?"},
                {"role": "patient", "text": "No, I haven't been taking my medication."},
            ],
        }],
    )

    adapter = FakeAdapter.instances[-1]
    assert "medication non-compliance" in adapter.system_prompt.split("Already revealed")[1]
    assert "medication non-compliance" not in adapter.system_prompt.split("Still hidden")[1].split("Concerns you have")[0]


def test_reconnect_with_no_prior_transcript_still_starts_fresh(monkeypatch):
    # validate_session succeeding with session_id supplied but no
    # session_transcripts rows yet (e.g. the very first connection attempt
    # raced a client retry) must fall back to the empty PatientState, not
    # error.
    ws = FakeWebSocket(
        handshake={"token": "tok", "scenario_id": 42, "session_id": 7},
        audio_chunks=[_DISCONNECT],
    )

    _run_stream(
        monkeypatch, ws, auth_user=FakeUser(), validate_ok=True, scenario_rows=[SCENARIO_WITH_HIDDEN_INFO],
    )

    adapter = FakeAdapter.instances[-1]
    assert "medication non-compliance" in adapter.system_prompt.split("Still hidden")[1].split("Concerns you have")[0]
