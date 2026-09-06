"""Concurrency + model-fallback behavior for writing OCR page reads.

Guards the gather refactor: pages must come back in input order (not finish
order), a failed primary model must fall back to the next, and an all-fail page
must raise HTTPException naming which photo to re-take.

_read_ocr_page now goes through the purpose-driven ai_scoring._call_ai (see
commit 4215b64b) instead of calling per-provider functions directly, so the
model pair for "writing_ocr" comes from ai_registry.get_model_config (an
Admin > AI Models DB row) rather than being hardcoded here. Without faking
that lookup, this test either depends on whatever the live/dev DB happens to
have configured for that purpose, or -- when no API key is present for
whatever it finds -- fails via a real (or live-502) provider call instead of
exercising the FakeClient below at all. We fake get_model_config with the
same primary/fallback pair (OpenRouter-routed anthropic sonnet -> OpenRouter-
routed google gemini) the real DB currently uses, so the marker-based
FakeClient logic keeps testing genuine dispatch/fallback behavior."""
import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.routers import writing
from app.services import ai_registry, ai_scoring


class _FakeResp:
    def __init__(self, status_code, content=""):
        self.status_code = status_code
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeClient:
    """Routes on (model, image marker) so each test scripts per-page outcomes.
    Accepts/ignores the timeout kwarg the real AsyncClient takes."""

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, url, headers=None, json=None):
        model = json["model"]
        url = json["messages"][0]["content"][1]["image_url"]["url"]
        marker = url.replace("data:image/jpeg;base64,", "")
        if "SLOW" in marker:
            await asyncio.sleep(0.05)  # finishes last, must still land first in order
        if "BAD" in marker:
            return _FakeResp(500)
        if "FALLBACK" in marker and "sonnet" in model:
            return _FakeResp(500)  # force fallback to the second model
        provider = model.split("/")[0]
        return _FakeResp(200, f"text::{marker}::{provider}")


_WRITING_OCR_CFG = ai_registry.ModelConfig(
    id=1, provider="openrouter", model_name="anthropic/claude-sonnet-5", api_base=None,
    fallback=ai_registry.ModelConfig(id=2, provider="openrouter", model_name="google/gemini-flash-latest", api_base=None),
)


async def _fake_get_model_config(_purpose):
    return _WRITING_OCR_CFG


def _patch(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(ai_registry, "get_model_config", _fake_get_model_config)
    monkeypatch.setattr(ai_scoring.settings, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_scoring.circuit_breaker, "allow_request", lambda provider: True)
    monkeypatch.setattr(ai_scoring.circuit_breaker, "record_success", lambda provider: None)
    monkeypatch.setattr(ai_scoring.circuit_breaker, "record_failure", lambda provider: None)


def test_pages_returned_in_input_order(monkeypatch):
    _patch(monkeypatch)
    # page 0 sleeps longest; gather must still return it first
    out = asyncio.run(writing._ocr_images(["SLOW-GOOD-A", "GOOD-B"]))
    assert out == "text::SLOW-GOOD-A::anthropic\n\ntext::GOOD-B::anthropic"


def test_falls_back_to_second_model(monkeypatch):
    _patch(monkeypatch)
    out = asyncio.run(writing._ocr_images(["FALLBACK-1"]))
    assert out == "text::FALLBACK-1::google"  # gemini, after sonnet 500'd


def test_all_models_fail_names_the_page(monkeypatch):
    _patch(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(writing._ocr_images(["GOOD-1", "BAD-2"]))
    assert exc.value.status_code == 502
    assert "page 2" in exc.value.detail
