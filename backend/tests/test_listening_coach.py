"""E2.3 -- Listening AI Coach v1.

Pure-function tests for listening_coach.py (context building, confidence
tiers, fallback shapes, schema validation), orchestration tests with
get_weakness/get_mistake_profile/_call_ai monkeypatched at the module
boundary (same style as test_speaking_session_quota.py), and router-level
tests (plan gating, rate limiting, history-gate short-circuit) with
app.routers.listening's imported names monkeypatched directly.

skill_graph.get_weakness and listening_mistake_intelligence.get_mistake_profile
are exercised as black boxes here (already covered by their own test files) --
this file asserts listening_coach calls them, never recomputes what they own,
and never leaks their raw rows into the AI prompt.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

import app.routers.listening as listening_module
import app.services.listening_coach as listening_coach
from app.routers.auth import UserInfo


def _run(coro):
    return asyncio.run(coro)


EMPTY_MISTAKE_PROFILE = {
    "recent_mistakes": [], "corrected_mistakes": [], "persistent_mistakes": [],
    "repeated_mistakes": [], "part_patterns": {}, "frequency": {"total_events": 0, "total_wrong": 0, "distinct_questions_wrong": 0},
}


def _mistake_profile(**overrides):
    return {**EMPTY_MISTAKE_PROFILE, **overrides}


# ── classify_confidence ────────────────────────────────────────────────

def test_confidence_persistent_when_persistent_mistakes_present():
    profile = _mistake_profile(persistent_mistakes=[{"question_id": 1}], repeated_mistakes=[{"question_id": 1}])
    assert listening_coach.classify_confidence(profile) == "persistent pattern"


def test_confidence_recurring_when_only_repeated():
    profile = _mistake_profile(repeated_mistakes=[{"question_id": 1}])
    assert listening_coach.classify_confidence(profile) == "recurring pattern"


def test_confidence_recent_limited_when_no_repeats():
    profile = _mistake_profile(recent_mistakes=[{"question_id": 1}])
    assert listening_coach.classify_confidence(profile) == "recent/limited evidence"


def test_confidence_recent_limited_on_corrected_only():
    """A corrected mistake (wrong once, then right) is not a pattern."""
    profile = _mistake_profile(corrected_mistakes=[{"question_id": 1, "wrong_count": 1}])
    assert listening_coach.classify_confidence(profile) == "recent/limited evidence"


# ── build_coach_context ──────────────────────────────────────────────────

def test_context_takes_top_two_weakest_parts_in_order():
    weakness = [
        {"skill": "A", "label": "Part A", "band": 3.0, "attempts": 4},
        {"skill": "C", "label": "Part C", "band": 3.5, "attempts": 2},
        {"skill": "B", "label": "Part B", "band": 4.0, "attempts": 5},
    ]
    ctx = listening_coach.build_coach_context(weakness, EMPTY_MISTAKE_PROFILE, attempt_count=5)
    assert [w["part"] for w in ctx["weak_parts"]] == ["A", "C"]  # weakest-first, capped at 2


def test_context_strong_performance_has_no_weak_parts():
    ctx = listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=5)
    assert ctx["weak_parts"] == []


def test_context_sufficient_history_flag():
    assert listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=1)["sufficient_history"] is False
    assert listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=2)["sufficient_history"] is True


def test_context_never_carries_raw_mistake_rows():
    """No question ids, selected options, or answer text -- only aggregate
    counts -- ever land in the context the prompt is built from."""
    profile = _mistake_profile(
        recent_mistakes=[{"question_id": 99, "selected_option": "B", "correct_answer": "C"}],
        persistent_mistakes=[{"question_id": 99, "wrong_count": 3}],
    )
    ctx = listening_coach.build_coach_context([], profile, attempt_count=5)
    serialized = str(ctx)
    assert "99" not in serialized
    assert "selected_option" not in serialized and "correct_answer" not in serialized
    assert ctx["persistent_count"] == 1 and ctx["recent_wrong_count"] == 1


# ── validate_coach_response ───────────────────────────────────────────────

VALID_AI_SHAPE = {
    "summary": "Part B is your weak spot.",
    "key_issue": "You misread speaker attitude cues.",
    "why_it_happens": "You focus on words, not tone.",
    "next_action": "Practice Part B with a focus on tone.",
    "recommended_practice": {"part": "B", "reason": "It has your lowest band."},
}


def test_validate_accepts_well_formed_response():
    result = listening_coach.validate_coach_response(dict(VALID_AI_SHAPE))
    assert result == VALID_AI_SHAPE


@pytest.mark.parametrize("missing_key", ["summary", "key_issue", "why_it_happens", "next_action"])
def test_validate_rejects_missing_or_blank_string_fields(missing_key):
    bad = dict(VALID_AI_SHAPE)
    bad[missing_key] = "   "
    assert listening_coach.validate_coach_response(bad) is None


def test_validate_rejects_invalid_part():
    bad = dict(VALID_AI_SHAPE, recommended_practice={"part": "D", "reason": "x"})
    assert listening_coach.validate_coach_response(bad) is None


def test_validate_rejects_missing_recommended_practice():
    bad = dict(VALID_AI_SHAPE)
    del bad["recommended_practice"]
    assert listening_coach.validate_coach_response(bad) is None


def test_validate_rejects_non_dict():
    assert listening_coach.validate_coach_response("not json") is None
    assert listening_coach.validate_coach_response(None) is None


# ── fallback shapes always match the contract ────────────────────────────

def test_insufficient_history_response_matches_contract():
    ctx = listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=1)
    resp = listening_coach.insufficient_history_response(ctx)
    assert listening_coach.validate_coach_response(resp) == resp


def test_deterministic_fallback_matches_contract_with_and_without_weak_parts():
    weak_ctx = listening_coach.build_coach_context(
        [{"skill": "A", "label": "Part A", "band": 3.0, "attempts": 3}], EMPTY_MISTAKE_PROFILE, attempt_count=3,
    )
    strong_ctx = listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=3)
    assert listening_coach.validate_coach_response(listening_coach.deterministic_fallback(weak_ctx))
    assert listening_coach.validate_coach_response(listening_coach.deterministic_fallback(strong_ctx))


def test_recommended_practice_uses_weakest_part_when_available():
    ctx = listening_coach.build_coach_context(
        [{"skill": "C", "label": "Part C", "band": 2.5, "attempts": 3}], EMPTY_MISTAKE_PROFILE, attempt_count=3,
    )
    assert listening_coach.deterministic_fallback(ctx)["recommended_practice"]["part"] == "C"


def test_recommended_practice_falls_back_to_worst_part_pattern():
    profile = _mistake_profile(part_patterns={"A": {"wrong": 1, "total": 4, "rate": 0.25}, "B": {"wrong": 3, "total": 4, "rate": 0.75}})
    ctx = listening_coach.build_coach_context([], profile, attempt_count=3)
    assert listening_coach.deterministic_fallback(ctx)["recommended_practice"]["part"] == "B"


def test_recommended_practice_defaults_when_no_signal_at_all():
    ctx = listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=3)
    assert listening_coach.deterministic_fallback(ctx)["recommended_practice"]["part"] in ("A", "B", "C")


# ── generate_coach_response: AI success / failure / malformed / timeout ──

def test_ai_success_returns_validated_shape(monkeypatch):
    async def fake_call_ai(messages, purpose, max_tokens, json_mode, temperature, user_id):
        assert purpose == "listening_coach"  # E2.3: distinct purpose, never reuses "coach"
        assert json_mode is True and temperature == 0.0
        return dict(VALID_AI_SHAPE)

    monkeypatch.setattr(listening_coach, "_call_ai", fake_call_ai)
    ctx = listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=3)
    result = _run(listening_coach.generate_coach_response(ctx, "user-1"))
    assert result == VALID_AI_SHAPE


def test_provider_failure_falls_back(monkeypatch):
    async def fake_call_ai(*_a, **_k):
        return {"raw_feedback": "AI service unavailable.", "provider_failure": True}

    monkeypatch.setattr(listening_coach, "_call_ai", fake_call_ai)
    ctx = listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=3)
    result = _run(listening_coach.generate_coach_response(ctx, "user-1"))
    assert listening_coach.validate_coach_response(result) == result
    assert "raw_feedback" not in str(result)  # never surfaces raw model/provider text


def test_malformed_json_falls_back(monkeypatch):
    async def fake_call_ai(*_a, **_k):
        return {"summary": "only one field"}  # missing everything else

    monkeypatch.setattr(listening_coach, "_call_ai", fake_call_ai)
    ctx = listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=3)
    result = _run(listening_coach.generate_coach_response(ctx, "user-1"))
    assert listening_coach.validate_coach_response(result) == result


def test_ai_timeout_falls_back(monkeypatch):
    async def slow_call_ai(*_a, **_k):
        await asyncio.sleep(0.2)
        return dict(VALID_AI_SHAPE)

    monkeypatch.setattr(listening_coach, "_call_ai", slow_call_ai)
    monkeypatch.setattr(listening_coach, "AI_CALL_TIMEOUT_SECONDS", 0.02)
    ctx = listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=3)
    result = _run(listening_coach.generate_coach_response(ctx, "user-1"))
    assert listening_coach.validate_coach_response(result) == result


# ── prepare_coach_context: canonical sources + user isolation ────────────

def test_prepare_context_reads_from_canonical_sources_and_isolates_users(monkeypatch):
    """skill_graph.get_weakness and listening_mistake_intelligence.get_mistake_profile
    stay the only weakness/mistake sources -- and each user only ever sees
    their own data."""
    weakness_by_user = {"user-1": [{"skill": "A", "label": "Part A", "band": 3.0, "attempts": 2}], "user-2": []}
    calls = []

    async def fake_get_weakness(user_db, user_id, tag_prefix, label_fn=None):
        calls.append(("weakness", user_id))
        assert tag_prefix == "listening:"
        return weakness_by_user[user_id]

    async def fake_get_mistake_profile(user_db, user_id):
        calls.append(("mistakes", user_id))
        return EMPTY_MISTAKE_PROFILE

    async def fake_count(user_db, user_id):
        calls.append(("count", user_id))
        return 5

    monkeypatch.setattr(listening_coach, "get_weakness", fake_get_weakness)
    monkeypatch.setattr(listening_coach, "get_mistake_profile", fake_get_mistake_profile)
    monkeypatch.setattr(listening_coach, "_count_listening_attempts", fake_count)

    ctx1 = _run(listening_coach.prepare_coach_context(None, "user-1"))
    ctx2 = _run(listening_coach.prepare_coach_context(None, "user-2"))

    assert ctx1["weak_parts"][0]["part"] == "A"
    assert ctx2["weak_parts"] == []
    assert ("weakness", "user-1") in calls and ("weakness", "user-2") in calls
    assert ("mistakes", "user-1") in calls and ("mistakes", "user-2") in calls


# ── router: plan gating, history-gate short-circuit, rate limiting ───────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeProfileQuery:
    def __init__(self, plan):
        self._plan = plan

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        # get_plan_from_profile treats a paid plan with no plan_expires_at as
        # expired (see plan_gating.is_subscription_active) -- a paid-plan
        # fixture needs a future expiry to actually resolve to that plan.
        expires_at = None if self._plan == "free" else "2099-01-01T00:00:00+00:00"
        return _FakeResult([{"plan": self._plan, "plan_expires_at": expires_at}])


class _FakeProfileSupabase:
    def __init__(self, plan):
        self._plan = plan

    def table(self, name):
        assert name == "user_profiles"
        return _FakeProfileQuery(self._plan)


def _user(uid="user-1"):
    return UserInfo(id=uid, email="n@example.com")


@pytest.mark.parametrize("plan", ["basic", "pro", "elite"])
def test_paid_plans_pass_the_gate(monkeypatch, plan):
    monkeypatch.setattr(listening_module, "get_supabase", lambda: _FakeProfileSupabase(plan))

    async def fake_prepare(user_db, user_id):
        return listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=0)

    monkeypatch.setattr(listening_module, "prepare_coach_context", fake_prepare)
    result = _run(listening_module.listening_coach(current_user=_user(), user_db=None))
    assert result["recommended_practice"]["part"] in ("A", "B", "C")


def test_free_plan_is_locked(monkeypatch):
    monkeypatch.setattr(listening_module, "get_supabase", lambda: _FakeProfileSupabase("free"))
    with pytest.raises(HTTPException) as exc_info:
        _run(listening_module.listening_coach(current_user=_user(), user_db=None))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["upgrade_required"] is True


def test_insufficient_history_never_calls_ai_or_rate_limiter(monkeypatch):
    monkeypatch.setattr(listening_module, "get_supabase", lambda: _FakeProfileSupabase("pro"))

    ctx = listening_coach.build_coach_context([], EMPTY_MISTAKE_PROFILE, attempt_count=1)

    async def fake_prepare(user_db, user_id):
        return ctx

    def fail_if_called(*_a, **_k):
        raise AssertionError("rate limiter must not run before the history gate short-circuits")

    async def fail_if_called_async(*_a, **_k):
        raise AssertionError("generate_coach_response must not run when history is insufficient")

    monkeypatch.setattr(listening_module, "prepare_coach_context", fake_prepare)
    monkeypatch.setattr(listening_module, "generate_coach_response", fail_if_called_async)
    monkeypatch.setattr(listening_module._coach_rate_limiter, "is_rate_limited", fail_if_called)

    result = _run(listening_module.listening_coach(current_user=_user(), user_db=None))
    assert result == listening_coach.insufficient_history_response(ctx)


def test_rate_limit_blocks_before_ai_call(monkeypatch):
    monkeypatch.setattr(listening_module, "get_supabase", lambda: _FakeProfileSupabase("pro"))

    async def fake_prepare(user_db, user_id):
        return {"sufficient_history": True, "attempt_count": 5}

    async def fail_if_called_async(*_a, **_k):
        raise AssertionError("generate_coach_response must not run once rate-limited")

    monkeypatch.setattr(listening_module, "prepare_coach_context", fake_prepare)
    monkeypatch.setattr(listening_module, "generate_coach_response", fail_if_called_async)
    monkeypatch.setattr(listening_module._coach_rate_limiter, "is_rate_limited", lambda _key: True)

    with pytest.raises(HTTPException) as exc_info:
        _run(listening_module.listening_coach(current_user=_user(), user_db=None))
    assert exc_info.value.status_code == 429


def test_sufficient_history_calls_ai_path(monkeypatch):
    monkeypatch.setattr(listening_module, "get_supabase", lambda: _FakeProfileSupabase("pro"))

    async def fake_prepare(user_db, user_id):
        return {"sufficient_history": True, "attempt_count": 5}

    async def fake_generate(context, user_id):
        assert context["attempt_count"] == 5
        return dict(VALID_AI_SHAPE)

    monkeypatch.setattr(listening_module, "prepare_coach_context", fake_prepare)
    monkeypatch.setattr(listening_module, "generate_coach_response", fake_generate)
    monkeypatch.setattr(listening_module._coach_rate_limiter, "is_rate_limited", lambda _key: False)

    result = _run(listening_module.listening_coach(current_user=_user(), user_db=None))
    assert result == VALID_AI_SHAPE
