"""
Tests for app.services.session_semantic_state (Step 13: persisted Semantic
Verification State).

No network, no live DB -- a fake Supabase client stands in for
session_semantic_state table access, matching this repo's existing style
(see test_sessions_validate.py). Driven via asyncio.run() (no pytest-asyncio
dependency), matching test_speaking_realtime_router.py.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.session_semantic_state as sss
from app.services.patient_state import SemanticHints

GOLDEN_ITEM = "childhood trauma involving uncle and injections"


def _run(coro):
    return asyncio.run(coro)


def _golden_hints() -> SemanticHints:
    """Step 20's exact scenario: turn 5 a false-positive candidate (verified
    NOT revealed), turn 11 the genuine disclosure (verified revealed)."""
    return SemanticHints(
        confirmed_hidden_reveals=frozenset({GOLDEN_ITEM}),
        verification_status={GOLDEN_ITEM: "verified_revealed"},
        candidate_turn_status={GOLDEN_ITEM: {5: "verified_not_revealed", 11: "verified_revealed"}},
        confirmed_reveal_turn={GOLDEN_ITEM: 11},
    )


# ── Fakes ───────────────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, store, raise_on=None):
        self.store = store
        self.raise_on = raise_on or set()
        self._op = None
        self._payload = None
        self._filters = {}

    def select(self, *_a, **_k):
        self._op = self._op or "select"
        return self

    def upsert(self, row, **_k):
        self._op = "upsert"
        self._payload = row
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, key, value):
        self._filters[key] = value
        return self

    def lt(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        if self._op in self.raise_on:
            raise RuntimeError(f"simulated {self._op} failure")
        if self._op == "upsert":
            self.store[self._payload["session_usage_id"]] = dict(self._payload)
            return _FakeResult([self._payload])
        if self._op == "select":
            sid = self._filters.get("session_usage_id")
            row = self.store.get(sid)
            return _FakeResult([row] if row else [])
        return _FakeResult([])


class _FakeSupabase:
    def __init__(self, store, raise_on=None):
        self.store = store
        self.raise_on = raise_on or set()

    def table(self, _name):
        return _FakeQuery(self.store, raise_on=self.raise_on)


def _patch(monkeypatch, store=None, raise_on=None):
    store = store if store is not None else {}
    monkeypatch.setattr(sss, "get_supabase", lambda: _FakeSupabase(store, raise_on=raise_on))
    return store


# ── Serialization roundtrip (Step 21) ────────────────────────────────────

def test_roundtrip_preserves_golden_case():
    hints = _golden_hints()
    stored = sss._to_storage(hints)
    restored = sss._from_storage(stored)
    assert restored == hints
    assert restored.candidate_turn_status[GOLDEN_ITEM][5] == "verified_not_revealed"
    assert restored.candidate_turn_status[GOLDEN_ITEM][11] == "verified_revealed"
    assert restored.confirmed_reveal_turn[GOLDEN_ITEM] == 11
    assert GOLDEN_ITEM in restored.confirmed_hidden_reveals


def test_roundtrip_through_actual_json():
    import json
    hints = _golden_hints()
    as_json = json.dumps(sss._to_storage(hints))
    restored = sss._from_storage(json.loads(as_json))
    assert restored == hints


# ── Save / load (Step 22, golden case Step 20) ───────────────────────────

def test_save_then_load_roundtrip(monkeypatch):
    store = _patch(monkeypatch)
    hints = _golden_hints()
    _run(sss.save_semantic_state(101, "user-1", hints))
    loaded = _run(sss.load_semantic_state(101))
    assert loaded == hints


def test_load_missing_session_returns_empty(monkeypatch):
    _patch(monkeypatch)
    loaded = _run(sss.load_semantic_state(999))
    assert loaded == SemanticHints()


def test_load_none_session_id_returns_empty_without_db_call(monkeypatch):
    def _boom():
        raise AssertionError("should not touch the DB for session_id=None")
    monkeypatch.setattr(sss, "get_supabase", _boom)
    assert _run(sss.load_semantic_state(None)) == SemanticHints()


# ── Idempotency (Step 22) ────────────────────────────────────────────────

def test_duplicate_save_keeps_one_row(monkeypatch):
    store = _patch(monkeypatch)
    hints = _golden_hints()
    _run(sss.save_semantic_state(101, "user-1", hints))
    _run(sss.save_semantic_state(101, "user-1", hints))
    _run(sss.save_semantic_state(101, "user-1", hints))
    assert len(store) == 1
    assert store[101]["semantic_state"] == sss._to_storage(hints)


def test_unchanged_state_skips_db_write_entirely(monkeypatch):
    """save_semantic_state(..., prior=hints) with hints == prior must not
    even call the DB -- the common "nothing new this turn" case."""
    def _boom():
        raise AssertionError("should not touch the DB when prior == hints")
    monkeypatch.setattr(sss, "get_supabase", _boom)
    hints = _golden_hints()
    _run(sss.save_semantic_state(101, "user-1", hints, prior=hints))


def test_reconnect_then_save_again_is_one_authoritative_state(monkeypatch):
    store = _patch(monkeypatch)
    turn5_only = SemanticHints(
        candidate_turn_status={GOLDEN_ITEM: {5: "verified_not_revealed"}},
        verification_status={GOLDEN_ITEM: "verified_not_revealed"},
    )
    _run(sss.save_semantic_state(101, "user-1", turn5_only))
    reloaded = _run(sss.load_semantic_state(101))
    assert reloaded == turn5_only

    full = _golden_hints()
    _run(sss.save_semantic_state(101, "user-1", full, prior=reloaded))
    assert len(store) == 1
    assert _run(sss.load_semantic_state(101)) == full


def test_no_session_id_never_writes(monkeypatch):
    def _boom():
        raise AssertionError("should not touch the DB for a warmup (no session_id)")
    monkeypatch.setattr(sss, "get_supabase", _boom)
    _run(sss.save_semantic_state(None, "user-1", _golden_hints()))


# ── Failure handling (Step 23) ────────────────────────────────────────────

def test_save_failure_does_not_raise(monkeypatch):
    _patch(monkeypatch, raise_on={"upsert"})
    # Must not raise -- a persistence failure is never allowed to take down
    # a live speaking session.
    _run(sss.save_semantic_state(101, "user-1", _golden_hints()))


def test_load_failure_falls_back_to_empty(monkeypatch):
    _patch(monkeypatch, raise_on={"select"})
    assert _run(sss.load_semantic_state(101)) == SemanticHints()


# ── Version handling (Step 17/24) ────────────────────────────────────────

def test_unknown_state_version_falls_back_to_empty_not_crash(monkeypatch):
    store = _patch(monkeypatch)
    store[101] = {
        "session_usage_id": 101, "state_version": 999,
        "semantic_state": sss._to_storage(_golden_hints()),
    }
    loaded = _run(sss.load_semantic_state(101))
    assert loaded == SemanticHints()  # safe fallback, not a crash, not a misread


def test_current_version_round_trips(monkeypatch):
    store = _patch(monkeypatch)
    _run(sss.save_semantic_state(101, "user-1", _golden_hints()))
    assert store[101]["state_version"] == sss.STATE_VERSION


# ── Session isolation (Step 32.19) ───────────────────────────────────────

def test_sessions_are_isolated(monkeypatch):
    store = _patch(monkeypatch)
    hints_a = _golden_hints()
    hints_b = SemanticHints(resolved_concerns=frozenset({"pain"}))
    _run(sss.save_semantic_state(1, "user-1", hints_a))
    _run(sss.save_semantic_state(2, "user-2", hints_b))
    assert _run(sss.load_semantic_state(1)) == hints_a
    assert _run(sss.load_semantic_state(2)) == hints_b


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
