"""
Verifies scoring/grading/explanation calls default to temperature 0.0
(deterministic), while the patient-persona roleplay call explicitly keeps
0.3 (see item 31 in Final Checklist.md -- non-deterministic scores confuse
students). No real network -- httpx.AsyncClient.post is faked.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.services import ai_scoring as ai


def _run(coro):
    return asyncio.run(coro)


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = "{}"

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def _patch_openai_post(monkeypatch, captured):
    async def fake_post(self, url, headers=None, json=None):
        captured.append(json)
        return FakeResponse({
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def _patch_gemini_post(monkeypatch, captured):
    async def fake_post(self, url, json=None):
        captured.append(json)
        return FakeResponse({
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


async def _fake_log_ai_usage(*_a, **_kw):
    return None


def test_call_ai_openai_path_defaults_to_zero_temperature(monkeypatch):
    # _call_openai_compatible/_call_gemini were collapsed into _call_ai
    # (ai_scoring._call_ai -> ai_registry.dispatch_call -> the real,
    # unmocked provider function) -- so the provider/model is now decided
    # by ai_registry.get_model_config(purpose), which we fake here to force
    # the openai_compatible path instead of patching a function that no
    # longer exists on ai_scoring.
    captured = []
    _patch_openai_post(monkeypatch, captured)
    cfg = ai.ai_registry.ModelConfig(id=1, provider="openai", model_name="gpt-5.4-mini", api_base=None)

    async def fake_get_model_config(purpose):
        return cfg

    monkeypatch.setattr(ai.ai_registry, "get_model_config", fake_get_model_config)
    monkeypatch.setattr(ai.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(ai.circuit_breaker, "allow_request", lambda prov: True)
    monkeypatch.setattr(ai.circuit_breaker, "record_success", lambda prov: None)
    monkeypatch.setattr(ai, "log_ai_usage", _fake_log_ai_usage)

    _run(ai._call_ai([{"role": "user", "content": "hi"}], purpose="scoring"))
    assert captured[0]["temperature"] == 0.0


def test_call_ai_gemini_path_defaults_to_zero_temperature(monkeypatch):
    captured = []
    _patch_gemini_post(monkeypatch, captured)
    cfg = ai.ai_registry.ModelConfig(id=2, provider="google", model_name="gemini-2.5-flash", api_base=None)

    async def fake_get_model_config(purpose):
        return cfg

    monkeypatch.setattr(ai.ai_registry, "get_model_config", fake_get_model_config)
    monkeypatch.setattr(ai.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai.circuit_breaker, "allow_request", lambda prov: True)
    monkeypatch.setattr(ai.circuit_breaker, "record_success", lambda prov: None)
    monkeypatch.setattr(ai, "log_ai_usage", _fake_log_ai_usage)

    _run(ai._call_ai([{"role": "user", "content": "hi"}], purpose="scoring"))
    assert captured[0]["generationConfig"]["temperature"] == 0.0


def test_get_patient_response_uses_temperature_point_three(monkeypatch):
    captured = []
    _patch_gemini_post(monkeypatch, captured)
    monkeypatch.setattr(ai.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai.settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(ai.circuit_breaker, "allow_request", lambda prov: True)
    monkeypatch.setattr(ai.circuit_breaker, "record_success", lambda prov: None)

    async def fake_log_ai_usage(*a, **kw):
        return None

    monkeypatch.setattr(ai, "log_ai_usage", fake_log_ai_usage)

    card = {"patient_name": "John", "instructions_for_ai": "Be anxious."}
    _run(ai.get_patient_response(card, [], "How are you feeling?"))

    assert captured[0]["generationConfig"]["temperature"] == 0.3
