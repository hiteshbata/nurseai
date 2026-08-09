"""RC4.1 -- Listening test serving/grading dual-mode (app.routers.listening).
Mirrors test_reading_versioning.py: publishing cuts a version; a versioned
test serves/grades from the frozen snapshot (audio_url and transcript
included) even after live content is edited; a legacy test is unaffected.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.routers.listening as listening_router
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
    fake = FakeSupabase()
    fake.tables["user_profiles"] = [_PRO_PROFILE]
    fake.tables["mock_test_sessions"] = []
    fake.tables["listening_tests"] = [{"id": 2, "title": "OET Listening Test 1", "is_active": False, "part_audio": {}, "part_audio_times": {}}]
    fake.tables["listening_sections"] = [{
        "id": 20, "title": "Section 1", "part": "B", "difficulty": "intermediate",
        "audio_url": "https://bucket/original.mp3", "transcript": [{"speaker": "Nurse", "text": "original"}],
        "body": None, "test_id": 2, "is_active": True,
    }]
    fake.tables["questions"] = [{
        "id": 200, "section_id": 20, "type": "mcq", "content": "original question",
        "options": json.dumps(["a", "b"]), "correct_answer": "a",
    }]
    return fake


def test_publishing_cuts_version_1_and_flips_live(monkeypatch):
    fake = _seeded_fake()
    monkeypatch.setattr(listening_router, "get_supabase", lambda: fake)
    result = listening_router.set_test_active(2, SetActiveRequest(is_active=True), admin=_ADMIN)
    assert result == {"success": True, "is_active": True}
    assert len(fake.tables["listening_test_versions"]) == 1
    assert fake.tables["listening_test_versions"][0]["version"] == 1


def test_get_test_serves_frozen_audio_url_and_withholds_transcript(monkeypatch):
    fake = _seeded_fake()
    monkeypatch.setattr(listening_router, "get_supabase", lambda: fake)
    listening_router.set_test_active(2, SetActiveRequest(is_active=True), admin=_ADMIN)

    # Admin replaces the audio after publishing.
    fake.tables["listening_sections"][0]["audio_url"] = "https://bucket/REPLACED.mp3"

    result = listening_router.get_test(2, current_user=_USER)
    section = result["sections"][0]
    assert section["audio_url"] == "https://bucket/original.mp3"  # frozen, not the replacement
    assert "transcript" not in section  # withheld pre-submit, same as legacy contract
    assert "correct_answer" not in section["questions"][0]


def test_legacy_unversioned_test_still_serves_from_live_tables(monkeypatch):
    fake = _seeded_fake()
    fake.tables["listening_tests"][0]["is_active"] = True  # live, never versioned
    monkeypatch.setattr(listening_router, "get_supabase", lambda: fake)

    result = listening_router.get_test(2, current_user=_USER)
    assert result["sections"][0]["title"] == "Section 1"
    assert fake.tables.get("listening_test_versions", []) == []


def test_submit_grades_and_reveals_transcript_from_frozen_snapshot(monkeypatch):
    fake = _seeded_fake()
    monkeypatch.setattr(listening_router, "get_supabase", lambda: fake)
    listening_router.set_test_active(2, SetActiveRequest(is_active=True), admin=_ADMIN)  # freezes answer="a", transcript="original"

    # Admin edits the live answer and transcript after publish.
    fake.tables["questions"][0]["correct_answer"] = "b"
    fake.tables["listening_sections"][0]["transcript"] = [{"speaker": "Nurse", "text": "EDITED"}]

    request = ListeningTestSubmitRequest(answers=[ListeningAnswer(questionId=200, selectedOption="a")], elapsed_seconds=90)
    result = asyncio.run(listening_router.submit_test(2, request, current_user=_USER, user_db=fake))

    assert result["correct"] == 1  # graded against frozen "a", not live "b"
    assert result["transcripts"] == {20: [{"speaker": "Nurse", "text": "original"}]}  # frozen transcript revealed

    stored_feedback = json.loads(fake.tables["submissions"][0]["feedback"])
    assert stored_feedback["test_version_id"] == fake.tables["listening_test_versions"][0]["id"]


def test_submit_legacy_test_grades_from_live_table(monkeypatch):
    fake = _seeded_fake()
    fake.tables["listening_tests"][0]["is_active"] = True
    monkeypatch.setattr(listening_router, "get_supabase", lambda: fake)

    request = ListeningTestSubmitRequest(answers=[ListeningAnswer(questionId=200, selectedOption="a")], elapsed_seconds=60)
    result = asyncio.run(listening_router.submit_test(2, request, current_user=_USER, user_db=fake))
    assert result["correct"] == 1
    assert result["transcripts"] == {20: [{"speaker": "Nurse", "text": "original"}]}


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
    print(f"{passed}/{len(tests)} listening versioning checks passed")
