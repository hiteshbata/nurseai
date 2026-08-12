"""
Regression tests for the P1 QA bug: a failed AI call on /speaking/chat's
session-start turn was consuming a monthly session credit even though the
student never got a real conversation. Covers the full lifecycle --
check_and_increment_session (charge), release_session_charge (refund on AI
failure), and chat_with_patient (the route wiring both together) -- plus the
existing quota-enforcement and concurrency-safety behavior that must survive
the fix untouched.

Same style as test_speaking_realtime_router.py: routes/helpers called
directly with a fake Supabase client, no live DB, no FastAPI TestClient.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

import app.routers.sessions as sessions_module
import app.routers.speaking as speaking_module
from app.routers.auth import UserInfo
from app.routers.speaking import PatientChatRequest


def _run(coro):
    return asyncio.run(coro)


# ── Fake Supabase: user_profiles (single row, CAS-checked updates) + ──────
# ── session_usage (list, auto-incrementing id) ─────────────────────────

class FakeResult:
    def __init__(self, data=None, count=None):
        self.data = data if data is not None else []
        self.count = count


class FakeQuery:
    def __init__(self, table_name, state):
        self.table_name = table_name
        self.state = state
        self._op = None
        self._payload = None
        self._filters = []
        self._count_mode = None

    def select(self, cols=None, count=None):
        self._op = self._op or "select"
        self._count_mode = count
        return self

    def upsert(self, payload, on_conflict=None, ignore_duplicates=False):
        self._op = "upsert"
        self._payload = payload
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        if self.table_name == "user_profiles":
            return self._exec_user_profiles()
        if self.table_name == "session_usage":
            return self._exec_session_usage()
        raise AssertionError(f"unexpected table {self.table_name!r}")

    def _match_profile(self):
        profile = self.state.get("profile")
        if profile is None:
            return None
        for col, val in self._filters:
            if profile.get(col) != val:
                return None
        return profile

    def _exec_user_profiles(self):
        if self._op == "upsert":
            if self.state.get("profile") is None:
                self.state["profile"] = dict(self._payload)
            return FakeResult([self.state["profile"]])
        if self._op == "select":
            profile = self.state.get("profile")
            return FakeResult([dict(profile)] if profile else [])
        if self._op == "update":
            # Simulates a concurrent request winning the race between this
            # request's read and its compare-and-swap write, so the CAS
            # filter below observes a changed counter -- exactly what the
            # real DB would do under concurrent writers.
            interference = self.state.pop("interference", None)
            if interference and any(k in self._payload for k in interference["fields"]):
                interference["fn"](self.state["profile"])
            profile = self._match_profile()
            if profile is None:
                return FakeResult([])
            profile.update(self._payload)
            return FakeResult([dict(profile)])
        raise AssertionError(f"unexpected op {self._op!r} on user_profiles")

    def _exec_session_usage(self):
        rows = self.state.setdefault("session_usage", [])
        if self._op == "insert":
            new_id = self.state.get("next_id", 1)
            self.state["next_id"] = new_id + 1
            row = dict(self._payload)
            row["id"] = new_id
            rows.append(row)
            return FakeResult([row])
        if self._op == "select":
            matched = [r for r in rows if all(r.get(c) == v for c, v in self._filters)]
            if self._count_mode == "exact":
                return FakeResult(matched, count=len(matched))
            return FakeResult(matched)
        if self._op == "delete":
            remaining = [r for r in rows if not all(r.get(c) == v for c, v in self._filters)]
            self.state["session_usage"] = remaining
            return FakeResult([])
        raise AssertionError(f"unexpected op {self._op!r} on session_usage")


class FakeRPC:
    def execute(self):
        return FakeResult([])


class FakeSupabase:
    def __init__(self, state):
        self.state = state

    def table(self, name):
        return FakeQuery(name, self.state)

    def rpc(self, *_a, **_k):
        return FakeRPC()


def _fresh_state(sessions_used=0, bonus=0):
    return {
        "profile": {
            "user_id": "user-1",
            "plan": "free",
            "plan_expires_at": None,
            "sessions_used_this_month": sessions_used,
            "sessions_reset_date": sessions_module.get_month_start_utc(),
            "auto_renew_enabled": False,
            "bonus_sessions": bonus,
        },
        "session_usage": [],
        "next_id": 1,
    }


# ── check_and_increment_session / release_session_charge (unit level) ────

def test_check_and_increment_session_charges_one_credit(monkeypatch):
    state = _fresh_state(sessions_used=0)
    fake = FakeSupabase(state)
    monkeypatch.setattr(sessions_module, "get_supabase", lambda: fake)

    usage = sessions_module.check_and_increment_session(UserInfo(id="user-1", email="n@example.com"), fake)

    assert usage["allowed"] is True
    assert usage["spent_bonus"] is False
    assert state["profile"]["sessions_used_this_month"] == 1
    assert len(state["session_usage"]) == 1


def test_release_session_charge_refunds_plan_quota(monkeypatch):
    state = _fresh_state(sessions_used=1)
    state["session_usage"] = [{"id": 7, "user_id": "user-1", "session_type": "speaking"}]
    fake = FakeSupabase(state)
    monkeypatch.setattr(sessions_module, "get_supabase", lambda: fake)

    sessions_module.release_session_charge("user-1", 7, spent_bonus=False)

    assert state["profile"]["sessions_used_this_month"] == 0
    assert state["session_usage"] == []


def test_release_session_charge_refunds_bonus_wallet(monkeypatch):
    state = _fresh_state(sessions_used=3, bonus=2)
    state["profile"]["bonus_sessions"] = 1  # one bonus already spent
    state["session_usage"] = [{"id": 9, "user_id": "user-1", "session_type": "speaking"}]
    fake = FakeSupabase(state)
    monkeypatch.setattr(sessions_module, "get_supabase", lambda: fake)

    sessions_module.release_session_charge("user-1", 9, spent_bonus=True)

    assert state["profile"]["bonus_sessions"] == 2
    assert state["profile"]["sessions_used_this_month"] == 3  # untouched
    assert state["session_usage"] == []


def test_check_and_increment_session_429_when_quota_exhausted(monkeypatch):
    state = _fresh_state(sessions_used=3)  # free plan limit is 3
    fake = FakeSupabase(state)
    monkeypatch.setattr(sessions_module, "get_supabase", lambda: fake)

    with pytest.raises(HTTPException) as exc_info:
        sessions_module.check_and_increment_session(UserInfo(id="user-1", email="n@example.com"), fake)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"] == "session_limit_reached"
    assert state["profile"]["sessions_used_this_month"] == 3  # unchanged


def test_check_and_increment_session_survives_concurrent_writer(monkeypatch):
    """A second request incrementing the same counter between this
    request's read and its compare-and-swap write must not cause a lost
    update -- the retry loop should re-read and succeed against the new
    value instead of overwriting the concurrent request's increment."""
    state = _fresh_state(sessions_used=0)
    fake = FakeSupabase(state)
    monkeypatch.setattr(sessions_module, "get_supabase", lambda: fake)

    state["interference"] = {
        "fields": ["sessions_used_this_month"],
        "fn": lambda profile: profile.__setitem__(
            "sessions_used_this_month", profile["sessions_used_this_month"] + 1
        ),
    }

    usage = sessions_module.check_and_increment_session(UserInfo(id="user-1", email="n@example.com"), fake)

    assert usage["allowed"] is True
    # The interfering write (+1) and this request's own charge (+1) both
    # landed -- neither was silently lost to the race.
    assert state["profile"]["sessions_used_this_month"] == 2
    assert "interference" not in state  # consumed on the first (failed) attempt


