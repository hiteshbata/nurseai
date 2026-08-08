"""One runnable check: content_studio must count reading/listening publish
state off the TEST tables (the student-visibility gate), not the child
passage/section tables -- that mismatch was the original bug (dashboard
showed 0 unpublished while draft tests existed).
"""
from unittest.mock import patch

from app.services import content_studio

_ROWS = {
    "reading_tests": [
        {"id": 1, "title": "Test 1", "is_active": True, "created_at": "2026-01-01"},
        {"id": 2, "title": "Test 2 (draft)", "is_active": False, "created_at": "2026-01-02"},
    ],
    "listening_tests": [
        {"id": 1, "title": "Test 1", "is_active": True, "created_at": "2026-01-01"},
    ],
    "scenarios": [
        {"id": 1, "title": "S1", "difficulty": "easy", "is_active": True, "created_at": "2026-01-01", "updated_at": "2026-01-01", "module": "speaking"},
    ],
    # Not queried anymore for the summary -- present only to prove a bug
    # regression (querying this table instead of reading_tests) would be
    # caught: it has zero drafts, so if _TABLE ever points here again this
    # test's unpublished-count assertion fails.
    "reading_passages": [
        {"id": 1, "title": "P1", "is_active": True, "created_at": "2026-01-01"},
    ],
}


class _FakeQuery:
    def __init__(self, table_name):
        self._table = table_name
        self._rows = _ROWS.get(table_name, [])

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        return type("Result", (), {"data": self._rows})()


class _FakeSupabase:
    def table(self, name):
        return _FakeQuery(name)


def test_summary_counts_reading_listening_from_test_tables():
    with patch.object(content_studio, "get_supabase", return_value=_FakeSupabase()):
        summary = content_studio.get_summary()

    assert summary["modules"]["reading"] == {"total": 2, "published": 1, "unpublished": 1}
    assert summary["modules"]["listening"] == {"total": 1, "published": 1, "unpublished": 0}
    assert summary["modules"]["speaking"] == {"total": 1, "published": 1, "unpublished": 0}


if __name__ == "__main__":
    test_summary_counts_reading_listening_from_test_tables()
    print("OK")
