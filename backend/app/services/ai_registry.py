"""AI provider/model registry: purpose -> model lookup with a single-hop
fallback, backing the admin-editable model management panel. See
supabase/migrations/20260807000000_ai_model_registry.sql for the schema.

v1 covers exactly the providers already integrated in this codebase (OpenAI,
Gemini, OpenRouter -- Anthropic is reached only via OpenRouter today, so it
needs no native integration). Any other provider string still dispatches
through the openai_compatible family as long as its ai_models row has an
api_base and an env var named {PROVIDER}_API_KEY exists -- that's the
provider-agnostic extension point, not a promise every provider works
untested.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.supabase import get_supabase
from app.core.threading import run_sync

logger = logging.getLogger(__name__)

PROVIDER_CONFIG: Dict[str, Dict[str, Optional[str]]] = {
    "openai": {"family": "openai_compatible", "base_url": "https://api.openai.com/v1/chat/completions", "key_env": "OPENAI_API_KEY"},
    "openrouter": {"family": "openai_compatible", "base_url": "https://openrouter.ai/api/v1/chat/completions", "key_env": "OPENROUTER_API_KEY"},
    "google": {"family": "gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", "key_env": "GEMINI_API_KEY"},
}


def _api_key_for(provider: str) -> str:
    """Typed settings field for the 3 known providers; falls back to the
    {PROVIDER}_API_KEY env-var convention for anything else, so a new
    OpenAI-wire-compatible provider needs zero code -- just a row + a var."""
    if provider == "openai":
        return settings.OPENAI_API_KEY
    if provider == "openrouter":
        return settings.OPENROUTER_API_KEY
    if provider == "google":
        return settings.GEMINI_API_KEY
    return os.environ.get(f"{provider.upper()}_API_KEY", "")


@dataclass
class ModelConfig:
    id: int
    provider: str
    model_name: str
    api_base: Optional[str]
    fallback: Optional["ModelConfig"] = None

    @property
    def family(self) -> str:
        return PROVIDER_CONFIG.get(self.provider, {}).get("family", "openai_compatible")


class PurposeNotConfigured(Exception):
    """Raised when a purpose has no (enabled) ai_model_purposes mapping --
    an admin needs to set one in the panel, not something to silently guess
    a default for."""


def _row_to_config(row: dict, fallback: Optional[ModelConfig] = None) -> ModelConfig:
    return ModelConfig(
        id=row["id"], provider=row["provider"], model_name=row["model_name"],
        api_base=row.get("api_base"), fallback=fallback,
    )


def _fetch_model_config_sync(purpose: str) -> ModelConfig:
    supabase = get_supabase()
    mapping = supabase.table("ai_model_purposes").select("model_id").eq("purpose", purpose).execute()
    if not mapping.data:
        raise PurposeNotConfigured(f"No model configured for purpose {purpose!r} -- set one in Admin > AI Models.")
    model_id = mapping.data[0]["model_id"]

    primary_rows = supabase.table("ai_models").select("*").eq("id", model_id).execute().data
    if not primary_rows or not primary_rows[0]["enabled"]:
        raise PurposeNotConfigured(f"Model configured for purpose {purpose!r} is missing or disabled.")
    primary_row = primary_rows[0]

    fallback_cfg = None
    if primary_row.get("fallback_model_id"):
        fb_rows = supabase.table("ai_models").select("*").eq("id", primary_row["fallback_model_id"]).execute().data
        if fb_rows and fb_rows[0]["enabled"]:
            fallback_cfg = _row_to_config(fb_rows[0])

    return _row_to_config(primary_row, fallback=fallback_cfg)


_CACHE_TTL_SECONDS = 60
_config_cache: Dict[str, tuple[float, ModelConfig]] = {}


async def get_model_config(purpose: str) -> ModelConfig:
    """DB lookup, cached in-process for 60s -- same TTL pattern as
    speaking_realtime._get_voice_provider, so an admin panel change takes
    effect within a minute without a redeploy or restart."""
    now = time.monotonic()
    cached = _config_cache.get(purpose)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    config = await run_sync(_fetch_model_config_sync, purpose)
    _config_cache[purpose] = (now, config)
    return config


def invalidate_cache(purpose: Optional[str] = None) -> None:
    """Called by the admin API after a write so a purpose reassignment or
    model edit doesn't wait out the 60s TTL."""
    if purpose is None:
        _config_cache.clear()
    else:
        _config_cache.pop(purpose, None)


# ── request dispatch ─────────────────────────────────────────────────

class ModelCallError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


