"""
Regression tests for the P0 QA bug: POST /speaking/chat could raise an
unhandled exception when the AI provider was unconfigured or its call path
threw unexpectedly, producing a raw 500 with no CORS headers (browsers
report that as a network/CORS failure). Covers:

  - _call_ai never raising for a config-lookup failure (expected or not)
  - get_patient_response surfacing provider_failure instead of faking a reply
  - chat_with_patient converting both into a safe, structured 503
  - the global exception handler keeping CORS headers on a genuinely
    unhandled exception, without leaking exception internals

Same style as test_speaking_realtime_router.py: functions called directly
with fakes, no live DB. The CORS check uses a throwaway FastAPI app wired
with the same CORSMiddleware + exception handler as app.main, so it doesn't
need Supabase/lifespan to construct the real app.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

import app.services.ai_scoring as ai_scoring
import app.routers.speaking as speaking_module
from app.services import ai_registry
from app.routers.auth import UserInfo
from app.routers.speaking import PatientChatRequest


def _run(coro):
    return asyncio.run(coro)


CARD = {"patient_name": "Mary", "instructions_for_ai": "Be anxious.", "condition": "chest pain"}


# ── _call_ai: provider-unavailable / unexpected-exception paths ──────────

def test_call_ai_purpose_not_configured_returns_safe_result_no_raise(monkeypatch):
    async def raise_not_configured(purpose):
        raise ai_registry.PurposeNotConfigured("no model for purpose")

    monkeypatch.setattr(ai_registry, "get_model_config", raise_not_configured)

    result = _run(ai_scoring._call_ai([{"role": "user", "content": "hi"}], purpose="patient_roleplay"))

    assert result["provider_failure"] is True
    assert "unavailable" in result["raw_feedback"].lower()


def test_call_ai_unexpected_config_lookup_exception_returns_safe_result_no_raise(monkeypatch):
    """The bug: get_model_config can fail with something other than
    PurposeNotConfigured (DB/network blip) -- that must not escape _call_ai
    as a raw exception."""
    async def raise_unexpected(purpose):
        raise ConnectionError("could not reach postgrest: password=hunter2")

    monkeypatch.setattr(ai_registry, "get_model_config", raise_unexpected)

    result = _run(ai_scoring._call_ai([{"role": "user", "content": "hi"}], purpose="patient_roleplay"))

    assert result["provider_failure"] is True
    assert "hunter2" not in result["raw_feedback"]
    assert "ConnectionError" not in result["raw_feedback"]


def test_call_ai_success_path_unchanged(monkeypatch):
    class FakeCfg:
        provider = "openrouter"
        model_name = "test-model"
        fallback = None

    async def fake_get_model_config(purpose):
        return FakeCfg()

    async def fake_dispatch_call(candidate, messages, max_tokens, json_mode, temperature, **kw):
        return {"text": "a real reply", "finish_reason": "stop", "usage": {"input_tokens": 1, "output_tokens": 1}}

    async def fake_log_ai_usage(*a, **kw):
        return None

    monkeypatch.setattr(ai_registry, "get_model_config", fake_get_model_config)
    monkeypatch.setattr(ai_registry, "dispatch_call", fake_dispatch_call)
    monkeypatch.setattr(ai_scoring, "log_ai_usage", fake_log_ai_usage)
    monkeypatch.setattr(ai_scoring.circuit_breaker, "allow_request", lambda p: True)
    monkeypatch.setattr(ai_scoring.circuit_breaker, "record_success", lambda p: None)

    result = _run(ai_scoring._call_ai([{"role": "user", "content": "hi"}], purpose="patient_roleplay"))

    assert result.get("provider_failure", False) is False
    assert result["raw_feedback"] == "a real reply"


# ── get_patient_response: surfaces provider_failure instead of faking it ─

def test_get_patient_response_surfaces_provider_failure(monkeypatch):
    async def fake_call_ai(*a, **kw):
        return {"raw_feedback": "unavailable text", "provider_failure": True}

    monkeypatch.setattr(ai_scoring, "_call_ai", fake_call_ai)

    reply, provider_failure = _run(ai_scoring.get_patient_response(CARD, [], "How are you?"))

    assert provider_failure is True
    assert reply == "unavailable text"


def test_get_patient_response_success_path_unchanged(monkeypatch):
    async def fake_call_ai(*a, **kw):
        return {"raw_feedback": "I feel a bit anxious, nurse.", "provider_failure": False}

    monkeypatch.setattr(ai_scoring, "_call_ai", fake_call_ai)

    reply, provider_failure = _run(ai_scoring.get_patient_response(CARD, [], "How are you?"))

    assert provider_failure is False
    assert reply == "I feel a bit anxious, nurse."


# ── chat_with_patient: converts AI failures into a safe structured 503 ───

DEFAULT_SCENARIO = {"id": 42, "is_active": True, "interlocutor_card": CARD}


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeScenarioSupabase:
    def table(self, name):
        assert name == "scenarios"
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        return FakeResult([dict(DEFAULT_SCENARIO)])


def _patch_route(monkeypatch, provider_failure=False, raises=None):
    monkeypatch.setattr(speaking_module, "get_supabase", lambda: FakeScenarioSupabase())
    monkeypatch.setattr(speaking_module, "validate_session", lambda user_id, session_id: session_id is not None)

    def fake_check_and_increment_session(current_user, user_db):
        return {"session_id": 99, "spent_bonus": False, "sessions_used": 1, "sessions_remaining": 2}

    released = []

    def fake_release(user_id, session_id, spent_bonus):
        released.append((user_id, session_id, spent_bonus))

    async def fake_get_patient_response(**kwargs):
        if raises is not None:
            raise raises
        return ("Hello nurse.", provider_failure)

    monkeypatch.setattr(speaking_module, "check_and_increment_session", fake_check_and_increment_session)
    monkeypatch.setattr(speaking_module, "release_session_charge", fake_release)
    monkeypatch.setattr(speaking_module, "get_patient_response", fake_get_patient_response)
    return released


def _make_request():
    return PatientChatRequest(scenario_id=42, message="How are you?", history=[], session_id=None)


def test_expected_provider_failure_returns_503_not_500(monkeypatch):
    released = _patch_route(monkeypatch, provider_failure=True)

    with pytest.raises(HTTPException) as exc_info:
        _run(speaking_module.chat_with_patient(
            request=_make_request(),
            current_user=UserInfo(id="user-1", email="n@example.com"),
            user_db=object(),
        ))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "ai_unavailable"
    assert released == [("user-1", 99, False)]


def test_unexpected_exception_converted_to_safe_503(monkeypatch):
    released = _patch_route(monkeypatch, raises=RuntimeError("provider api_key=sk-super-secret-123 rejected"))

    with pytest.raises(HTTPException) as exc_info:
        _run(speaking_module.chat_with_patient(
            request=_make_request(),
            current_user=UserInfo(id="user-1", email="n@example.com"),
            user_db=object(),
        ))

    assert exc_info.value.status_code == 503
    detail_text = str(exc_info.value.detail)
    assert "sk-super-secret-123" not in detail_text
    assert "RuntimeError" not in detail_text
    assert released == [("user-1", 99, False)]


def test_successful_ai_path_unchanged(monkeypatch):
    released = _patch_route(monkeypatch, provider_failure=False)

    response = _run(speaking_module.chat_with_patient(
        request=_make_request(),
        current_user=UserInfo(id="user-1", email="n@example.com"),
        user_db=object(),
    ))

    assert response.patient_reply == "Hello nurse."
    assert response.session_id == 99
    assert released == []


# ── CORS must survive a genuinely unhandled exception (global handler) ───

def test_unhandled_exception_keeps_cors_headers_and_hides_details():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.testclient import TestClient
    from app.main import UnhandledExceptionMiddleware

    test_app = FastAPI()
    # Registration order matters: UnhandledExceptionMiddleware must be added
    # before CORSMiddleware so it ends up inside it (see app.main for why).
    test_app.add_middleware(UnhandledExceptionMiddleware)
    test_app.add_middleware(
        CORSMiddleware, allow_origins=["https://qa.example.test"],
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )

    @test_app.get("/boom")
    def boom():
        raise RuntimeError("db password=hunter2 leaked-if-this-appears")

    client = TestClient(test_app, raise_server_exceptions=False)
    resp = client.get("/boom", headers={"Origin": "https://qa.example.test"})

    assert resp.status_code == 500
    assert resp.headers.get("access-control-allow-origin") == "https://qa.example.test"
    assert "hunter2" not in resp.text
    assert "RuntimeError" not in resp.text
    body = resp.json()
    assert body["error"] == "internal_server_error"
    assert "request_id" in body


def test_successful_request_unaffected_by_global_handler():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.testclient import TestClient
    from app.main import UnhandledExceptionMiddleware

    test_app = FastAPI()
    test_app.add_middleware(UnhandledExceptionMiddleware)
    test_app.add_middleware(
        CORSMiddleware, allow_origins=["https://qa.example.test"],
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )

    @test_app.get("/ok")
    def ok():
        return {"status": "ok"}

    client = TestClient(test_app)
    resp = client.get("/ok", headers={"Origin": "https://qa.example.test"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers.get("access-control-allow-origin") == "https://qa.example.test"
