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
    estimate_azure_pronunciation_cost,
    estimate_realtime_cost,
    estimate_tts_cost,
)


def test_openai_cost_uses_configured_per_minute_rates():
    result = estimate_realtime_cost("openai", input_seconds=60, output_seconds=60)
    expected = settings.OPENAI_REALTIME_USD_PER_MIN_INPUT + settings.OPENAI_REALTIME_USD_PER_MIN_OUTPUT
    assert result.realtime_usd == round(expected, 6)
    assert result.provider == "openai"


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


def test_estimate_tts_cost_premium_costs_more_than_standard():
    standard = estimate_tts_cost(character_count=1_000_000, is_premium_voice=False)
    premium = estimate_tts_cost(character_count=1_000_000, is_premium_voice=True)
    assert premium > standard


def test_estimate_azure_pronunciation_cost_scales_with_duration():
    one_hour = estimate_azure_pronunciation_cost(audio_seconds=3600)
    half_hour = estimate_azure_pronunciation_cost(audio_seconds=1800)
    assert one_hour == round(half_hour * 2, 6)
