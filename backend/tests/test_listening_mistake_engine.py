"""E2.1 -- Mistake Engine (evidence store) for Listening.

Verifies listening_mistake_engine.record_listening_mistake_events writes the
right per-question evidence row, for both the frozen-version and legacy
(never-versioned) grading paths, and that it -- like skill_graph -- can never
turn a successful submission into a failure. Also checks the existing submit
response shape, GET /listening/mistakes, and the mock-pinned-version path are
all untouched by this addition.

Fake Supabase fixture mirrors test_listening_versioning.py's (same table/
FakeQuery/FakeSupabase shape), kept local per this test suite's convention of
one self-contained fake per file rather than a shared import.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.routers.listening as listening_router
import app.services.skill_graph as skill_graph
import app.services.listening_mistake_engine as mistake_engine
from app.routers.listening import ListeningTestSubmitRequest, ListeningAnswer, SetActiveRequest


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
        self.not_filters = []
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
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for p in payloads:
                new_id = max([r.get("id", 0) for r in self.rows], default=0) + 1
                row = {"id": new_id, **p}
                self.rows.append(row)
                out.append(row)
            return FakeResult(out)
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


_ADMIN = SimpleNamespace(id="admin-1", is_anonymous=False)
_PRO_PROFILE_TEMPLATE = {"plan": "pro", "plan_expires_at": "2099-01-01T00:00:00Z"}


def _user(uid: str) -> SimpleNamespace:
    return SimpleNamespace(id=uid, is_anonymous=False)


def _seeded_fake(user_id: str) -> FakeSupabase:
    """Same A/B/C fixture as test_listening_versioning.py (needed to satisfy
    the full-coverage publish gate). Section 20/question 200 (Part B) is what
    every test below actually submits against."""
    fake = FakeSupabase()
    fake.tables["user_profiles"] = [{"user_id": user_id, **_PRO_PROFILE_TEMPLATE}]
    fake.tables["mock_test_sessions"] = []
    fake.tables["listening_tests"] = [{"id": 2, "title": "OET Listening Test 1", "is_active": False, "part_audio": {}, "part_audio_times": {}}]
    fake.tables["listening_sections"] = [{
        "id": 20, "title": "Section 1", "part": "B", "difficulty": "intermediate",
        "audio_url": "https://bucket/original.mp3", "transcript": [{"speaker": "Nurse", "text": "original"}],
        "body": None, "test_id": 2, "is_active": True,
    }, {
        "id": 21, "title": "Section A", "part": "A", "difficulty": "easy",
        "audio_url": "https://bucket/part-a.mp3", "transcript": None,
        "body": None, "test_id": 2, "is_active": True,
    }, {
        "id": 22, "title": "Section C", "part": "C", "difficulty": "hard",
        "audio_url": "https://bucket/part-c.mp3", "transcript": None,
        "body": None, "test_id": 2, "is_active": True,
    }]
    fake.tables["questions"] = [{
        "id": 200, "section_id": 20, "type": "mcq", "content": "original question",
        "options": json.dumps(["a", "b"]), "correct_answer": "a",
    }, {
        "id": 210, "section_id": 21, "type": "mcq", "content": "part a question",
        "options": json.dumps(["a", "b"]), "correct_answer": "a",
    }, {
        "id": 220, "section_id": 22, "type": "mcq", "content": "part c question",
        "options": json.dumps(["a", "b"]), "correct_answer": "a",
    }]
    return fake


def _patch_all(monkeypatch, fake):
    monkeypatch.setattr(listening_router, "get_supabase", lambda: fake)
    monkeypatch.setattr(skill_graph, "get_supabase", lambda: fake)
    monkeypatch.setattr(mistake_engine, "get_supabase", lambda: fake)


def _submit(fake, user, question_id=200, selected="a", elapsed=60):
    request = ListeningTestSubmitRequest(answers=[ListeningAnswer(questionId=question_id, selectedOption=selected)], elapsed_seconds=elapsed)
    return asyncio.run(listening_router.submit_test(2, request, current_user=user, user_db=fake))


def _events(fake):
    return fake.tables.get("listening_mistake_events", [])


# ── core event content ────────────────────────────────────────────────

def test_correct_answer_creates_mistake_event(monkeypatch):
    fake = _seeded_fake("u-correct")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True  # legacy (never versioned)

    _submit(fake, _user("u-correct"), selected="a")

    events = _events(fake)
    assert len(events) == 1
    e = events[0]
    assert e["is_correct"] is True
    assert e["selected_option"] == "a"
    assert e["correct_answer"] == "a"
    assert e["question_id"] == 200
    assert e["section_id"] == 20
    assert e["part"] == "B"
    assert e["question_type"] == "mcq"
    assert e["skill_tag"] == "listening:B"
    assert e["difficulty"] == "intermediate"
    assert e["test_id"] == 2
    assert e["test_version_id"] is None
    assert e["attempt_number"] == 1


def test_wrong_answer_creates_mistake_event(monkeypatch):
    fake = _seeded_fake("u-wrong")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True

    _submit(fake, _user("u-wrong"), selected="b")

    events = _events(fake)
    assert len(events) == 1
    assert events[0]["is_correct"] is False
    assert events[0]["selected_option"] == "b"
    assert events[0]["correct_answer"] == "a"


def test_blank_answer_creates_mistake_event(monkeypatch):
    fake = _seeded_fake("u-blank")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True

    _submit(fake, _user("u-blank"), selected=None)

    events = _events(fake)
    assert len(events) == 1
    assert events[0]["is_correct"] is False
    assert events[0]["selected_option"] is None
    assert events[0]["correct_answer"] == "a"


# ── attempt numbering ─────────────────────────────────────────────────

def test_repeated_question_attempt_numbers_increment(monkeypatch):
    fake = _seeded_fake("u-repeat")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True
    user = _user("u-repeat")

    _submit(fake, user, selected="a")
    _submit(fake, user, selected="a")

    events = sorted(_events(fake), key=lambda e: e["id"])
    assert [e["attempt_number"] for e in events] == [1, 2]


def test_wrong_then_corrected_records_two_events(monkeypatch):
    fake = _seeded_fake("u-fix")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True
    user = _user("u-fix")

    _submit(fake, user, selected="b")  # wrong
    _submit(fake, user, selected="a")  # corrected

    events = sorted(_events(fake), key=lambda e: e["id"])
    assert [e["is_correct"] for e in events] == [False, True]
    assert [e["attempt_number"] for e in events] == [1, 2]


def test_repeated_persistent_wrong_records_multiple_events(monkeypatch):
    fake = _seeded_fake("u-persist")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True
    user = _user("u-persist")

    _submit(fake, user, selected="b")
    _submit(fake, user, selected="b")
    _submit(fake, user, selected="b")

    events = sorted(_events(fake), key=lambda e: e["id"])
    assert [e["is_correct"] for e in events] == [False, False, False]
    assert [e["attempt_number"] for e in events] == [1, 2, 3]


# ── frozen vs. legacy metadata ─────────────────────────────────────────

def test_frozen_version_metadata_used_for_event(monkeypatch):
    fake = _seeded_fake("u-frozen")
    _patch_all(monkeypatch, fake)
    listening_router.set_test_active(2, SetActiveRequest(is_active=True), admin=_ADMIN)
    version_id = fake.tables["listening_test_versions"][0]["id"]

    # Admin edits live content after publish -- event must reflect the frozen
    # snapshot's metadata, same as grading itself does (RC4.1 contract).
    fake.tables["listening_sections"][0]["difficulty"] = "hard"
    fake.tables["questions"][0]["correct_answer"] = "b"

    _submit(fake, _user("u-frozen"), selected="a")

    events = _events(fake)
    assert len(events) == 1
    e = events[0]
    assert e["test_version_id"] == version_id
    assert e["difficulty"] == "intermediate"  # frozen, not the post-publish edit
    assert e["correct_answer"] == "a"  # frozen answer, not the edited "b"
    assert e["section_id"] == 20
    assert e["part"] == "B"


def test_legacy_nonversioned_test_metadata(monkeypatch):
    fake = _seeded_fake("u-legacy")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True  # live, never published

    _submit(fake, _user("u-legacy"), selected="a")

    events = _events(fake)
    assert len(events) == 1
    assert events[0]["test_version_id"] is None
    assert events[0]["difficulty"] == "intermediate"
    assert events[0]["section_id"] == 20
    assert fake.tables.get("listening_test_versions", []) == []


# ── best-effort failure isolation ──────────────────────────────────────

def test_skill_graph_failure_does_not_break_submission(monkeypatch):
    fake = _seeded_fake("u-sg-fail")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True

    def _boom():
        raise RuntimeError("skill graph down")
    monkeypatch.setattr(skill_graph, "get_supabase", _boom)

    result = _submit(fake, _user("u-sg-fail"), selected="a")
    assert result["correct"] == 1
    assert len(fake.tables["submissions"]) == 1
    assert len(_events(fake)) == 1  # mistake engine still ran fine


def test_mistake_engine_db_failure_does_not_break_submission(monkeypatch):
    fake = _seeded_fake("u-me-fail")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True

    def _boom():
        raise RuntimeError("mistake engine table unavailable")
    monkeypatch.setattr(mistake_engine, "get_supabase", _boom)

    result = _submit(fake, _user("u-me-fail"), selected="a")
    assert result["correct"] == 1
    assert len(fake.tables["submissions"]) == 1
    assert _events(fake) == []  # nothing written, but submission still succeeded


# ── compatibility: response shape, /mistakes, mock-pinned path ────────

def test_submit_response_shape_unchanged(monkeypatch):
    fake = _seeded_fake("u-shape")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True

    result = _submit(fake, _user("u-shape"), selected="a")
    assert set(result.keys()) == {"score", "correct", "total", "results", "per_part", "transcripts", "insights"}
    assert result["results"] == [{"questionId": 200, "selected": "a", "correct_answer": "a", "is_correct": True}]


def test_mistakes_endpoint_unaffected_by_new_table(monkeypatch):
    fake = _seeded_fake("u-mistakes")
    _patch_all(monkeypatch, fake)
    fake.tables["listening_tests"][0]["is_active"] = True
    user = _user("u-mistakes")

    _submit(fake, user, selected="b")  # wrong -- should surface in /mistakes

    result = asyncio.run(listening_router.list_mistakes(current_user=user, user_db=fake))
    assert len(result) == 1
    assert result[0]["questionId"] == 200
    assert result[0]["your_answer"] == "b"
    assert result[0]["correct_answer"] == "a"


def test_mock_pinned_version_path_still_works(monkeypatch):
    """Mock Listening submits through this exact same endpoint, pinned to the
    version its session started on (see mock.py get_pinned_test_version_id) --
    no separate submit path exists for it."""
    fake = _seeded_fake("u-mock")
    _patch_all(monkeypatch, fake)
    listening_router.set_test_active(2, SetActiveRequest(is_active=True), admin=_ADMIN)
    version_id = fake.tables["listening_test_versions"][0]["id"]

    fake.tables["mock_test_sessions"].append({
        "id": 1, "user_id": "u-mock", "status": "in_progress",
        "current_section": "listening", "listening_test_id": 2,
        "listening_test_version_id": version_id, "created_at": "2026-08-19T00:00:00Z",
    })

    result = _submit(fake, _user("u-mock"), selected="a")
    assert result["correct"] == 1

    events = _events(fake)
    assert len(events) == 1
    assert events[0]["test_version_id"] == version_id


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
    print(f"{passed}/{len(tests)} listening mistake engine checks passed")
