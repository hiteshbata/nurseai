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


def test_call_openai_compatible_defaults_to_zero_temperature(monkeypatch):
    captured = []
    _patch_openai_post(monkeypatch, captured)
    _run(ai._call_openai_compatible("openai", [{"role": "user", "content": "hi"}], "key", "gpt-5.4-mini", 100, False))
    assert captured[0]["temperature"] == 0.0


def test_call_gemini_defaults_to_zero_temperature(monkeypatch):
    captured = []
    _patch_gemini_post(monkeypatch, captured)
    _run(ai._call_gemini([{"role": "user", "content": "hi"}], "key", "gemini-2.5-flash", 100, False))
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
