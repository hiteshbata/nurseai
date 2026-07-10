"""
validate_session must reject a session_id past CHAT_SESSION_MAX_SECONDS old
(M6 fix) -- otherwise a session, in particular a free user's premium-trial
first session, stays valid forever and can keep re-hitting /chat and /tts
at whatever tier it was granted. No network, no live DB -- a fake
Supabase client stands in for the session_usage lookup.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import sessions as sessions_mod

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return _FakeResult([self._row] if self._row else [])


class _FakeSupabase:
    def __init__(self, row):
        self._row = row

    def table(self, _name):
        return _FakeQuery(self._row)


def _patch(monkeypatch, row, max_seconds=1800):
    monkeypatch.setattr(sessions_mod, "get_supabase", lambda: _FakeSupabase(row))
    monkeypatch.setattr(sessions_mod.settings, "CHAT_SESSION_MAX_SECONDS", max_seconds)
    monkeypatch.setattr(
        sessions_mod, "datetime",
        type("_FrozenDatetime", (), {"now": staticmethod(lambda tz=None: NOW)}),
    )


def test_missing_session_is_invalid(monkeypatch):
    _patch(monkeypatch, row=None)
    assert sessions_mod.validate_session("user-1", 999) is False


def test_fresh_session_is_valid(monkeypatch):
    row = {"id": 1, "created_at": (NOW - timedelta(minutes=5)).isoformat()}
    _patch(monkeypatch, row)
    assert sessions_mod.validate_session("user-1", 1) is True


def test_session_past_max_seconds_is_invalid(monkeypatch):
    row = {"id": 1, "created_at": (NOW - timedelta(seconds=1801)).isoformat()}
    _patch(monkeypatch, row)
    assert sessions_mod.validate_session("user-1", 1) is False


def test_session_at_exact_boundary_is_valid(monkeypatch):
    row = {"id": 1, "created_at": (NOW - timedelta(seconds=1800)).isoformat()}
    _patch(monkeypatch, row)
    assert sessions_mod.validate_session("user-1", 1) is True


def test_legacy_row_with_no_created_at_is_treated_as_valid(monkeypatch):
    row = {"id": 1}
    _patch(monkeypatch, row)
    assert sessions_mod.validate_session("user-1", 1) is True
