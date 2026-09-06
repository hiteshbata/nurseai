"""
Tests for app.services.realtime.events -- the canonical event types shared
by every provider adapter.

Mostly a regression guard: confirms the event union only contains types
that adapters/router actually use (SessionEnded/UsageUpdate were removed as
dead code -- never constructed by either adapter nor handled by the
router -- see the architecture review that prompted this cleanup) and that
the dataclasses keep the properties the router relies on (frozen, correct
defaults).
"""
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import get_args

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.realtime import events


def test_realtime_event_union_has_no_dead_types():
    members = {t.__name__ for t in get_args(events.RealtimeEvent)}
    assert members == {
        "SessionReady",
        "TranscriptDelta",
        "TranscriptFinal",
        "ResponseDone",
        "SpeechStopped",
        "ResponseCreated",
        "InstructionsAcked",
        "Interrupted",
        "ProviderError",
    }


def test_removed_event_types_are_actually_gone():
    assert not hasattr(events, "SessionEnded")
    assert not hasattr(events, "UsageUpdate")


def test_events_are_frozen():
    delta = events.TranscriptDelta(role="patient", delta="hi")
    with pytest.raises(FrozenInstanceError):
        delta.delta = "changed"


def test_provider_error_defaults():
    err = events.ProviderError(message="boom")
    assert err.code is None
    assert err.recoverable is False


def test_provider_error_equality_by_value():
    assert events.ProviderError(message="x", recoverable=True) == events.ProviderError(message="x", recoverable=True)
