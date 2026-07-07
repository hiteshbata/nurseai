"""
Tests for app.services.realtime.factory -- the VOICE_PROVIDER -> adapter
class lookup. This is deliberately a plain dict lookup (see the module
docstring and the architecture review that confirmed it already serves as
the "registry" a separate ProviderRegistry class would only duplicate).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.realtime.capabilities import capabilities_for
from app.services.realtime.factory import ADAPTER_CLASSES, get_adapter_class
from app.services.realtime.gemini_adapter import GeminiLiveAdapter
from app.services.realtime.openai_adapter import OpenAIRealtimeAdapter


def test_get_adapter_class_openai():
    assert get_adapter_class("openai") is OpenAIRealtimeAdapter


def test_get_adapter_class_gemini():
    assert get_adapter_class("gemini") is GeminiLiveAdapter


def test_get_adapter_class_unknown_provider_raises_with_known_options():
    with pytest.raises(ValueError) as exc_info:
        get_adapter_class("azure")
    message = str(exc_info.value)
    assert "azure" in message
    assert "gemini" in message
    assert "openai" in message


def test_every_registered_adapter_capabilities_matches_capabilities_for():
    # Each adapter's class-level `.capabilities` must be the same object
    # capabilities_for(name) returns -- the router reads them via two
    # different call sites (factory.get_adapter_class + capabilities_for)
    # and both must agree, or the frontend gets one sample rate while the
    # adapter assumes another.
    for name, adapter_class in ADAPTER_CLASSES.items():
        assert adapter_class.capabilities is capabilities_for(name)
