"""
Tests for app.services.realtime.pricing -- the wall-clock-seconds x
blended-$/minute cost estimator (deliberately not exact per-token billing
math, see module docstring).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.realtime.pricing import (
    OPENAI_TOKEN_PRICING,
    accumulate_openai_usage,
    cache_hit_rate,
    estimate_azure_pronunciation_cost,
    estimate_realtime_cost,
    estimate_tts_cost,
    new_usage_totals,
    price_openai_usage,
)


def usage_payload(
    *, input_tokens, output_tokens, cached=0, text_in=0, audio_in=0,
    cached_text=0, cached_audio=0, text_out=0, audio_out=0,
):
    """One response.done `usage` payload, OpenAI GA shape."""
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_token_details": {
            "cached_tokens": cached,
            "text_tokens": text_in,
            "audio_tokens": audio_in,
            "cached_tokens_details": {"text_tokens": cached_text, "audio_tokens": cached_audio},
        },
        "output_token_details": {"text_tokens": text_out, "audio_tokens": audio_out},
    }


def test_openai_cost_uses_configured_per_minute_rates():
    result = estimate_realtime_cost("openai", input_seconds=60, output_seconds=60)
    expected = settings.OPENAI_REALTIME_USD_PER_MIN_INPUT + settings.OPENAI_REALTIME_USD_PER_MIN_OUTPUT
    assert result.realtime_usd == round(expected, 6)
    assert result.provider == "openai"


def test_openai_mini_model_uses_mini_rates():
    result = estimate_realtime_cost(
        "openai", input_seconds=60, output_seconds=60, model=settings.OPENAI_REALTIME_MODEL_MINI
    )
    expected = settings.OPENAI_REALTIME_USD_PER_MIN_INPUT_MINI + settings.OPENAI_REALTIME_USD_PER_MIN_OUTPUT_MINI
    assert result.realtime_usd == round(expected, 6)


def test_openai_flagship_model_costs_more_than_mini():
    flagship = estimate_realtime_cost("openai", input_seconds=60, output_seconds=60, model="gpt-realtime")
    mini = estimate_realtime_cost(
        "openai", input_seconds=60, output_seconds=60, model=settings.OPENAI_REALTIME_MODEL_MINI
    )
    assert flagship.realtime_usd > mini.realtime_usd


def test_gemini_cost_uses_configured_per_minute_rates():
    result = estimate_realtime_cost("gemini", input_seconds=120, output_seconds=0)
    expected = 2 * settings.GEMINI_LIVE_USD_PER_MIN_INPUT
    assert result.realtime_usd == round(expected, 6)


def test_zero_duration_is_zero_cost():
    result = estimate_realtime_cost("openai", input_seconds=0, output_seconds=0)
    assert result.realtime_usd == 0.0


def test_unknown_provider_costs_nothing_rather_than_raising():
    # Metrics persistence must never fail a live session over an unrecognized
    # provider string -- see app.routers.speaking_realtime._persist_realtime_metrics,
    # which calls this unconditionally in a best-effort path.
    result = estimate_realtime_cost("some-future-provider", input_seconds=100, output_seconds=100)
    assert result.realtime_usd == 0.0


def test_openai_output_costs_more_per_minute_than_input():
    # Sanity check on the configured constants themselves -- realtime voice
    # output (synthesis) is consistently pricier than input across providers.
    assert settings.OPENAI_REALTIME_USD_PER_MIN_OUTPUT > settings.OPENAI_REALTIME_USD_PER_MIN_INPUT


# ── metered token pricing ─────────────────────────────────────────────

def test_accumulate_sums_across_responses():
    totals = new_usage_totals()
    accumulate_openai_usage(totals, usage_payload(
        input_tokens=100, output_tokens=50, cached=0, audio_in=100, audio_out=50,
    ))
    accumulate_openai_usage(totals, usage_payload(
        input_tokens=300, output_tokens=50, cached=100, audio_in=300,
        cached_audio=100, audio_out=50,
    ))
    assert totals["input_tokens"] == 400
    assert totals["output_tokens"] == 100
    assert totals["cached_tokens"] == 100
    assert totals["audio_input_tokens"] == 400
    assert totals["responses"] == 2


def test_accumulate_tolerates_missing_fields():
    # Raw provider JSON -- a renamed/absent field must not crash teardown.
    totals = new_usage_totals()
    accumulate_openai_usage(totals, {"input_tokens": 10})
    assert totals["input_tokens"] == 10
    assert totals["cached_tokens"] == 0
    assert totals["responses"] == 1


def test_price_uses_cached_rate_for_cached_portion():
    rates = OPENAI_TOKEN_PRICING["gpt-realtime"]
    totals = new_usage_totals()
    accumulate_openai_usage(totals, usage_payload(
        input_tokens=1_000_000, output_tokens=0,
        cached=800_000, audio_in=1_000_000, cached_audio=800_000,
    ))
    expected = (200_000 * rates["audio_input"] + 800_000 * rates["audio_input_cached"]) / 1_000_000
    assert price_openai_usage("gpt-realtime", totals) == round(expected, 6)


def test_caching_is_cheaper_than_no_caching_for_same_token_count():
    cached_totals = new_usage_totals()
    accumulate_openai_usage(cached_totals, usage_payload(
        input_tokens=100_000, output_tokens=0, cached=90_000,
        audio_in=100_000, cached_audio=90_000,
    ))
    uncached_totals = new_usage_totals()
    accumulate_openai_usage(uncached_totals, usage_payload(
        input_tokens=100_000, output_tokens=0, audio_in=100_000,
    ))
    assert price_openai_usage("gpt-realtime", cached_totals) < price_openai_usage("gpt-realtime", uncached_totals)


def test_price_returns_none_for_unknown_model_so_caller_falls_back():
    totals = new_usage_totals()
    accumulate_openai_usage(totals, usage_payload(input_tokens=100, output_tokens=10))
    assert price_openai_usage("gemini-live-something", totals) is None


def test_price_returns_none_when_no_response_reported_usage():
    # Connection dropped before any turn completed -- must fall back to the
    # wall-clock estimate, not report a confident $0.00.
    assert price_openai_usage("gpt-realtime", new_usage_totals()) is None


def test_price_never_credits_when_cached_exceeds_total():
    totals = new_usage_totals()
    accumulate_openai_usage(totals, usage_payload(
        input_tokens=100, output_tokens=0, cached=500, audio_in=100, cached_audio=500,
    ))
    assert price_openai_usage("gpt-realtime", totals) >= 0


def test_mini_is_cheaper_than_flagship_on_identical_tokens():
    totals = new_usage_totals()
    accumulate_openai_usage(totals, usage_payload(
        input_tokens=10_000, output_tokens=5_000, audio_in=10_000, audio_out=5_000,
    ))
    assert price_openai_usage("gpt-realtime-mini", totals) < price_openai_usage("gpt-realtime", totals)


def test_cache_hit_rate_reports_cached_share_of_input():
    totals = new_usage_totals()
    accumulate_openai_usage(totals, usage_payload(input_tokens=1000, output_tokens=0, cached=800))
    assert cache_hit_rate(totals) == 0.8


def test_cache_hit_rate_is_none_when_nothing_metered():
    assert cache_hit_rate(new_usage_totals()) is None


def test_estimate_tts_cost_premium_costs_more_than_standard():
    standard = estimate_tts_cost(character_count=1_000_000, is_premium_voice=False)
    premium = estimate_tts_cost(character_count=1_000_000, is_premium_voice=True)
    assert premium > standard


def test_estimate_azure_pronunciation_cost_scales_with_duration():
    one_hour = estimate_azure_pronunciation_cost(audio_seconds=3600)
    half_hour = estimate_azure_pronunciation_cost(audio_seconds=1800)
    assert one_hour == round(half_hour * 2, 6)
