"""RC4.1 -- Mock Test versioning (app.routers.mock). Proves: generating a
pack cuts its Version 1 immediately (packs have no draft state); starting a
mock pins the session to that pack's newest Mock Test Version and to the
Reading/Listening version it references; the staleness guard no longer
blocks a versioned session mid-mock just because the live test was
unpublished after the student started; and a legacy (pre-RC4.1 or never-
versioned) pack/session keeps working exactly as before.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import app.routers.mock as mock_router
from app.routers.mock import StartMockRequest, SectionDoneRequest


class FakeResult:
    def __init__(self, data):
        self.data = data
        self.count = len(data)


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

    def not_(self):
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
            if self.table_name == "mock_tests" and "is_active" not in row:
                row["is_active"] = True  # mirrors the DB default (mock_tests.is_active default true)
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


_ADMIN = SimpleNamespace(id="admin-1", is_anonymous=False)
_STUDENT = SimpleNamespace(id="student-1", is_anonymous=False)
_ELITE_PROFILE = {"user_id": "student-1", "plan": "elite", "plan_expires_at": "2099-01-01T00:00:00Z"}


def _seeded_content(fake):
    """One active, already-versioned Reading test (v1) and Listening test
    (v1) -- each with full Part A/B/C coverage so admin_publish_mock_test_version's
    RC4.2 validation gate passes -- plus a writing + two speaking scenarios
    with every snapshot field."""
    fake.tables["reading_tests"] = [{"id": 1, "title": "Reading 1", "is_active": True}]
    fake.tables["reading_passages"] = [
        {"id": 10, "title": "P1", "part": "B", "difficulty": "intermediate", "body": "b", "test_id": 1, "is_active": True},
        {"id": 11, "title": "PA", "part": "A", "difficulty": "intermediate", "body": "a", "test_id": 1, "is_active": True},
        {"id": 12, "title": "PC", "part": "C", "difficulty": "intermediate", "body": "c", "test_id": 1, "is_active": True},
    ]
    fake.tables["questions"] = [
        {"id": 100, "passage_id": 10, "type": "mcq", "content": "q", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
        {"id": 110, "passage_id": 11, "type": "mcq", "content": "qa", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
        {"id": 120, "passage_id": 12, "type": "mcq", "content": "qc", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
    ]
    fake.tables["listening_tests"] = [{"id": 2, "title": "Listening 1", "is_active": True, "part_audio": {}, "part_audio_times": {}}]
    fake.tables["listening_sections"] = [
        {"id": 20, "title": "S1", "part": "B", "difficulty": "intermediate", "audio_url": "https://x/b.mp3", "transcript": [], "body": None, "test_id": 2, "is_active": True},
        {"id": 21, "title": "SA", "part": "A", "difficulty": "intermediate", "audio_url": "https://x/a.mp3", "transcript": [], "body": None, "test_id": 2, "is_active": True},
        {"id": 22, "title": "SC", "part": "C", "difficulty": "intermediate", "audio_url": "https://x/c.mp3", "transcript": [], "body": None, "test_id": 2, "is_active": True},
    ]
    fake.tables["questions"] += [
        {"id": 200, "section_id": 20, "type": "mcq", "content": "q", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
        {"id": 210, "section_id": 21, "type": "mcq", "content": "qa", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
        {"id": 220, "section_id": 22, "type": "mcq", "content": "qc", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
    ]
    # RC4.2: nurse_card/interlocutor_card/scoring_criteria must be non-empty
    # (validate_mock_test's scenario checks) -- `{}` (this fixture's
    # pre-RC4.2 placeholder) is now a legitimate "missing" failure.
    fake.tables["scenarios"] = [
        {"id": 300, "module": "writing", "title": "W1", "is_active": True, "setting": "notes", "nurse_card": {"task": "Write a letter"}, "scoring_criteria": {"rubric": "content"}, "key_points": [], "difficulty": "medium", "specialty": "general"},
        {"id": 301, "module": "speaking", "title": "S1", "is_active": True, "setting": "ward", "nurse_card": {"task": "Explain the procedure"}, "interlocutor_card": {"persona": "anxious patient"}, "scoring_criteria": {"rubric": "communication"}, "difficulty": "easy", "specialty": "general", "voice_config": {}, "patient_gender": "male", "patient_age": 40},
        {"id": 302, "module": "speaking", "title": "S2", "is_active": True, "setting": "ward", "nurse_card": {"task": "Reassure the patient"}, "interlocutor_card": {"persona": "worried relative"}, "scoring_criteria": {"rubric": "communication"}, "difficulty": "easy", "specialty": "general", "voice_config": {}, "patient_gender": "female", "patient_age": 30},
    ]
    from app.services.assessment_versioning import publish_reading_version, publish_listening_version
    publish_reading_version(fake, 1, "admin-1")
    publish_listening_version(fake, 2, "admin-1")


def test_generate_cuts_version_1_at_creation(monkeypatch):
    fake = FakeSupabase()
    _seeded_content(fake)
    monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)

    pack = asyncio.run(mock_router.admin_generate_mock_test(current_user=_ADMIN))
    assert pack["label"] == "Mock Test 1"
    versions = fake.tables["mock_test_versions"]
    assert len(versions) == 1
    assert versions[0]["mock_test_id"] == pack["id"]
    assert versions[0]["version"] == 1
    assert versions[0]["snapshot"]["reading_test_version_id"] == fake.tables["reading_test_versions"][0]["id"]


def test_start_mock_pins_session_to_versions(monkeypatch):
    fake = FakeSupabase()
    _seeded_content(fake)
    fake.tables["user_profiles"] = [_ELITE_PROFILE]
    monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)

    pack = asyncio.run(mock_router.admin_generate_mock_test(current_user=_ADMIN))
    payload = asyncio.run(mock_router.start_mock(StartMockRequest(mock_test_id=pack["id"]), request=None, current_user=_STUDENT))

    session = fake.tables["mock_test_sessions"][0]
    mock_version = fake.tables["mock_test_versions"][0]
    assert session["mock_test_version_id"] == mock_version["id"]
    assert session["reading_test_version_id"] == mock_version["snapshot"]["reading_test_version_id"]
    assert session["listening_test_version_id"] == mock_version["snapshot"]["listening_test_version_id"]
    assert payload["current_section"] == "listening"


def test_legacy_pack_without_any_version_starts_with_null_pins(monkeypatch):
    fake = FakeSupabase()
    _seeded_content(fake)
    fake.tables["user_profiles"] = [_ELITE_PROFILE]
    monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)

    # A pack that predates RC4.1 (or the backfill hasn't run yet) -- no
    # mock_test_versions row for it at all.
    fake.tables["mock_tests"] = [{
        "id": 9, "label": "Legacy Pack", "is_active": True,
        "reading_test_id": 1, "listening_test_id": 2,
        "writing_scenario_id": 300, "speaking_scenario_id_1": 301, "speaking_scenario_id_2": 302,
    }]

    asyncio.run(mock_router.start_mock(StartMockRequest(mock_test_id=9), request=None, current_user=_STUDENT))
    session = fake.tables["mock_test_sessions"][0]
    assert session.get("mock_test_version_id") is None
    assert session.get("reading_test_version_id") is None
    assert session["reading_test_id"] == 1  # legacy content-id columns still populated as before


def test_section_done_not_blocked_by_unpublish_when_version_pinned(monkeypatch):
    """The safety-critical case: a student already mid-mock, pinned to an
    immutable Reading version, must not be blocked from advancing into
    Reading just because an admin unpublished the live reading_tests row
    after the mock started."""
    fake = FakeSupabase()
    _seeded_content(fake)
    monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)

    reading_version_id = fake.tables["reading_test_versions"][0]["id"]
    listening_version_id = fake.tables["listening_test_versions"][0]["id"]
    fake.tables["mock_test_sessions"] = [{
        "id": "sess-1", "user_id": "student-1", "status": "in_progress",
        "current_section": "listening", "listening_test_id": 2, "reading_test_id": 1,
        "writing_scenario_id": 300, "speaking_scenario_id_1": 301, "speaking_scenario_id_2": 302,
        "reading_test_version_id": reading_version_id, "listening_test_version_id": listening_version_id,
        "mock_test_version_id": 1, "section_started_at": {}, "results": {},
    }]

    # Admin unpublishes the live reading test after the student started.
    fake.tables["reading_tests"][0]["is_active"] = False

    result = asyncio.run(mock_router.section_done(
        "sess-1", SectionDoneRequest(section="listening", result={"band": 6.0}), current_user=_STUDENT,
    ))
    assert result["next_section"] == "reading"  # not blocked


def test_section_done_still_blocked_for_legacy_unpinned_session(monkeypatch):
    """Same scenario, but a legacy session with no version pin -- the
    original staleness guard behavior must be unchanged."""
    fake = FakeSupabase()
    _seeded_content(fake)
    monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
    fake.tables["mock_test_sessions"] = [{
        "id": "sess-2", "user_id": "student-1", "status": "in_progress",
        "current_section": "listening", "listening_test_id": 2, "reading_test_id": 1,
        "writing_scenario_id": 300, "speaking_scenario_id_1": 301, "speaking_scenario_id_2": 302,
        "section_started_at": {}, "results": {},
    }]
    fake.tables["reading_tests"][0]["is_active"] = False

    try:
        asyncio.run(mock_router.section_done(
            "sess-2", SectionDoneRequest(section="listening", result={"band": 6.0}), current_user=_STUDENT,
        ))
        assert False, "expected 409"
    except HTTPException as e:
        assert e.status_code == 409


def test_admin_publish_recuts_a_second_version_for_existing_pack(monkeypatch):
    fake = FakeSupabase()
    _seeded_content(fake)
    monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
    pack = asyncio.run(mock_router.admin_generate_mock_test(current_user=_ADMIN))
    assert len(fake.tables["mock_test_versions"]) == 1

    # Reading gets republished to v2.
    from app.services.assessment_versioning import publish_reading_version
    reading_v2 = publish_reading_version(fake, 1, "admin-1")

    result = asyncio.run(mock_router.admin_publish_mock_test_version(pack["id"], current_user=_ADMIN))
    assert result["version"] == 2
    new_version = fake.tables["mock_test_versions"][1]
    assert new_version["snapshot"]["reading_test_version_id"] == reading_v2["id"]
    # The first version is untouched.
    assert fake.tables["mock_test_versions"][0]["snapshot"]["reading_test_version_id"] != reading_v2["id"]


def test_admin_publish_404s_for_unknown_pack(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
    try:
        asyncio.run(mock_router.admin_publish_mock_test_version(999, current_user=_ADMIN))
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
    print(f"{passed}/{len(tests)} mock versioning checks passed")
