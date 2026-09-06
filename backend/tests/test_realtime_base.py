"""
Tests for the RealtimeProviderAdapter interface contract
(app.services.realtime.base) -- specifically that update_instructions()
(Step 2) is a required part of the interface, same as every other adapter
method, and that both shipped adapters satisfy it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.realtime.base import RealtimeProviderAdapter
from app.services.realtime.gemini_adapter import GeminiLiveAdapter
from app.services.realtime.openai_adapter import OpenAIRealtimeAdapter


def test_openai_and_gemini_adapters_satisfy_the_interface():
    assert issubclass(OpenAIRealtimeAdapter, RealtimeProviderAdapter)
    assert issubclass(GeminiLiveAdapter, RealtimeProviderAdapter)
    OpenAIRealtimeAdapter(system_prompt="x", voice="alloy", api_key="k", model="m")
    GeminiLiveAdapter(system_prompt="x", voice="Kore", api_key="k", model="m")


def test_adapter_missing_update_instructions_cannot_be_instantiated():
    class IncompleteAdapter(RealtimeProviderAdapter):
        async def connect(self): ...
        async def disconnect(self): ...
        async def send_audio(self, pcm16_bytes): ...
        async def cancel_response(self): ...
        def receive_events(self):
            if False:
                yield  # pragma: no cover -- makes this an async generator

    with pytest.raises(TypeError):
        IncompleteAdapter(system_prompt="x", voice="v", api_key="k")