async def _call_gemini(
    cfg: ModelConfig, messages: list, max_tokens: int, json_mode: bool, temperature: float,
    extra_payload: Optional[Dict[str, Any]] = None, timeout: float = 60.0,
) -> Dict[str, Any]:
    api_key = _api_key_for(cfg.provider)
    if not api_key:
        raise ModelCallError(f"No API key configured for provider {cfg.provider!r}")
    # ponytail: text-only -- OpenAI-style multimodal content arrays (image_url/
    # file blocks) and OpenRouter's `extra_payload` plugins aren't translated
    # to Gemini's own multimodal shape. Not needed today: every OCR/vision
    # purpose is seeded as provider=openrouter, never native google. Add
    # translation here if a purpose is ever pointed at a native Gemini model.

    system_parts = []
    contents = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append({"text": msg["content"]})
        elif msg["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": msg["content"]}]})
        else:
            contents.append({"role": "user", "parts": [{"text": msg["content"]}]})

    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    base = cfg.api_base or PROVIDER_CONFIG["google"]["base_url"]
    url = base.format(model=cfg.model_name) + f"?key={api_key}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            raise ModelCallError(f"Gemini API error {response.status_code}: {response.text[:200]}", response.status_code)
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ModelCallError("No candidates in Gemini response")
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        usage_meta = data.get("usageMetadata", {})
        return {
            "text": text,
            "finish_reason": candidates[0].get("finishReason"),
            "usage": {
                "input_tokens": usage_meta.get("promptTokenCount", 0),
                "output_tokens": usage_meta.get("candidatesTokenCount", 0),
            },
        }


