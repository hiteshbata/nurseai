"""RC4.1 -- Reading test serving/grading dual-mode (app.routers.reading).
Proves: publishing (Make Live) cuts a version; a versioned test serves and
grades from the frozen snapshot -- even after the live question's own
correct_answer is edited mid-flight; and a never-versioned (legacy) test
keeps working exactly as before, untouched by any of this.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.routers.reading as reading_router
from app.routers.reading import ReadingTestSubmitRequest, ReadingAnswer, SetActiveRequest


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, supabase, table_name):
        self.supabase = supabase
        self.table_name = table_name
        self.rows = supabase.tables.setdefault(table_name, [])
        self.filters = []
        self.in_filters = []
        self.order_col = None
        self.order_desc = False
        self.limit_n = None
        self.op = None
        self.payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def in_(self, col, vals):
        self.in_filters.append((col, set(vals)))
        return self

    def order(self, col, desc=False):
        self.order_col = col
        self.order_desc = desc
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def _matched(self):
        rows = [
            r for r in self.rows
            if all(r.get(c) == v for c, v in self.filters)
            and all(r.get(c) in v for c, v in self.in_filters)
        ]
        if self.order_col:
            rows = sorted(rows, key=lambda r: r.get(self.order_col) or 0, reverse=self.order_desc)
        if self.limit_n is not None:
            rows = rows[: self.limit_n]
        return rows

    def execute(self):
        if self.op == "insert":
            new_id = max([r.get("id", 0) for r in self.rows], default=0) + 1
            row = {"id": new_id, **self.payload}
            self.rows.append(row)
            return FakeResult([row])
        if self.op == "update":
            for r in self._matched():
                r.update(self.payload)
            return FakeResult(self._matched())
        return FakeResult(self._matched())


class FakeSupabase:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return FakeQuery(self, name)


_USER = SimpleNamespace(id="student-1", is_anonymous=False)
_ADMIN = SimpleNamespace(id="admin-1", is_anonymous=False)
_PRO_PROFILE = {"user_id": "student-1", "plan": "pro", "plan_expires_at": "2099-01-01T00:00:00Z"}


def _seeded_fake():
    """Passage 10 (Part B) is what every test below actually exercises
    (frozen body/grading). Passages 11 (Part A) and 12 (Part C) exist only
    so the fixture satisfies RC4.2's full A/B/C publish gate -- set_test_active
    now 409s on partial coverage (see assessment_validation.validate_reading_test)."""
    fake = FakeSupabase()
    fake.tables["user_profiles"] = [_PRO_PROFILE]
    fake.tables["mock_test_sessions"] = []  # no open mock -- get_pinned_test_version_id short-circuits
    fake.tables["reading_tests"] = [{"id": 1, "title": "OET Reading Test 1", "is_active": False}]
    fake.tables["reading_passages"] = [{
        "id": 10, "title": "Passage 1", "part": "B", "difficulty": "intermediate",
        "body": "original body", "test_id": 1, "is_active": True,
    }, {
        "id": 11, "title": "Passage A", "part": "A", "difficulty": "intermediate",
        "body": "part a body", "test_id": 1, "is_active": True,
    }, {
        "id": 12, "title": "Passage C", "part": "C", "difficulty": "intermediate",
        "body": "part c body", "test_id": 1, "is_active": True,
    }]
    fake.tables["questions"] = [{
        "id": 100, "passage_id": 10, "type": "mcq", "content": "original question",
        "options": json.dumps(["a", "b"]), "correct_answer": "a",
    }, {
        "id": 110, "passage_id": 11, "type": "mcq", "content": "part a question",
        "options": json.dumps(["a", "b"]), "correct_answer": "a",
    }, {
        "id": 120, "passage_id": 12, "type": "mcq", "content": "part c question",
        "options": json.dumps(["a", "b"]), "correct_answer": "a",
    }]
    return fake


def test_publishing_cuts_version_1_and_flips_live(monkeypatch):
    fake = _seeded_fake()
    monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
    result = reading_router.set_test_active(1, SetActiveRequest(is_active=True), admin=_ADMIN)
    assert result == {"success": True, "is_active": True}
    assert fake.tables["reading_tests"][0]["is_active"] is True
    assert len(fake.tables["reading_test_versions"]) == 1
    assert fake.tables["reading_test_versions"][0]["version"] == 1


def test_unpublish_does_not_cut_a_version():
    fake = _seeded_fake()
    fake.tables["reading_tests"][0]["is_active"] = True
    import app.routers.reading as rr
    orig = rr.get_supabase
    rr.get_supabase = lambda: fake
    try:
        rr.set_test_active(1, SetActiveRequest(is_active=False), admin=_ADMIN)
    finally:
        rr.get_supabase = orig
    assert fake.tables.get("reading_test_versions", []) == []


def test_get_reading_test_serves_frozen_snapshot_once_published(monkeypatch):
    fake = _seeded_fake()
    monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
    reading_router.set_test_active(1, SetActiveRequest(is_active=True), admin=_ADMIN)

    result = reading_router.get_reading_test(1, current_user=_USER)
    q = result["passages"][0]["questions"][0]
    assert result["title"] == "OET Reading Test 1"
    assert "correct_answer" not in q  # never leaked to the student payload


def test_legacy_unversioned_test_still_serves_from_live_tables(monkeypatch):
    fake = _seeded_fake()
    fake.tables["reading_tests"][0]["is_active"] = True  # live, but never went through set_test_active
    monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)

    result = reading_router.get_reading_test(1, current_user=_USER)
    assert any(p["title"] == "Passage 1" for p in result["passages"])
    assert fake.tables.get("reading_test_versions", []) == []  # legacy path never touches versions


def test_submit_grades_against_frozen_answer_even_after_live_edit(monkeypatch):
    """The core RC4.1 safety guarantee: once published, an admin editing the
    live correct_answer must NOT change how an already-served attempt is
    graded."""
    fake = _seeded_fake()
    monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
    reading_router.set_test_active(1, SetActiveRequest(is_active=True), admin=_ADMIN)  # freezes correct_answer="a"

    # Admin now changes the live answer to "b".
    fake.tables["questions"][0]["correct_answer"] = "b"

    request = ReadingTestSubmitRequest(answers=[ReadingAnswer(questionId=100, selectedOption="a")], elapsed_seconds=120)
    result = asyncio.run(reading_router.submit_reading_test(1, request, current_user=_USER, user_db=fake))

    # Graded against the FROZEN answer ("a"), not the live one ("b") --
    # the student's "a" is marked correct.
    assert result["correct"] == 1
    assert result["results"][0]["is_correct"] is True
    assert result["results"][0]["correct_answer"] == "a"

    stored_feedback = json.loads(fake.tables["submissions"][0]["feedback"])
    assert stored_feedback["test_version_id"] == fake.tables["reading_test_versions"][0]["id"]


def test_submit_legacy_test_grades_from_live_table(monkeypatch):
    fake = _seeded_fake()
    fake.tables["reading_tests"][0]["is_active"] = True  # legacy live test, never versioned
    monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)

    request = ReadingTestSubmitRequest(answers=[ReadingAnswer(questionId=100, selectedOption="a")], elapsed_seconds=60)
    result = asyncio.run(reading_router.submit_reading_test(1, request, current_user=_USER, user_db=fake))
    assert result["correct"] == 1

    stored_feedback = json.loads(fake.tables["submissions"][0]["feedback"])
    assert stored_feedback["test_version_id"] is None


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
    print(f"{passed}/{len(tests)} reading versioning checks passed")
