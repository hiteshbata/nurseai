"""
Cost estimation for realtime voice sessions.

These are estimates for internal cost dashboards and the OpenAI-vs-Gemini
comparison view, NOT invoices -- both providers meter usage in audio tokens
per fixed time slice (OpenAI: 1 input token/100ms, 1 output token/50ms;
Gemini: ~25 tokens/sec for both directions) and bill those tokens at
different per-million rates that change over time. Modeling the exact
token-boundary math would still only be as accurate as the $/token constant
underneath it, so this module instead works off wall-clock seconds of
audio actually sent/received, multiplied by a blended $/minute constant
from app.core.config -- good enough to compare providers against each
other and to catch a cost regression, not good enough to reconcile against
a provider invoice line-by-line.

Update the *_USD_PER_MIN_* settings whenever you check current pricing at:
  https://ai.google.dev/gemini-api/docs/pricing  (Gemini Live)
  https://developers.openai.com/api/docs/pricing (OpenAI Realtime)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings

# Google Cloud TTS, $/1M characters -- Standard/WaveNet vs Chirp3-HD tiers.
# Verify at https://cloud.google.com/text-to-speech/pricing.
GOOGLE_TTS_USD_PER_MILLION_CHARS_STANDARD = 4.0
GOOGLE_TTS_USD_PER_MILLION_CHARS_PREMIUM = 30.0

# Azure Speech pronunciation assessment bills as standard speech-to-text,
# $/audio-hour. Verify at https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/.
AZURE_PRONUNCIATION_USD_PER_AUDIO_HOUR = 1.0


# --- Exact token pricing (OpenAI Realtime only) ---------------------------
# $ per 1M tokens, per model. Cached input is the whole reason realtime is
# affordable: every response re-sends the entire conversation as input, and
# OpenAI automatically bills the repeated prefix at the cached rate (~99%
# off audio). Text and audio are metered separately in both directions.
#
# These go stale. Verify at https://developers.openai.com/api/docs/pricing.
# A model missing from this table falls back to wall-clock estimation
# (estimate_realtime_cost) rather than mispricing against the wrong row.
OPENAI_TOKEN_PRICING: dict[str, dict[str, float]] = {
    "gpt-realtime": {
        "text_input": 4.0,
        "text_input_cached": 0.40,
        "text_output": 16.0,
        "audio_input": 32.0,
        "audio_input_cached": 0.40,
        "audio_output": 64.0,
    },
    "gpt-realtime-mini": {
        "text_input": 0.60,
        "text_input_cached": 0.06,
        "text_output": 2.40,
        "audio_input": 10.0,
        "audio_input_cached": 0.30,
        "audio_output": 20.0,
    },
}


@dataclass(frozen=True, slots=True)
class RealtimeCostEstimate:
    provider: str
    input_seconds: float
    output_seconds: float
    realtime_usd: float


def estimate_realtime_cost(
    provider: str, input_seconds: float, output_seconds: float, model: str | None = None
) -> RealtimeCostEstimate:
    if provider == "openai":
        if model == settings.OPENAI_REALTIME_MODEL_MINI:
            per_min_in = settings.OPENAI_REALTIME_USD_PER_MIN_INPUT_MINI
            per_min_out = settings.OPENAI_REALTIME_USD_PER_MIN_OUTPUT_MINI
        else:
            per_min_in = settings.OPENAI_REALTIME_USD_PER_MIN_INPUT
            per_min_out = settings.OPENAI_REALTIME_USD_PER_MIN_OUTPUT
    elif provider == "gemini":
        per_min_in = settings.GEMINI_LIVE_USD_PER_MIN_INPUT
        per_min_out = settings.GEMINI_LIVE_USD_PER_MIN_OUTPUT
    else:
        per_min_in = per_min_out = 0.0

    cost = (input_seconds / 60.0) * per_min_in + (output_seconds / 60.0) * per_min_out
    return RealtimeCostEstimate(
        provider=provider,
        input_seconds=input_seconds,
        output_seconds=output_seconds,
        realtime_usd=round(cost, 6),
    )


def accumulate_openai_usage(totals: dict[str, int], usage: dict) -> None:
    """Fold one response.done `usage` payload into a running per-session
    total, in place. Everything is read defensively with .get() -- this is
    raw provider JSON, and a missing/renamed field must degrade to 0 rather
    than blow up a live session's teardown path.

    Cached tokens are a SUBSET of input tokens, not an addition to them, so
    the uncached portion is (total - cached) per modality -- see
    price_openai_usage below, which is the only consumer of these keys."""
    input_details = usage.get("input_token_details") or {}
    output_details = usage.get("output_token_details") or {}
    cached_details = input_details.get("cached_tokens_details") or {}

    totals["input_tokens"] += usage.get("input_tokens") or 0
    totals["output_tokens"] += usage.get("output_tokens") or 0
    totals["cached_tokens"] += input_details.get("cached_tokens") or 0
    totals["text_input_tokens"] += input_details.get("text_tokens") or 0
    totals["audio_input_tokens"] += input_details.get("audio_tokens") or 0
    totals["cached_text_tokens"] += cached_details.get("text_tokens") or 0
    totals["cached_audio_tokens"] += cached_details.get("audio_tokens") or 0
    totals["text_output_tokens"] += output_details.get("text_tokens") or 0
    totals["audio_output_tokens"] += output_details.get("audio_tokens") or 0
    totals["responses"] += 1


def new_usage_totals() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "text_input_tokens": 0,
        "audio_input_tokens": 0,
        "cached_text_tokens": 0,
        "cached_audio_tokens": 0,
        "text_output_tokens": 0,
        "audio_output_tokens": 0,
        "responses": 0,
    }


def price_openai_usage(model: str, totals: dict[str, int]) -> float | None:
    """Exact cost from metered tokens. Returns None when the model isn't in
    OPENAI_TOKEN_PRICING or no response ever reported usage -- the caller
    falls back to estimate_realtime_cost() in that case rather than
    reporting a confidently wrong $0.00."""
    rates = OPENAI_TOKEN_PRICING.get(model)
    if rates is None or not totals.get("responses"):
        return None

    # max(0, ...) guards the (shouldn't-happen) case of a provider reporting
    # more cached tokens than total tokens for a modality; a negative
    # billable count would silently credit the session.
    uncached_text_in = max(0, totals["text_input_tokens"] - totals["cached_text_tokens"])
    uncached_audio_in = max(0, totals["audio_input_tokens"] - totals["cached_audio_tokens"])

    cost = (
        uncached_text_in * rates["text_input"]
        + totals["cached_text_tokens"] * rates["text_input_cached"]
        + uncached_audio_in * rates["audio_input"]
        + totals["cached_audio_tokens"] * rates["audio_input_cached"]
        + totals["text_output_tokens"] * rates["text_output"]
        + totals["audio_output_tokens"] * rates["audio_output"]
    ) / 1_000_000.0
    return round(cost, 6)


def cache_hit_rate(totals: dict[str, int]) -> float | None:
    """Share of input tokens served from cache, 0.0-1.0. None when nothing
    was metered. This is the number that says whether the prompt prefix is
    actually staying stable across turns."""
    input_tokens = totals.get("input_tokens") or 0
    if not input_tokens:
        return None
    return round((totals.get("cached_tokens") or 0) / input_tokens, 4)


def estimate_tts_cost(character_count: int, is_premium_voice: bool) -> float:
    rate = GOOGLE_TTS_USD_PER_MILLION_CHARS_PREMIUM if is_premium_voice else GOOGLE_TTS_USD_PER_MILLION_CHARS_STANDARD
    return round((character_count / 1_000_000.0) * rate, 6)


def estimate_azure_pronunciation_cost(audio_seconds: float) -> float:
    return round((audio_seconds / 3600.0) * AZURE_PRONUNCIATION_USD_PER_AUDIO_HOUR, 6)
