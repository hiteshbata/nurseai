"""RC4.1 -- Assessment Immutability & Versioning: core service tests
(app.services.assessment_versioning). Pure in-memory fake of the Supabase
query builder -- enough to exercise version numbering, concurrency safety,
immutability, snapshot shaping, cross-version Mock references, and backfill
idempotency without a real DB. Mirrors the FakeQuery/FakeSupabase pattern
already used by test_draft_workflow.py.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import app.services.assessment_versioning as av


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
            # Fault injection: simulates a concurrent writer committing the
            # SAME version number a split second before this insert -- the
            # phantom row lands first (as the racing writer's would have),
            # then this insert raises the unique-constraint violation it
            # would genuinely hit against a real DB. One-shot: cleared after
            # firing, so the retry that follows succeeds normally.
            if self.table_name in self.supabase.fail_insert_once_for:
                self.supabase.fail_insert_once_for.discard(self.table_name)
                phantom_id = max([r.get("id", 0) for r in self.rows], default=0) + 1
                self.rows.append({"id": phantom_id, **self.payload})
                raise Exception(f'duplicate key value violates unique constraint "{self.table_name}_uidx"')

            unique_cols = self.supabase.unique_constraints.get(self.table_name)
            if unique_cols and any(all(r.get(c) == self.payload.get(c) for c in unique_cols) for r in self.rows):
                raise Exception(f'duplicate key value violates unique constraint "{self.table_name}_uidx"')
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
    def __init__(self, unique_constraints=None):
        self.tables = {}
        self.unique_constraints = unique_constraints or {}
        self.fail_insert_once_for = set()

    def table(self, name):
        return FakeQuery(self, name)


_VERSION_UNIQUES = {
    "reading_test_versions": ("reading_test_id", "version"),
    "listening_test_versions": ("listening_test_id", "version"),
    "mock_test_versions": ("mock_test_id", "version"),
}


def _fake():
    return FakeSupabase(unique_constraints=_VERSION_UNIQUES)


def _seed_reading_test(fake, test_id=1, passage_id=10, question_id=100):
    fake.tables["reading_tests"] = [{"id": test_id, "title": "OET Reading Test 1"}]
    fake.tables.setdefault("reading_passages", []).append({
        "id": passage_id, "title": "Passage 1", "part": "B", "difficulty": "intermediate",
        "body": "original body", "test_id": test_id, "is_active": True,
    })
    fake.tables.setdefault("questions", []).append({
        "id": question_id, "passage_id": passage_id, "type": "mcq", "content": "original question",
        "options": json.dumps(["a", "b"]), "correct_answer": "a",
    })


def _seed_listening_test(fake, test_id=2, section_id=20, question_id=200):
    fake.tables["listening_tests"] = [{"id": test_id, "title": "OET Listening Test 1", "part_audio": {}, "part_audio_times": {}}]
    fake.tables.setdefault("listening_sections", []).append({
        "id": section_id, "title": "Section 1", "part": "B", "difficulty": "intermediate",
        "audio_url": "https://bucket/original.mp3", "transcript": [{"speaker": "Nurse", "text": "original"}],
        "body": None, "test_id": test_id, "is_active": True,
    })
    fake.tables.setdefault("questions", []).append({
        "id": question_id, "section_id": section_id, "type": "mcq", "content": "original question",
        "options": json.dumps(["a", "b"]), "correct_answer": "a",
    })


# ── version creation ───────────────────────────────────────────────────

def test_first_publish_creates_version_1():
    fake = _fake()
    _seed_reading_test(fake)
    row = av.publish_reading_version(fake, 1, "admin-1")
    assert row["version"] == 1
    assert row["snapshot"]["test_id"] == 1
    assert row["snapshot"]["passages"][0]["passage_id"] == 10


def test_second_successful_publish_creates_version_2():
    fake = _fake()
    _seed_reading_test(fake)
    first = av.publish_reading_version(fake, 1, "admin-1")
    second = av.publish_reading_version(fake, 1, "admin-1")
    assert first["version"] == 1
    assert second["version"] == 2
    assert len(fake.tables["reading_test_versions"]) == 2


def test_failed_publish_does_not_consume_a_version_number():
    fake = _fake()  # no reading_tests row at all -- publish must 404
    try:
        av.publish_reading_version(fake, 999, "admin-1")
        assert False, "expected 404"
    except HTTPException as e:
        assert e.status_code == 404
    assert fake.tables.get("reading_test_versions", []) == []

    # A subsequent successful publish still starts at Version 1 -- the
    # failed attempt above didn't burn a number.
    _seed_reading_test(fake, test_id=999, passage_id=910, question_id=9100)
    row = av.publish_reading_version(fake, 999, "admin-1")
    assert row["version"] == 1


def test_concurrent_publish_does_not_duplicate_version_number():
    """Two simultaneous publishes must not create the same version number.
    Simulated via fault injection: the fake's insert raises a unique-
    constraint violation on the first attempt (as if another transaction
    had just committed that same version), and _allocate_version must
    recompute and retry rather than propagate the conflict or silently
    duplicate the number."""
    fake = _fake()
    fake.fail_insert_once_for.add("reading_test_versions")
    row = av._allocate_version(fake, "reading_test_versions", "reading_test_id", 5, {"x": 1}, "admin-1")
    assert row["version"] == 2  # version 1 was the "other" writer's; this one retried to 2
    versions = sorted(r["version"] for r in fake.tables["reading_test_versions"])
    assert versions == [1, 2]  # exactly one row per version -- no duplicate


# ── immutability ────────────────────────────────────────────────────────

def test_reading_version_unaffected_by_later_live_edits():
    fake = _fake()
    _seed_reading_test(fake)
    version = av.publish_reading_version(fake, 1, "admin-1")

    # Admin edits the live passage, the question's text, and its correct answer.
    fake.tables["reading_passages"][0]["body"] = "EDITED body"
    fake.tables["questions"][0]["content"] = "EDITED question"
    fake.tables["questions"][0]["correct_answer"] = "b"

    frozen = av.get_version_row(fake, "reading_test_versions", version["id"])
    assert frozen["snapshot"]["passages"][0]["body"] == "original body"
    assert frozen["snapshot"]["questions"][0]["content"] == "original question"
    assert frozen["snapshot"]["questions"][0]["correct_answer"] == "a"


def test_listening_version_freezes_audio_url_and_transcript():
    fake = _fake()
    _seed_listening_test(fake)
    version = av.publish_listening_version(fake, 2, "admin-1")

    # Admin replaces the audio (new URL -- old object is never overwritten
    # in place, see build_listening_snapshot's docstring) and edits the transcript.
    fake.tables["listening_sections"][0]["audio_url"] = "https://bucket/REPLACED.mp3"
    fake.tables["listening_sections"][0]["transcript"] = [{"speaker": "Nurse", "text": "EDITED"}]

    frozen = av.get_version_row(fake, "listening_test_versions", version["id"])
    assert frozen["snapshot"]["sections"][0]["audio_url"] == "https://bucket/original.mp3"
    assert frozen["snapshot"]["sections"][0]["transcript"] == [{"speaker": "Nurse", "text": "original"}]


# ── reading/listening snapshot shaping ───────────────────────────────────

def test_reading_snapshot_student_payload_withholds_correct_answer():
    fake = _fake()
    _seed_reading_test(fake)
    version = av.publish_reading_version(fake, 1, "admin-1")
    payload = av.reading_snapshot_student_payload(version)
    q = payload["passages"][0]["questions"][0]
    assert "correct_answer" not in q
    assert q["content"] == "original question"


def test_reading_snapshot_questions_by_id_shape_matches_grading_contract():
    fake = _fake()
    _seed_reading_test(fake)
    version = av.publish_reading_version(fake, 1, "admin-1")
    qbid = av.reading_snapshot_questions_by_id(version)
    assert qbid[100] == {"id": 100, "content": "original question", "correct_answer": "a", "type": "mcq"}


def test_listening_snapshot_transcripts_keyed_by_section_id():
    fake = _fake()
    _seed_listening_test(fake)
    version = av.publish_listening_version(fake, 2, "admin-1")
    transcripts = av.listening_snapshot_transcripts(version)
    assert transcripts == {20: [{"speaker": "Nurse", "text": "original"}]}


# ── Mock: cross-version references ────────────────────────────────────

def _seed_mock_pack(fake, mock_test_id=7, reading_test_id=1, listening_test_id=2):
    fake.tables["mock_tests"] = [{
        "id": mock_test_id, "label": "Mock Test 7",
        "reading_test_id": reading_test_id, "listening_test_id": listening_test_id,
        "writing_scenario_id": 300, "speaking_scenario_id_1": 301, "speaking_scenario_id_2": 302,
    }]
    fake.tables["scenarios"] = [
        {"id": 300, "title": "Writing S", "setting": "notes", "nurse_card": {}, "scoring_criteria": {}, "key_points": [], "difficulty": "medium", "specialty": "general"},
        {"id": 301, "title": "Speaking S1", "setting": "ward", "nurse_card": {}, "interlocutor_card": {}, "scoring_criteria": {}, "difficulty": "easy", "specialty": "general", "voice_config": {}, "patient_gender": "male", "patient_age": 40},
        {"id": 302, "title": "Speaking S2", "setting": "ward", "nurse_card": {}, "interlocutor_card": {}, "scoring_criteria": {}, "difficulty": "easy", "specialty": "general", "voice_config": {}, "patient_gender": "female", "patient_age": 30},
    ]


def test_mock_publish_requires_reading_and_listening_already_versioned():
    fake = _fake()
    _seed_mock_pack(fake)
    # Neither Reading nor Listening has been published yet.
    try:
        av.publish_mock_version(fake, 7, "admin-1")
        assert False, "expected 409"
    except HTTPException as e:
        assert e.status_code == 409


def test_mock_7_version_1_keeps_referencing_reading_v3_after_reading_moves_to_v4():
    """The exact scenario from the architecture doc: Mock 7 Version 1 ->
    Reading V3. Reading is later republished to V4. Mock 7 Version 1 must
    still reference V3, forever. Publishing Mock 7 Version 2 afterward picks
    up the new latest (V4) instead."""
    fake = _fake()
    _seed_reading_test(fake, test_id=1)
    _seed_listening_test(fake, test_id=2)
    _seed_mock_pack(fake, mock_test_id=7, reading_test_id=1, listening_test_id=2)

    # Get Reading to V3 before Mock 7's first publish.
    av.publish_reading_version(fake, 1, "admin-1")  # v1
    av.publish_reading_version(fake, 1, "admin-1")  # v2
    reading_v3 = av.publish_reading_version(fake, 1, "admin-1")  # v3
    av.publish_listening_version(fake, 2, "admin-1")  # listening v1

    mock_v1 = av.publish_mock_version(fake, 7, "admin-1")
    assert mock_v1["version"] == 1
    assert mock_v1["snapshot"]["reading_test_version_id"] == reading_v3["id"]

    # Reading moves on to V4.
    reading_v4 = av.publish_reading_version(fake, 1, "admin-1")
    assert reading_v4["version"] == 4

    # Mock 7 Version 1's already-stored snapshot is untouched.
    reloaded_v1 = av.get_version_row(fake, "mock_test_versions", mock_v1["id"])
    assert reloaded_v1["snapshot"]["reading_test_version_id"] == reading_v3["id"]

    # Publishing Mock 7 Version 2 now picks up the new latest (V4).
    mock_v2 = av.publish_mock_version(fake, 7, "admin-1")
    assert mock_v2["version"] == 2
    assert mock_v2["snapshot"]["reading_test_version_id"] == reading_v4["id"]


# ── Version 1 backfill ────────────────────────────────────────────────

def test_backfill_creates_version_1_for_active_content():
    fake = _fake()
    _seed_reading_test(fake, test_id=1)
    _seed_listening_test(fake, test_id=2)
    _seed_mock_pack(fake, mock_test_id=7, reading_test_id=1, listening_test_id=2)
    fake.tables["reading_tests"][0]["is_active"] = True
    fake.tables["listening_tests"][0]["is_active"] = True

    result = av.backfill_versions(fake, "system")
    assert result["created"]["reading_tests"] == [1]
    assert result["created"]["listening_tests"] == [2]
    assert result["created"]["mock_tests"] == [7]
    assert av.latest_version_id(fake, "reading_test_versions", "reading_test_id", 1) is not None
    assert av.latest_version_id(fake, "mock_test_versions", "mock_test_id", 7) is not None


def test_backfill_is_idempotent_and_touches_no_live_content():
    fake = _fake()
    _seed_reading_test(fake, test_id=1)
    _seed_listening_test(fake, test_id=2)
    _seed_mock_pack(fake, mock_test_id=7, reading_test_id=1, listening_test_id=2)
    fake.tables["reading_tests"][0]["is_active"] = True
    fake.tables["listening_tests"][0]["is_active"] = True

    av.backfill_versions(fake, "system")
    live_passage_before = dict(fake.tables["reading_passages"][0])
    live_section_before = dict(fake.tables["listening_sections"][0])

    second = av.backfill_versions(fake, "system")
    assert second["created"] == {"reading_tests": [], "listening_tests": [], "mock_tests": []}
    assert second["skipped"]["reading_tests"] == [1]
    assert second["skipped"]["listening_tests"] == [2]
    assert second["skipped"]["mock_tests"] == [7]

    # No second Version 1 was minted, and live content rows are untouched.
    assert len(fake.tables["reading_test_versions"]) == 1
    assert len(fake.tables["listening_test_versions"]) == 1
    assert len(fake.tables["mock_test_versions"]) == 1
    assert fake.tables["reading_passages"][0] == live_passage_before
    assert fake.tables["listening_sections"][0] == live_section_before


def test_backfill_skips_inactive_content():
    fake = _fake()
    _seed_reading_test(fake, test_id=1)
    fake.tables["reading_tests"][0]["is_active"] = False  # draft, never published
    result = av.backfill_versions(fake, "system")
    assert result["created"]["reading_tests"] == []
    assert result["skipped"]["reading_tests"] == []  # not even considered -- inactive


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"{passed}/{len(tests)} assessment versioning checks passed")
