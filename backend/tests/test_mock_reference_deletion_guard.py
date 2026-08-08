"""Regression tests for the Mock Test deletion guard
(app.services.mock_reference_guard.block_if_referenced_by_mock_test) and its
three call sites: reading.delete_test, listening.delete_test, and
admin.admin_delete_scenario(hard=True).

Before this fix, deleting a reading/listening test or hard-deleting a
scenario never checked mock_tests/mock_test_sessions -- the FK's
ON DELETE SET NULL would silently null a live pack's frozen reference (this
is exactly how Mock Test 3 ended up with reading_test_id=NULL). The guard
blocks (409) only when the content is still frozen into an ACTIVE pack or an
OPEN (in_progress/awaiting_speaking) session -- a completed session's copy of
the id must never block deletion, since its result is already recorded and
needs no live content.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from app.routers import reading, listening, admin


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def in_(self, col, values):
        values = set(values)
        self._filters.append(lambda r, c=col, v=values: r.get(c) in v)
        return self

    def delete(self):
        return self

    def update(self, *_a, **_k):
        return self

    def insert(self, *_a, **_k):
        return self

    def execute(self):
        return FakeResult([r for r in self._rows if all(f(r) for f in self._filters)])


class FakeSupabase:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return FakeQuery(self._tables.get(name, []))


_ADMIN = SimpleNamespace(id="admin-1", email="admin@example.com")

_ACTIVE_PACK = {"id": 1, "label": "Mock Test 1", "reading_test_id": 100, "listening_test_id": 200,
                "writing_scenario_id": 300, "speaking_scenario_id_1": 301, "speaking_scenario_id_2": 302,
                "is_active": True}
_OPEN_SESSION = {"id": "sess-1", "status": "in_progress", "reading_test_id": 101, "listening_test_id": 201,
                  "writing_scenario_id": 310, "speaking_scenario_id_1": 311, "speaking_scenario_id_2": 312}
_COMPLETED_SESSION = {"id": "sess-2", "status": "complete", "reading_test_id": 102, "listening_test_id": 202,
                       "writing_scenario_id": 320, "speaking_scenario_id_1": 321, "speaking_scenario_id_2": 322}


def _fake(**extra_tables):
    tables = {
        "mock_tests": [_ACTIVE_PACK],
        "mock_test_sessions": [_OPEN_SESSION, _COMPLETED_SESSION],
    }
    tables.update(extra_tables)
    return FakeSupabase(tables)


def _expect_409(fn):
    try:
        fn()
        assert False, "expected HTTPException(409)"
    except HTTPException as e:
        assert e.status_code == 409, e.status_code


# ── Reading ──────────────────────────────────────────────────────────

def test_reading_delete_blocked_by_active_pack(monkeypatch):
    fake = _fake(reading_tests=[{"id": 100}])
    monkeypatch.setattr(reading, "get_supabase", lambda: fake)
    _expect_409(lambda: reading.delete_test(100, _admin=_ADMIN))


def test_reading_delete_blocked_by_open_session(monkeypatch):
    fake = _fake(reading_tests=[{"id": 101}])
    monkeypatch.setattr(reading, "get_supabase", lambda: fake)
    _expect_409(lambda: reading.delete_test(101, _admin=_ADMIN))


def test_reading_delete_allowed_when_only_completed_session_references_it(monkeypatch):
    fake = _fake(reading_tests=[{"id": 102}])
    monkeypatch.setattr(reading, "get_supabase", lambda: fake)
    result = reading.delete_test(102, _admin=_ADMIN)
    assert result == {"success": True}


def test_reading_delete_unaffected_when_not_referenced(monkeypatch):
    fake = _fake(reading_tests=[{"id": 999}])
    monkeypatch.setattr(reading, "get_supabase", lambda: fake)
    result = reading.delete_test(999, _admin=_ADMIN)
    assert result == {"success": True}


# ── Listening ────────────────────────────────────────────────────────

def test_listening_delete_blocked_by_active_pack(monkeypatch):
    fake = _fake(listening_tests=[{"id": 200}])
    monkeypatch.setattr(listening, "get_supabase", lambda: fake)
    _expect_409(lambda: listening.delete_test(200, _admin=_ADMIN))


def test_listening_delete_allowed_when_only_completed_session_references_it(monkeypatch):
    fake = _fake(listening_tests=[{"id": 202}])
    monkeypatch.setattr(listening, "get_supabase", lambda: fake)
    result = listening.delete_test(202, _admin=_ADMIN)
    assert result == {"success": True}


def test_listening_delete_unaffected_when_not_referenced(monkeypatch):
    fake = _fake(listening_tests=[{"id": 999}])
    monkeypatch.setattr(listening, "get_supabase", lambda: fake)
    result = listening.delete_test(999, _admin=_ADMIN)
    assert result == {"success": True}


# ── Writing (scenarios table, hard delete) ──────────────────────────

def test_writing_hard_delete_blocked_by_active_pack(monkeypatch):
    fake = _fake(scenarios=[{"id": 300, "module": "writing"}])
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)
    _expect_409(lambda: admin.admin_delete_scenario(300, hard=True, current_user=_ADMIN))


def test_writing_hard_delete_blocked_by_open_session(monkeypatch):
    fake = _fake(scenarios=[{"id": 310, "module": "writing"}])
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)
    _expect_409(lambda: admin.admin_delete_scenario(310, hard=True, current_user=_ADMIN))


def test_writing_hard_delete_allowed_when_only_completed_session_references_it(monkeypatch):
    fake = _fake(scenarios=[{"id": 320, "module": "writing"}])
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)
    result = admin.admin_delete_scenario(320, hard=True, current_user=_ADMIN)
    assert result["deleted"] is True


# ── Speaking (scenarios table, both role-play columns) ──────────────

def test_speaking_hard_delete_blocked_as_role_play_1(monkeypatch):
    fake = _fake(scenarios=[{"id": 301, "module": "speaking"}])
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)
    _expect_409(lambda: admin.admin_delete_scenario(301, hard=True, current_user=_ADMIN))


def test_speaking_hard_delete_blocked_as_role_play_2(monkeypatch):
    fake = _fake(scenarios=[{"id": 302, "module": "speaking"}])
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)
    _expect_409(lambda: admin.admin_delete_scenario(302, hard=True, current_user=_ADMIN))


def test_speaking_hard_delete_blocked_by_open_session(monkeypatch):
    fake = _fake(scenarios=[{"id": 311, "module": "speaking"}])
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)
    _expect_409(lambda: admin.admin_delete_scenario(311, hard=True, current_user=_ADMIN))


def test_speaking_hard_delete_allowed_when_only_completed_session_references_it(monkeypatch):
    fake = _fake(scenarios=[{"id": 322, "module": "speaking"}])
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)
    result = admin.admin_delete_scenario(322, hard=True, current_user=_ADMIN)
    assert result["deleted"] is True


# ── Soft delete stays untouched ──────────────────────────────────────

def test_soft_delete_unchanged_even_when_referenced_by_active_pack(monkeypatch):
    # hard=False (default): must NOT be blocked by the new guard at all --
    # soft delete (is_active=False) is already safe under the stale-content
    # model, this task must not add a new restriction to it.
    fake = _fake(scenarios=[{"id": 300, "module": "writing"}])
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)
    result = admin.admin_delete_scenario(300, hard=False, current_user=_ADMIN)
    assert result == {"success": True, "deleted": False, "message": "Scenario 300 deactivated"}


if __name__ == "__main__":
    import inspect

    class MP:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = MP()
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        if "monkeypatch" in inspect.signature(t).parameters:
            t(mp)
        else:
            t()
        passed += 1
    print(f"{passed}/{len(tests)} mock reference deletion guard checks passed")
