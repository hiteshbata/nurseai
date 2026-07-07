"""
Tests for app.services.realtime.capabilities.

The one bug class this module exists to prevent is the frontend capturing
audio at the wrong sample rate for the active provider, so these tests
pin the exact per-provider values rather than just "is truthy."
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.realtime.capabilities import (
    GEMINI_LIVE_CAPABILITIES,
    OPENAI_REALTIME_CAPABILITIES,
    capabilities_for,
)


def test_openai_capabilities_sample_rates():
    caps = capabilities_for("openai")
    assert caps is OPENAI_REALTIME_CAPABILITIES
    assert caps.input_sample_rate == 24000
    assert caps.output_sample_rate == 24000
    assert caps.input_audio_encoding == "pcm16"


def test_gemini_capabilities_sample_rates():
    caps = capabilities_for("gemini")
    assert caps is GEMINI_LIVE_CAPABILITIES
    assert caps.input_sample_rate == 16000
    assert caps.output_sample_rate == 24000


def test_openai_and_gemini_input_rates_differ():
    # Regression guard: the frontend must configure its AudioContext/worklet
    # from session.ready per-provider, never a hardcoded constant. If these
    # ever became equal, a bug that hardcodes one rate would go unnoticed.
    assert OPENAI_REALTIME_CAPABILITIES.input_sample_rate != GEMINI_LIVE_CAPABILITIES.input_sample_rate


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        capabilities_for("azure")


def test_capabilities_are_frozen():
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        OPENAI_REALTIME_CAPABILITIES.input_sample_rate = 8000
