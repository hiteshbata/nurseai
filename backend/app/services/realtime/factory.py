"""
Provider registry. This is the only place that maps the VOICE_PROVIDER
config string to a concrete adapter class -- adding a third provider later
means adding one entry here (and implementing the adapter), nothing else in
the router changes.
"""
from __future__ import annotations

from app.services.realtime.base import RealtimeProviderAdapter
from app.services.realtime.gemini_adapter import GeminiLiveAdapter
from app.services.realtime.openai_adapter import OpenAIRealtimeAdapter

ADAPTER_CLASSES: dict[str, type[RealtimeProviderAdapter]] = {
    "openai": OpenAIRealtimeAdapter,
    "gemini": GeminiLiveAdapter,
}


def get_adapter_class(provider: str) -> type[RealtimeProviderAdapter]:
    try:
        return ADAPTER_CLASSES[provider]
    except KeyError:
        raise ValueError(
            f"Unknown VOICE_PROVIDER: {provider!r} (expected one of {sorted(ADAPTER_CLASSES)})"
        )