# ── chat_with_patient (route-level): charge/refund wiring ────────────────

DEFAULT_SCENARIO = {
    "id": 42,
    "is_active": True,
    "interlocutor_card": {"patient_name": "Mary", "instructions_for_ai": "Be anxious."},
}


class FakeScenarioSupabase:
    """Just enough of get_supabase()'s surface for chat_with_patient's own
    scenario lookup (separate from the sessions.py client above)."""

    def table(self, name):
        assert name == "scenarios"
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        return FakeResult([dict(DEFAULT_SCENARIO)])


def _patch_common(monkeypatch, state, fake_sessions_supabase, provider_failure, raises=None):
    monkeypatch.setattr(sessions_module, "get_supabase", lambda: fake_sessions_supabase)
    monkeypatch.setattr(speaking_module, "get_supabase", lambda: FakeScenarioSupabase())

    async def fake_get_patient_response(**kwargs):
        if raises is not None:
            raise raises
        return ("Hello nurse.", provider_failure)

    monkeypatch.setattr(speaking_module, "get_patient_response", fake_get_patient_response)


def _make_request(session_id=None):
    return PatientChatRequest(scenario_id=42, message="How are you?", history=[], session_id=session_id)


def test_failed_ai_call_does_not_consume_a_credit(monkeypatch):
    state = _fresh_state(sessions_used=0)
    fake = FakeSupabase(state)
    _patch_common(monkeypatch, state, fake, provider_failure=True)

    with pytest.raises(HTTPException) as exc_info:
        _run(speaking_module.chat_with_patient(
            request=_make_request(),
            current_user=UserInfo(id="user-1", email="n@example.com"),
            user_db=fake,
        ))

    assert exc_info.value.status_code == 503
    assert state["profile"]["sessions_used_this_month"] == 0
    assert state["session_usage"] == []


