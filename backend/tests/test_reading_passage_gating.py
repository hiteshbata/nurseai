"""Regression tests for the standalone Reading passage endpoints
(GET /reading/passages, GET /reading/passages/{id}) respecting their
parent test's Draft/Live status. Before this fix, both endpoints filtered
only the passage's own is_active, ignoring reading_tests.is_active
entirely -- a passage attached to a Draft test (test_id set) was exposed
same as a live one. A standalone passage (test_id null) has no parent to
gate on and must keep working exactly as before.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from app.routers import reading


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

    def order(self, *_a, **_k):
        return self

    def execute(self):
        return FakeResult([r for r in self._rows if all(f(r) for f in self._filters)])


class FakeSupabase:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return FakeQuery(self._tables.get(name, []))


_USER = SimpleNamespace(id="student-1", is_anonymous=False)
_PRO_PROFILE = {"user_id": "student-1", "plan": "pro", "plan_expires_at": "2099-01-01T00:00:00Z"}


def _fake(passages, tests, questions=None):
    return FakeSupabase({
        "reading_passages": passages,
        "reading_tests": tests,
        "user_profiles": [_PRO_PROFILE],
        "questions": questions or [],
    })


_PASSAGES = [
    {"id": 1, "title": "Standalone", "part": "B", "difficulty": "intermediate", "body": "x", "is_active": True, "test_id": None},
    {"id": 2, "title": "In live test", "part": "B", "difficulty": "intermediate", "body": "x", "is_active": True, "test_id": 100},
    {"id": 3, "title": "In draft test", "part": "B", "difficulty": "intermediate", "body": "x", "is_active": True, "test_id": 200},
    {"id": 4, "title": "Deactivated standalone", "part": "B", "difficulty": "intermediate", "body": "x", "is_active": False, "test_id": None},
]
_TESTS = [
    {"id": 100, "title": "Test A", "is_active": True},
    {"id": 200, "title": "Test B (draft)", "is_active": False},
]


def test_list_excludes_draft_test_passages(monkeypatch):
    monkeypatch.setattr(reading, "get_supabase", lambda: _fake(_PASSAGES, _TESTS))
    result_ids = {r["id"] for r in reading.list_passages(current_user=_USER)}
    assert result_ids == {1, 2}  # standalone + live-test passage only


def test_standalone_passage_accessible(monkeypatch):
    monkeypatch.setattr(reading, "get_supabase", lambda: _fake(_PASSAGES, _TESTS))
    result = reading.get_passage(1, current_user=_USER)
    assert result["id"] == 1
    assert "test_id" not in result


def test_live_test_passage_accessible(monkeypatch):
    monkeypatch.setattr(reading, "get_supabase", lambda: _fake(_PASSAGES, _TESTS))
    result = reading.get_passage(2, current_user=_USER)
    assert result["id"] == 2


def test_draft_test_passage_returns_404(monkeypatch):
    monkeypatch.setattr(reading, "get_supabase", lambda: _fake(_PASSAGES, _TESTS))
    try:
        reading.get_passage(3, current_user=_USER)
        assert False, "expected 404"
    except HTTPException as e:
        assert e.status_code == 404


def test_inactive_passage_returns_404(monkeypatch):
    monkeypatch.setattr(reading, "get_supabase", lambda: _fake(_PASSAGES, _TESTS))
    try:
        reading.get_passage(4, current_user=_USER)
        assert False, "expected 404"
    except HTTPException as e:
        assert e.status_code == 404


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
    print(f"{passed}/{len(tests)} reading passage gating checks passed")
