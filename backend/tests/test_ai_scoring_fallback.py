"""Step 16A: fix the tautological fallback gate in ai_scoring._call_ai.

The bug: for json_mode=True, a truncated/malformed response still produces a
non-empty `raw_feedback` (the partial text), which used to satisfy
`result.get("raw_feedback") or (json_mode and result)` and return immediately
-- skipping the fallback model entirely and letting score_speaking persist a
fake 0/6 as HTTP 200 instead of surfacing provider_failure -> 503.

No real network -- ai_registry.get_model_config / dispatch_call are faked.
Same style as test_speaking_chat_ai_failure.py.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

import app.services.ai_scoring as ai_scoring
import app.routers.speaking as speaking_module
from app.services import ai_registry


def _run(coro):
    return asyncio.run(coro)


class FakeCfg:
    def __init__(self, provider, model_name, fallback=None):
        self.provider = provider
        self.model_name = model_name
        self.fallback = fallback


PRIMARY = FakeCfg("google", "primary-model")
FALLBACK = FakeCfg("openrouter", "fallback-model")
PRIMARY_WITH_FALLBACK = FakeCfg("google", "primary-model", fallback=FALLBACK)

VALID_SCORES_JSON = (
    '{"scores": {"clinical_communication": {"score": 5, "feedback": "ok"}, '
    '"linguistic_delivery": {"score": 5, "feedback": "ok"}, '
    '"relationship_building": {"score": 5, "feedback": "ok"}}}'
)
VALID_ZERO_SCORES_JSON = (
    '{"scores": {"clinical_communication": {"score": 0, "feedback": "poor"}, '
    '"linguistic_delivery": {"score": 0, "feedback": "poor"}, '
    '"relationship_building": {"score": 0, "feedback": "poor"}}}'
)
TRUNCATED_JSON = '{"scores": {"clinical_communication": {"score": 5, "fee'


def _resp(text, finish_reason="stop"):
    return {"text": text, "finish_reason": finish_reason, "usage": {"input_tokens": 1, "output_tokens": 1}}


def _patch_infra(monkeypatch, cfg, dispatch_results):
    """dispatch_results: list popped in call order; each item is either a
    dict (dispatch_call return) or an Exception instance (raised)."""
    calls = []

    async def fake_get_model_config(purpose):
        return cfg

    async def fake_dispatch_call(candidate, messages, max_tokens, json_mode, temperature, **kw):
        calls.append(candidate.model_name)
        item = dispatch_results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def fake_log_ai_usage(*a, **kw):
        return None

    monkeypatch.setattr(ai_registry, "get_model_config", fake_get_model_config)
    monkeypatch.setattr(ai_registry, "dispatch_call", fake_dispatch_call)
    monkeypatch.setattr(ai_scoring, "log_ai_usage", fake_log_ai_usage)
    monkeypatch.setattr(ai_scoring, "_log_ai_error", lambda *a, **kw: None)
    monkeypatch.setattr(ai_scoring.circuit_breaker, "allow_request", lambda p: True)
    monkeypatch.setattr(ai_scoring.circuit_breaker, "record_success", lambda p: None)
    monkeypatch.setattr(ai_scoring.circuit_breaker, "record_failure", lambda p: None)
    return calls


# ── Test 1: primary valid -> no fallback ──────────────────────────────────

def test_primary_valid_json_returns_immediately_no_fallback(monkeypatch):
    calls = _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [_resp(VALID_SCORES_JSON)])

    result = _run(ai_scoring._call_ai(
        [{"role": "user", "content": "hi"}], purpose="speaking_scoring_free", json_mode=True,
    ))

    assert calls == ["primary-model"]
    assert result["scores"]["clinical_communication"]["score"] == 5
    assert result.get("provider_failure", False) is False


# ── Test 2: primary invalid JSON -> fallback invoked ──────────────────────

def test_primary_invalid_json_invokes_fallback(monkeypatch):
    calls = _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [
        _resp("not json at all"),
        _resp(VALID_SCORES_JSON),
    ])

    result = _run(ai_scoring._call_ai(
        [{"role": "user", "content": "hi"}], purpose="speaking_scoring_free", json_mode=True,
    ))

    assert calls == ["primary-model", "fallback-model"]
    assert result["scores"]["clinical_communication"]["score"] == 5


# ── Test 3: primary truncated JSON (MAX_TOKENS) -> fallback invoked ───────

def test_primary_truncated_json_invokes_fallback(monkeypatch):
    calls = _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [
        _resp(TRUNCATED_JSON, finish_reason="MAX_TOKENS"),
        _resp(VALID_SCORES_JSON),
    ])

    result = _run(ai_scoring._call_ai(
        [{"role": "user", "content": "hi"}], purpose="speaking_scoring_free", json_mode=True,
    ))

    assert calls == ["primary-model", "fallback-model"]
    assert result["scores"]["clinical_communication"]["score"] == 5
    assert result.get("provider_failure", False) is False


# ── Test 4: primary provider failure (exception) -> fallback invoked ──────

def test_primary_provider_failure_invokes_fallback(monkeypatch):
    calls = _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [
        ai_registry.ModelCallError("Gemini API error 500: boom", 500),
        _resp(VALID_SCORES_JSON),
    ])

    result = _run(ai_scoring._call_ai(
        [{"role": "user", "content": "hi"}], purpose="speaking_scoring_free", json_mode=True,
    ))

    assert calls == ["primary-model", "fallback-model"]
    assert result["scores"]["clinical_communication"]["score"] == 5
    assert result.get("provider_failure", False) is False


# ── Test 5: fallback valid -> successful structured result (distinguishes
#    the fallback's own data from the primary's, proving fallback was used) ─

def test_fallback_result_is_the_one_actually_returned(monkeypatch):
    fallback_json = (
        '{"scores": {"clinical_communication": {"score": 3, "feedback": "from fallback"}, '
        '"linguistic_delivery": {"score": 3, "feedback": "from fallback"}, '
        '"relationship_building": {"score": 3, "feedback": "from fallback"}}}'
    )
    _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [
        _resp(TRUNCATED_JSON, finish_reason="MAX_TOKENS"),
        _resp(fallback_json),
    ])

    result = _run(ai_scoring._call_ai(
        [{"role": "user", "content": "hi"}], purpose="speaking_scoring_free", json_mode=True,
    ))

    assert result["scores"]["clinical_communication"]["feedback"] == "from fallback"


# ── Test 6: primary + fallback both invalid JSON -> provider_failure=True ─

def test_both_invalid_json_yields_provider_failure(monkeypatch):
    calls = _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [
        _resp(TRUNCATED_JSON, finish_reason="MAX_TOKENS"),
        _resp(TRUNCATED_JSON, finish_reason="MAX_TOKENS"),
    ])

    result = _run(ai_scoring._call_ai(
        [{"role": "user", "content": "hi"}], purpose="speaking_scoring_free", json_mode=True,
    ))

    assert calls == ["primary-model", "fallback-model"]
    assert result["provider_failure"] is True
    assert "scores" not in result


# ── Test 7: primary + fallback both provider failures -> provider_failure ─

def test_both_provider_failures_yields_provider_failure(monkeypatch):
    calls = _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [
        ai_registry.ModelCallError("Gemini API error 500: boom", 500),
        ai_registry.ModelCallError("OpenRouter API error 500: boom", 500),
    ])

    result = _run(ai_scoring._call_ai(
        [{"role": "user", "content": "hi"}], purpose="speaking_scoring_free", json_mode=True,
    ))

    assert calls == ["primary-model", "fallback-model"]
    assert result["provider_failure"] is True


# ── Test 10: legitimate valid zero scores still accepted ──────────────────

def test_valid_zero_scores_accepted_not_treated_as_failure(monkeypatch):
    _patch_infra(monkeypatch, PRIMARY, [_resp(VALID_ZERO_SCORES_JSON)])

    result = _run(ai_scoring._call_ai(
        [{"role": "user", "content": "hi"}], purpose="speaking_scoring_free", json_mode=True,
    ))

    assert result.get("provider_failure", False) is False
    assert result["scores"]["clinical_communication"]["score"] == 0


# ── Test 11: json_mode=False behavior unchanged ────────────────────────────

def test_non_json_mode_success_unchanged_no_fallback(monkeypatch):
    calls = _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [_resp("a real patient reply")])

    result = _run(ai_scoring._call_ai(
        [{"role": "user", "content": "hi"}], purpose="patient_roleplay", json_mode=False,
    ))

    assert calls == ["primary-model"]
    assert result["raw_feedback"] == "a real patient reply"
    assert result.get("provider_failure", False) is False


def test_non_json_mode_empty_text_invokes_fallback(monkeypatch):
    calls = _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [
        _resp(""),
        _resp("fallback reply"),
    ])

    result = _run(ai_scoring._call_ai(
        [{"role": "user", "content": "hi"}], purpose="patient_roleplay", json_mode=False,
    ))

    assert calls == ["primary-model", "fallback-model"]
    assert result["raw_feedback"] == "fallback reply"


# ── score_speaking(): end-to-end through the real scoring/fallback path ───

NURSE_CARD = {"tasks": ["Explain the procedure"]}
HISTORY = [{"role": "nurse", "content": "Hello"}, {"role": "patient", "content": "Hi"}]


def test_score_speaking_fallback_succeeds_after_primary_truncation(monkeypatch):
    _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [
        _resp(TRUNCATED_JSON, finish_reason="MAX_TOKENS"),
        _resp(VALID_SCORES_JSON),
    ])

    result = _run(ai_scoring.score_speaking(
        NURSE_CARD, HISTORY, purpose="speaking_scoring_premium", criteria_count=3,
    ))

    assert result.get("provider_failure", False) is False
    assert result["overall_band"] == 5.0


def test_score_speaking_terminal_failure_sets_provider_failure(monkeypatch):
    _patch_infra(monkeypatch, PRIMARY_WITH_FALLBACK, [
        _resp(TRUNCATED_JSON, finish_reason="MAX_TOKENS"),
        _resp(TRUNCATED_JSON, finish_reason="MAX_TOKENS"),
        # score_speaking's own same-model retry (see line ~630) re-enters
        # _call_ai and walks primary+fallback again.
        _resp(TRUNCATED_JSON, finish_reason="MAX_TOKENS"),
        _resp(TRUNCATED_JSON, finish_reason="MAX_TOKENS"),
    ])

    result = _run(ai_scoring.score_speaking(
        NURSE_CARD, HISTORY, purpose="speaking_scoring_premium", criteria_count=3,
    ))

    assert result["provider_failure"] is True
    assert result["overall_band"] == 0.0


def test_score_speaking_valid_zero_scores_not_a_failure(monkeypatch):
    _patch_infra(monkeypatch, PRIMARY, [_resp(VALID_ZERO_SCORES_JSON)])

    result = _run(ai_scoring.score_speaking(
        NURSE_CARD, HISTORY, purpose="speaking_scoring_free", criteria_count=3,
    ))

    assert result.get("provider_failure", False) is False
    assert result["overall_band"] == 0.0
    assert result["scores"]["clinical_communication"]["score"] == 0


# ── /speaking/score endpoint: terminal failure -> 503, no fake submission ─

class _FakeResult:
    def __init__(self, data):
        self.data = data


_SCENARIO_ROW = {"id": 1, "title": "T", "nurse_card": NURSE_CARD, "scoring_criteria": {}}
_PROFILE_ROW = {"plan": "free", "plan_expires_at": None, "sessions_used_this_month": 0}


class _FakeScenarioSupabase:
    """Serves both `scenarios` (score_speaking_session's own lookup) and
    `user_profiles` (get_user_profile) off the same client, matching how
    get_supabase() is a single shared handle in the real endpoint."""

    _ROWS = {"scenarios": [_SCENARIO_ROW], "user_profiles": [_PROFILE_ROW]}

    def table(self, name):
        self._name = name
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        return _FakeResult(self._ROWS.get(self._name, []))


class _FakeUserDb:
    def __init__(self):
        self.inserted = []

    def table(self, name):
        assert name == "submissions"
        return self

    def insert(self, payload):
        self.inserted.append(payload)
        return self

    def execute(self):
        return _FakeResult([dict(self.inserted[-1], id=1)])


from app.routers.auth import UserInfo  # noqa: E402
from app.routers.speaking import ChatMessage, SpeakingSubmitRequest  # noqa: E402


def _submit_request():
    return SpeakingSubmitRequest(
        scenario_id=1,
        history=[ChatMessage(role="nurse", content="Hello"), ChatMessage(role="patient", content="Hi")],
        duration_seconds=60,
        session_id=99,
    )


def test_speaking_score_endpoint_terminal_failure_returns_503_no_submission(monkeypatch):
    async def fake_score_speaking(**_kw):
        return {"provider_failure": True, "overall_band": 0.0, "scores": {}}

    user_db = _FakeUserDb()
    with patch.object(speaking_module, "get_supabase", lambda: _FakeScenarioSupabase()), \
         patch.object(speaking_module, "validate_session", lambda *_a, **_k: True), \
         patch.object(speaking_module, "score_speaking", fake_score_speaking), \
         patch.object(speaking_module, "is_first_ever_session", lambda *_a, **_k: False), \
         patch.object(speaking_module, "claim_session_for_scoring", lambda *_a, **_k: True):
        with pytest.raises(HTTPException) as exc_info:
            _run(speaking_module.score_speaking_session(
                request=_submit_request(),
                current_user=UserInfo(id="u1", email="u1@example.com"),
                user_db=user_db,
            ))

    assert exc_info.value.status_code == 503
    assert user_db.inserted == []  # no fake 0/6 submission persisted


def test_speaking_score_endpoint_valid_zero_score_returns_200_and_persists(monkeypatch):
    async def fake_score_speaking(**_kw):
        return {
            "provider_failure": False, "overall_band": 0.0,
            "scores": {"clinical_communication": {"score": 0, "feedback": "poor"}},
        }

    async def fake_insights(*_a, **_k):
        return {}

    async def fake_noop(*_a, **_k):
        return {}

    user_db = _FakeUserDb()
    with patch.object(speaking_module, "get_supabase", lambda: _FakeScenarioSupabase()), \
         patch.object(speaking_module, "validate_session", lambda *_a, **_k: True), \
         patch.object(speaking_module, "score_speaking", fake_score_speaking), \
         patch.object(speaking_module, "is_first_ever_session", lambda *_a, **_k: False), \
         patch.object(speaking_module, "claim_session_for_scoring", lambda *_a, **_k: True), \
         patch.object(speaking_module, "record_skill_observations", fake_noop), \
         patch.object(speaking_module, "_build_speaking_insights", fake_insights):
        _run(speaking_module.score_speaking_session(
            request=_submit_request(),
            current_user=UserInfo(id="u1", email="u1@example.com"),
            user_db=user_db,
        ))

    assert len(user_db.inserted) == 1
    assert user_db.inserted[0]["score"] == 0.0