def test_retry_after_failed_ai_call_does_not_burn_a_second_credit(monkeypatch):
    state = _fresh_state(sessions_used=0)
    fake = FakeSupabase(state)
    _patch_common(monkeypatch, state, fake, provider_failure=True)

    for _ in range(2):
        with pytest.raises(HTTPException):
            _run(speaking_module.chat_with_patient(
                request=_make_request(),  # client has no session_id after a failed attempt
                current_user=UserInfo(id="user-1", email="n@example.com"),
                user_db=fake,
            ))

    assert state["profile"]["sessions_used_this_month"] == 0
    assert state["session_usage"] == []


def test_unexpected_exception_on_session_start_also_refunds(monkeypatch):
    state = _fresh_state(sessions_used=0)
    fake = FakeSupabase(state)
    _patch_common(monkeypatch, state, fake, provider_failure=False, raises=RuntimeError("boom"))

    with pytest.raises(HTTPException) as exc_info:
        _run(speaking_module.chat_with_patient(
            request=_make_request(),
            current_user=UserInfo(id="user-1", email="n@example.com"),
            user_db=fake,
        ))

    assert exc_info.value.status_code == 503
    assert state["profile"]["sessions_used_this_month"] == 0
    assert state["session_usage"] == []


def test_successful_session_consumes_exactly_one_credit(monkeypatch):
    state = _fresh_state(sessions_used=0)
    fake = FakeSupabase(state)
    _patch_common(monkeypatch, state, fake, provider_failure=False)

    response = _run(speaking_module.chat_with_patient(
        request=_make_request(),
        current_user=UserInfo(id="user-1", email="n@example.com"),
        user_db=fake,
    ))

    assert response.patient_reply == "Hello nurse."
    assert state["profile"]["sessions_used_this_month"] == 1
    assert len(state["session_usage"]) == 1


def test_ai_failure_mid_session_does_not_touch_quota(monkeypatch):
    """A later turn of an already-charged session failing must not refund
    (nothing new was charged) or double-charge -- check_and_increment_session
    should never even run for this turn."""
    state = _fresh_state(sessions_used=1)
    state["session_usage"] = [{"id": 5, "user_id": "user-1", "session_type": "speaking"}]
    fake = FakeSupabase(state)
    _patch_common(monkeypatch, state, fake, provider_failure=True)
    monkeypatch.setattr(speaking_module, "validate_session", lambda user_id, session_id: True)

    def fail_if_called(*_a, **_k):
        raise AssertionError("check_and_increment_session must not run for an already-charged session")

    monkeypatch.setattr(speaking_module, "check_and_increment_session", fail_if_called)

    with pytest.raises(HTTPException) as exc_info:
        _run(speaking_module.chat_with_patient(
            request=_make_request(session_id=5),
            current_user=UserInfo(id="user-1", email="n@example.com"),
            user_db=fake,
        ))

    assert exc_info.value.status_code == 503
    assert state["profile"]["sessions_used_this_month"] == 1  # unchanged, not refunded
    assert state["session_usage"] == [{"id": 5, "user_id": "user-1", "session_type": "speaking"}]  # not deleted
