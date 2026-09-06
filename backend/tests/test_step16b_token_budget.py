"""Step 16B: assert the raised generation-budget constants actually reach
the request-generation layer (ai_registry.dispatch_call), not just that the
module-level constants exist. Same fake-infra style as
test_ai_scoring_fallback.py -- no real network.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.ai_scoring as ai_scoring
from app.services import ai_registry
from app.services import semantic_evidence


def _run(coro):
    return asyncio.run(coro)


class FakeCfg:
    def __init__(self, provider, model_name, fallback=None):
        self.provider = provider
        self.model_name = model_name
        self.fallback = fallback


PRIMARY = FakeCfg("google", "primary-model")

NURSE_CARD = {"tasks": ["Explain the procedure"]}
HISTORY = [{"role": "nurse", "content": "Hello"}, {"role": "patient", "content": "Hi"}]

VALID_SCORES_JSON = (
    '{"scores": {"empathy": {"score": 5, "feedback": "ok"}, '
    '"patient_perspective": {"score": 5, "feedback": "ok"}, '
    '"providing_structure": {"score": 5, "feedback": "ok"}, '
    '"information_gathering": {"score": 5, "feedback": "ok"}, '
    '"information_giving": {"score": 5, "feedback": "ok"}, '
    '"intelligibility": {"score": 5, "feedback": "ok"}, '
    '"fluency": {"score": 5, "feedback": "ok"}, '
    '"appropriateness_of_language": {"score": 5, "feedback": "ok"}, '
    '"grammar": {"score": 5, "feedback": "ok"}}}'
)


def _resp(text, finish_reason="stop"):
    return {"text": text, "finish_reason": finish_reason, "usage": {"input_tokens": 1, "output_tokens": 1}}


def _patch_infra(monkeypatch, cfg, result):
    captured_max_tokens = []

    async def fake_get_model_config(purpose):
        return cfg

    async def fake_dispatch_call(candidate, messages, max_tokens, json_mode, temperature, **kw):
        captured_max_tokens.append(max_tokens)
        return result

    async def fake_log_ai_usage(*a, **kw):
        return None

    monkeypatch.setattr(ai_registry, "get_model_config", fake_get_model_config)
    monkeypatch.setattr(ai_registry, "dispatch_call", fake_dispatch_call)
    monkeypatch.setattr(ai_scoring, "log_ai_usage", fake_log_ai_usage)
    monkeypatch.setattr(ai_scoring, "_log_ai_error", lambda *a, **kw: None)
    monkeypatch.setattr(ai_scoring.circuit_breaker, "allow_request", lambda p: True)
    monkeypatch.setattr(ai_scoring.circuit_breaker, "record_success", lambda p: None)
    monkeypatch.setattr(ai_scoring.circuit_breaker, "record_failure", lambda p: None)
    return captured_max_tokens


def test_speaking_scoring_premium_uses_raised_budget(monkeypatch):
    captured = _patch_infra(monkeypatch, PRIMARY, _resp(VALID_SCORES_JSON))

    _run(ai_scoring.score_speaking(
        NURSE_CARD, HISTORY, purpose="speaking_scoring_premium", criteria_count=9, enhanced_feedback=True,
    ))

    assert captured == [ai_scoring.SPEAKING_SCORING_MAX_TOKENS_PREMIUM]
    assert ai_scoring.SPEAKING_SCORING_MAX_TOKENS_PREMIUM == 5000


def test_speaking_scoring_free_uses_raised_budget(monkeypatch):
    captured = _patch_infra(monkeypatch, PRIMARY, _resp(VALID_SCORES_JSON))

    _run(ai_scoring.score_speaking(
        NURSE_CARD, HISTORY, purpose="speaking_scoring_free", criteria_count=9, enhanced_feedback=False,
    ))

    assert captured == [ai_scoring.SPEAKING_SCORING_MAX_TOKENS_FREE]
    assert ai_scoring.SPEAKING_SCORING_MAX_TOKENS_FREE == 4000


def test_semantic_evidence_uses_raised_budget(monkeypatch):
    captured = _patch_infra(monkeypatch, PRIMARY, _resp('{"revealed": false}'))

    status, data = _run(semantic_evidence._call_semantic_detailed("does the patient reveal X?"))

    assert captured == [semantic_evidence.SEMANTIC_MAX_TOKENS]
    assert semantic_evidence.SEMANTIC_MAX_TOKENS == 500
    assert status == semantic_evidence.STATUS_OK
    assert data["revealed"] is False