async def _call_openai_compatible(
    cfg: ModelConfig, messages: list, max_tokens: int, json_mode: bool, temperature: float,
    extra_payload: Optional[Dict[str, Any]] = None, timeout: float = 60.0,
) -> Dict[str, Any]:
    api_key = _api_key_for(cfg.provider)
    provider_cfg = PROVIDER_CONFIG.get(cfg.provider)
    base_url = cfg.api_base or (provider_cfg["base_url"] if provider_cfg else None)
    if not base_url:
        raise ModelCallError(f"No api_base configured for provider {cfg.provider!r}")
    if not api_key:
        raise ModelCallError(f"No API key configured for provider {cfg.provider!r}")

    payload: Dict[str, Any] = {
        "model": cfg.model_name, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if extra_payload:
        # OpenRouter-specific extras (e.g. the mistral-ocr file-parser
        # plugin) that aren't part of the standard chat-completions shape --
        # passed through untouched, only ever set by OCR/vision call sites.
        payload.update(extra_payload)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(base_url, headers=headers, json=payload)
        if response.status_code != 200:
            raise ModelCallError(f"{cfg.provider} API error {response.status_code}: {response.text[:200]}", response.status_code)
        result = response.json()
        choice = result["choices"][0]
        usage_obj = result.get("usage", {})
        return {
            "text": choice["message"]["content"],
            "finish_reason": choice.get("finish_reason"),
            "usage": {
                "input_tokens": usage_obj.get("prompt_tokens", 0),
                "output_tokens": usage_obj.get("completion_tokens", 0),
            },
        }


_DISPATCH = {"gemini": _call_gemini, "openai_compatible": _call_openai_compatible}


async def dispatch_call(
    cfg: ModelConfig, messages: list, max_tokens: int, json_mode: bool, temperature: float,
    extra_payload: Optional[Dict[str, Any]] = None, timeout: float = 60.0,
) -> Dict[str, Any]:
    """Call `cfg`'s provider via whichever request-shape family it maps to.
    Raises ModelCallError on any failure -- callers (ai_scoring._call_ai,
    the health check below) decide what to do about it."""
    caller = _DISPATCH.get(cfg.family)
    if caller is None:
        raise ModelCallError(f"Provider family {cfg.family!r} is not implemented yet")
    return await caller(cfg, messages, max_tokens, json_mode, temperature, extra_payload=extra_payload, timeout=timeout)


# ── health check ─────────────────────────────────────────────────────

_HEALTHY_LATENCY_MS = 3000

# Providers/purposes that don't speak the chat-completions shape the health
# check pings -- Deepgram (STT), and any purpose that's realtime voice/TTS/
# STT. Testing these via a chat ping always fails even when they work fine
# for real (OpenAI Realtime is a WebSocket API, Google TTS is a synthesis
# endpoint, etc.) -- that false "Failed" is exactly what this guards against.
_NON_CHAT_PROVIDERS = {"deepgram"}
_NON_CHAT_PURPOSE_PREFIXES = ("realtime_voice_", "tts_", "stt_")
_NOT_TESTABLE_RESULT = {
    "status": "not_testable",
    "latency_ms": None,
    "error": "Not a chat-completions model (realtime voice / TTS / STT) -- "
             "verify it via the feature that actually uses it instead.",
}


def classify_health(status_code: int, latency_ms: float, error: Optional[str]) -> tuple[str, Optional[str]]:
    """Pure classification, unit-tested in __main__ below."""
    if error is None:
        return ("warning", None) if latency_ms > _HEALTHY_LATENCY_MS else ("healthy", None)
    if status_code in (401, 403):
        return "failed", "Authentication error"
    if status_code == 404:
        return "failed", "Model not found"
    return "failed", error[:200]


async def run_health_check(provider: str, model_name: str, api_base: Optional[str] = None) -> Dict[str, Any]:
    """Send a 1-message ping through the given provider/model without
    requiring it to already be a saved ai_models row -- backs both the
    saved-row Test button and the create/edit form's Test-Before-Save
    button."""
    if provider in _NON_CHAT_PROVIDERS:
        return dict(_NOT_TESTABLE_RESULT)

    cfg = ModelConfig(id=0, provider=provider, model_name=model_name, api_base=api_base)
    if cfg.family not in _DISPATCH:
        return {"status": "failed", "latency_ms": None, "error": f"Provider family {cfg.family!r} not implemented"}

    start = time.monotonic()
    status_code = 0
    error: Optional[str] = None
    try:
        await dispatch_call(cfg, [{"role": "user", "content": "ping"}], max_tokens=5, json_mode=False, temperature=0.0)
    except ModelCallError as e:
        status_code = e.status_code
        error = str(e)
    except Exception as e:
        error = str(e)[:200]
    latency_ms = round((time.monotonic() - start) * 1000)

    status, message = classify_health(status_code, latency_ms, error)
    return {"status": status, "latency_ms": latency_ms, "error": message}


def _persist_health_sync(model_id: int, result: Dict[str, Any]) -> None:
    get_supabase().table("ai_models").update({
        "last_health_status": result["status"],
        "last_health_latency_ms": result["latency_ms"],
        "last_health_checked_at": datetime.now(timezone.utc).isoformat(),
        "last_health_error": result["error"],
    }).eq("id", model_id).execute()


def _fetch_model_and_purposes_sync(model_id: int) -> tuple[Optional[dict], list[str]]:
    supabase = get_supabase()
    rows = supabase.table("ai_models").select("*").eq("id", model_id).execute().data
    if not rows:
        return None, []
    purposes = supabase.table("ai_model_purposes").select("purpose").eq("model_id", model_id).execute().data
    return rows[0], [p["purpose"] for p in purposes]


async def run_health_check_for_model(model_id: int) -> Dict[str, Any]:
    """Test a saved row and persist the result onto its last_health_* columns.
    Skips the network call entirely (no false "Failed") for a model whose
    only assigned purposes are all realtime/TTS/STT -- there's nothing
    chat-shaped to ping."""
    row, purposes = await run_sync(_fetch_model_and_purposes_sync, model_id)
    if row is None:
        raise ValueError(f"No ai_models row with id={model_id}")

    if purposes and all(p.startswith(_NON_CHAT_PURPOSE_PREFIXES) for p in purposes):
        result = dict(_NOT_TESTABLE_RESULT)
    else:
        result = await run_health_check(row["provider"], row["model_name"], row.get("api_base"))
    await run_sync(_persist_health_sync, model_id, result)
    return result


if __name__ == "__main__":
    # ponytail: smallest runnable check for the pure classification/dispatch
    # logic, not a pytest suite (see ai_pricing.py/ai_cost_metrics.py for the
    # same convention elsewhere in this codebase).
    assert classify_health(0, 500, None) == ("healthy", None)
    assert classify_health(0, 5000, None)[0] == "warning"
    assert classify_health(401, 100, "boom") == ("failed", "Authentication error")
    assert classify_health(404, 100, "boom") == ("failed", "Model not found")
    assert classify_health(500, 100, "server exploded")[0] == "failed"

    cfg = ModelConfig(id=1, provider="google", model_name="gemini-flash-latest", api_base=None)
    assert cfg.family == "gemini"
    cfg2 = ModelConfig(id=2, provider="openrouter", model_name="anthropic/claude-sonnet-5", api_base=None)
    assert cfg2.family == "openai_compatible"
    cfg3 = ModelConfig(id=3, provider="groq", model_name="llama-3", api_base="https://api.groq.com/openai/v1/chat/completions")
    assert cfg3.family == "openai_compatible"  # unknown provider still dispatches via the generic family

    import asyncio
    deepgram_result = asyncio.run(run_health_check("deepgram", "nova-2"))
    assert deepgram_result["status"] == "not_testable"  # never a chat-completions provider, no network call

    print("ai_registry self-check OK")
