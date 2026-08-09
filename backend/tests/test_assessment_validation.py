"""RC4.2 -- deterministic publish-time validation (app.services.assessment_validation)
and its 409 gate on reading.py/listening.py's set_test_active and mock.py's
admin_publish_mock_test_version.

Three layers, matching assessment_validation.py's own split:
1. Pure content-validator unit tests (_validate_reading_content /
   _validate_listening_content / _validate_scenario) -- one rule at a time,
   no supabase.
2. Live-table wrapper tests (validate_reading_test / validate_listening_test /
   validate_mock_test) against a FakeSupabase -- same fixture-mutation style
   as test_reading_versioning.py/test_mock_versioning.py.
3. Endpoint-level integration tests proving the 409 gate itself: a failing
   publish creates no version row, never flips is_active, and touches
   nothing else -- and a valid publish is completely unaffected (RC4.1
   versioning behavior unchanged).
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

from app.services.assessment_validation import (
    _validate_reading_content, _validate_listening_content, _validate_scenario, _is_blank,
    validate_reading_test, validate_listening_test, validate_mock_test,
)

import app.routers.reading as reading_router
import app.routers.listening as listening_router
import app.routers.mock as mock_router
from app.routers.reading import SetActiveRequest as ReadingSetActiveRequest
from app.routers.listening import SetActiveRequest as ListeningSetActiveRequest


# ── shared fake supabase (same shape every RC4.1/RC4.2 test file uses) ────

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


_ADMIN = SimpleNamespace(id="admin-1", is_anonymous=False)


# ═══════════════════════════════════════════════════════════════════════
# 1. Pure content-validator unit tests -- one rule at a time
# ═══════════════════════════════════════════════════════════════════════

def _valid_passages():
    return [{"passage_id": 1, "title": "P1", "part": "A"}, {"passage_id": 2, "title": "P2", "part": "B"}, {"passage_id": 3, "title": "P3", "part": "C"}]


def _valid_reading_questions():
    return {
        1: [{"question_id": 10, "type": "short_answer", "content": "q1", "options": [], "correct_answer": "x"}],
        2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "b"], "correct_answer": "a"}],
        3: [{"question_id": 30, "type": "mcq", "content": "q3", "options": ["a", "b"], "correct_answer": "a"}],
    }


class TestReadingContentValidatorRules:
    def test_full_coverage_is_valid(self):
        errors, _ = _validate_reading_content(_valid_passages(), _valid_reading_questions())
        assert errors == []

    def test_missing_part_c(self):
        errors, _ = _validate_reading_content(_valid_passages()[:2], {1: _valid_reading_questions()[1], 2: _valid_reading_questions()[2]})
        assert any(e["code"] == "missing_part" and e["field"] == "part:C" for e in errors)

    def test_missing_part_a_and_b(self):
        errors, _ = _validate_reading_content(_valid_passages()[2:], {3: _valid_reading_questions()[3]})
        codes = {e["code"] for e in errors}
        fields = {e["field"] for e in errors}
        assert "missing_part" in codes
        assert {"part:A", "part:B"} <= fields

    def test_invalid_part_value(self):
        errors, _ = _validate_reading_content(
            [{**_valid_passages()[0], "part": "D"}] + _valid_passages()[1:],
            _valid_reading_questions(),
        )
        assert any(e["code"] == "invalid_part" for e in errors)

    def test_passage_with_no_questions(self):
        errors, _ = _validate_reading_content(_valid_passages(), {**_valid_reading_questions(), 2: []})
        assert any(e["code"] == "no_questions" and e["field"] == "passage:2" for e in errors)

    def test_mcq_too_few_options(self):
        errors, _ = _validate_reading_content(
            _valid_passages(), {**_valid_reading_questions(), 2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a"], "correct_answer": "a"}]},
        )
        assert any(e["code"] == "too_few_options" for e in errors)

    def test_blank_correct_answer_mcq(self):
        errors, _ = _validate_reading_content(
            _valid_passages(), {**_valid_reading_questions(), 2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "b"], "correct_answer": ""}]},
        )
        assert any(e["code"] == "blank_answer" for e in errors)

    def test_blank_correct_answer_short_answer(self):
        errors, _ = _validate_reading_content(
            _valid_passages(), {**_valid_reading_questions(), 1: [{"question_id": 10, "type": "short_answer", "content": "q1", "options": [], "correct_answer": "  "}]},
        )
        assert any(e["code"] == "blank_answer" for e in errors)

    def test_dangling_correct_answer(self):
        errors, _ = _validate_reading_content(
            _valid_passages(), {**_valid_reading_questions(), 2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "b"], "correct_answer": "c"}]},
        )
        assert any(e["code"] == "dangling_answer" for e in errors)

    def test_duplicate_option_text(self):
        errors, _ = _validate_reading_content(
            _valid_passages(), {**_valid_reading_questions(), 2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "a"], "correct_answer": "a"}]},
        )
        assert any(e["code"] == "duplicate_option" for e in errors)

    def test_duplicate_question_text_within_passage(self):
        errors, _ = _validate_reading_content(_valid_passages(), {**_valid_reading_questions(), 2: [
            {"question_id": 20, "type": "mcq", "content": "same text", "options": ["a", "b"], "correct_answer": "a"},
            {"question_id": 21, "type": "mcq", "content": "same text", "options": ["c", "d"], "correct_answer": "c"},
        ]})
        assert any(e["code"] == "duplicate_question_text" for e in errors)

    def test_invalid_question_type(self):
        errors, _ = _validate_reading_content(
            _valid_passages(), {**_valid_reading_questions(), 2: [{"question_id": 20, "type": "essay", "content": "q2", "options": ["a", "b"], "correct_answer": "a"}]},
        )
        assert any(e["code"] == "invalid_type" for e in errors)


def _valid_sections():
    return [
        {"section_id": 1, "title": "S1", "part": "A", "audio_url": "https://x/a.mp3"},
        {"section_id": 2, "title": "S2", "part": "B", "audio_url": "https://x/b.mp3"},
        {"section_id": 3, "title": "S3", "part": "C", "audio_url": "https://x/c.mp3"},
    ]


def _valid_listening_questions():
    return {
        1: [{"question_id": 10, "type": "short_answer", "content": "q1", "options": [], "correct_answer": "x"}],
        2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "b"], "correct_answer": "a"}],
        3: [{"question_id": 30, "type": "mcq", "content": "q3", "options": ["a", "b"], "correct_answer": "a"}],
    }


class TestListeningContentValidatorRules:
    def test_full_coverage_is_valid(self):
        errors, _ = _validate_listening_content(_valid_sections(), _valid_listening_questions())
        assert errors == []

    def test_missing_part(self):
        errors, _ = _validate_listening_content(_valid_sections()[:2], {1: _valid_listening_questions()[1], 2: _valid_listening_questions()[2]})
        assert any(e["code"] == "missing_part" and e["field"] == "part:C" for e in errors)

    def test_missing_audio(self):
        errors, _ = _validate_listening_content(
            [{**_valid_sections()[0], "audio_url": None}] + _valid_sections()[1:], _valid_listening_questions(),
        )
        assert any(e["code"] == "missing_audio" and e["field"] == "section:1" for e in errors)

    def test_missing_audio_blank_string(self):
        errors, _ = _validate_listening_content(
            [{**_valid_sections()[0], "audio_url": "   "}] + _valid_sections()[1:], _valid_listening_questions(),
        )
        assert any(e["code"] == "missing_audio" for e in errors)

    def test_section_with_no_questions(self):
        errors, _ = _validate_listening_content(_valid_sections(), {**_valid_listening_questions(), 2: []})
        assert any(e["code"] == "no_questions" and e["field"] == "section:2" for e in errors)

    def test_dangling_answer(self):
        errors, _ = _validate_listening_content(
            _valid_sections(), {**_valid_listening_questions(), 2: [{"question_id": 20, "type": "mcq", "content": "q2", "options": ["a", "b"], "correct_answer": "z"}]},
        )
        assert any(e["code"] == "dangling_answer" for e in errors)

    def test_duplicate_question_text_within_section(self):
        errors, _ = _validate_listening_content(_valid_sections(), {**_valid_listening_questions(), 2: [
            {"question_id": 20, "type": "mcq", "content": "same", "options": ["a", "b"], "correct_answer": "a"},
            {"question_id": 21, "type": "mcq", "content": "same", "options": ["a", "b"], "correct_answer": "a"},
        ]})
        assert any(e["code"] == "duplicate_question_text" for e in errors)


class TestIsBlankAndScenarioValidator:
    def test_is_blank_none(self):
        assert _is_blank(None) is True

    def test_is_blank_empty_string(self):
        assert _is_blank("   ") is True

    def test_is_blank_non_empty_string(self):
        assert _is_blank("hello") is False

    def test_is_blank_empty_dict(self):
        assert _is_blank({}) is True

    def test_is_blank_non_empty_dict(self):
        assert _is_blank({"task": "x"}) is False

    def test_is_blank_empty_list(self):
        assert _is_blank([]) is True

    def test_scenario_missing_row(self):
        errors = _validate_scenario(None, "writing_scenario", ["nurse_card"])
        assert errors[0]["code"] == "slot_empty"

    def test_scenario_inactive(self):
        errors = _validate_scenario({"id": 1, "is_active": False, "nurse_card": {"a": 1}}, "writing_scenario", ["nurse_card"])
        assert any(e["code"] == "scenario_inactive" for e in errors)

    def test_scenario_missing_field(self):
        errors = _validate_scenario({"id": 1, "is_active": True, "nurse_card": {}}, "writing_scenario", ["nurse_card"])
        assert any(e["code"] == "scenario_missing_field" and e["details"]["field"] == "nurse_card" for e in errors)

    def test_scenario_fully_valid(self):
        errors = _validate_scenario({"id": 1, "is_active": True, "nurse_card": {"task": "x"}}, "writing_scenario", ["nurse_card"])
        assert errors == []


# ═══════════════════════════════════════════════════════════════════════
# 2. Live-table wrapper tests (validate_reading_test / validate_listening_test
#    / validate_mock_test against a FakeSupabase)
# ═══════════════════════════════════════════════════════════════════════

def _seed_valid_reading(fake, test_id=1):
    fake.tables.setdefault("reading_passages", []).extend([
        {"id": 10 + test_id * 100, "title": "P1", "part": "A", "difficulty": "intermediate", "body": "a", "test_id": test_id, "is_active": True},
        {"id": 11 + test_id * 100, "title": "P2", "part": "B", "difficulty": "intermediate", "body": "b", "test_id": test_id, "is_active": True},
        {"id": 12 + test_id * 100, "title": "P3", "part": "C", "difficulty": "intermediate", "body": "c", "test_id": test_id, "is_active": True},
    ])
    fake.tables.setdefault("questions", []).extend([
        {"id": 1000 + test_id * 100, "passage_id": 10 + test_id * 100, "type": "mcq", "content": "qa", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
        {"id": 1001 + test_id * 100, "passage_id": 11 + test_id * 100, "type": "mcq", "content": "qb", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
        {"id": 1002 + test_id * 100, "passage_id": 12 + test_id * 100, "type": "mcq", "content": "qc", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
    ])


def _seed_valid_listening(fake, test_id=2):
    fake.tables.setdefault("listening_sections", []).extend([
        {"id": 20 + test_id * 100, "title": "S1", "part": "A", "difficulty": "intermediate", "body": None, "transcript": None, "test_id": test_id, "is_active": True, "audio_url": "https://x/a.mp3"},
        {"id": 21 + test_id * 100, "title": "S2", "part": "B", "difficulty": "intermediate", "body": None, "transcript": None, "test_id": test_id, "is_active": True, "audio_url": "https://x/b.mp3"},
        {"id": 22 + test_id * 100, "title": "S3", "part": "C", "difficulty": "intermediate", "body": None, "transcript": None, "test_id": test_id, "is_active": True, "audio_url": "https://x/c.mp3"},
    ])
    fake.tables.setdefault("questions", []).extend([
        {"id": 2000 + test_id * 100, "section_id": 20 + test_id * 100, "type": "mcq", "content": "qa", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
        {"id": 2001 + test_id * 100, "section_id": 21 + test_id * 100, "type": "mcq", "content": "qb", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
        {"id": 2002 + test_id * 100, "section_id": 22 + test_id * 100, "type": "mcq", "content": "qc", "options": json.dumps(["a", "b"]), "correct_answer": "a"},
    ])


class TestValidateReadingTestWrapper:
    def test_valid_test_passes(self):
        fake = FakeSupabase()
        _seed_valid_reading(fake, test_id=1)
        result = validate_reading_test(fake, 1)
        assert result["valid"] is True
        assert result["errors"] == []

    def test_incomplete_test_fails(self):
        fake = FakeSupabase()
        fake.tables["reading_passages"] = [{"id": 10, "title": "Only B", "part": "B", "test_id": 1, "is_active": True}]
        fake.tables["questions"] = [{"id": 100, "passage_id": 10, "type": "mcq", "content": "q", "options": json.dumps(["a", "b"]), "correct_answer": "a"}]
        result = validate_reading_test(fake, 1)
        assert result["valid"] is False
        assert any(e["code"] == "missing_part" for e in result["errors"])

    def test_inactive_passage_not_counted(self):
        """An inactive passage doesn't count toward part coverage -- matches
        assessment_versioning.build_reading_snapshot which only freezes
        is_active passages, so validation must check exactly what publish
        would freeze."""
        fake = FakeSupabase()
        _seed_valid_reading(fake, test_id=1)
        fake.tables["reading_passages"][0]["is_active"] = False  # Part A now hidden
        result = validate_reading_test(fake, 1)
        assert result["valid"] is False
        assert any(e["code"] == "missing_part" and e["field"] == "part:A" for e in result["errors"])


class TestValidateListeningTestWrapper:
    def test_valid_test_passes(self):
        fake = FakeSupabase()
        _seed_valid_listening(fake, test_id=2)
        result = validate_listening_test(fake, 2)
        assert result["valid"] is True

    def test_missing_audio_fails(self):
        fake = FakeSupabase()
        _seed_valid_listening(fake, test_id=2)
        fake.tables["listening_sections"][0]["audio_url"] = None
        result = validate_listening_test(fake, 2)
        assert result["valid"] is False
        assert any(e["code"] == "missing_audio" for e in result["errors"])


def _seed_valid_scenarios(fake):
    fake.tables["scenarios"] = [
        {"id": 300, "module": "writing", "title": "W1", "is_active": True, "nurse_card": {"task": "x"}, "scoring_criteria": {"r": 1}},
        {"id": 301, "module": "speaking", "title": "S1", "is_active": True, "nurse_card": {"task": "x"}, "interlocutor_card": {"p": 1}, "scoring_criteria": {"r": 1}},
        {"id": 302, "module": "speaking", "title": "S2", "is_active": True, "nurse_card": {"task": "x"}, "interlocutor_card": {"p": 1}, "scoring_criteria": {"r": 1}},
    ]


def _seed_valid_mock(fake, mock_id=1, reading_id=1, listening_id=2):
    from app.services.assessment_versioning import publish_reading_version, publish_listening_version
    _seed_valid_reading(fake, test_id=reading_id)
    _seed_valid_listening(fake, test_id=listening_id)
    _seed_valid_scenarios(fake)
    fake.tables["reading_tests"] = [{"id": reading_id, "title": "R", "is_active": True}]
    fake.tables["listening_tests"] = [{"id": listening_id, "title": "L", "is_active": True, "part_audio": {}, "part_audio_times": {}}]
    fake.tables["mock_tests"] = [{
        "id": mock_id, "label": "Mock 1",
        "reading_test_id": reading_id, "listening_test_id": listening_id,
        "writing_scenario_id": 300, "speaking_scenario_id_1": 301, "speaking_scenario_id_2": 302,
    }]
    publish_reading_version(fake, reading_id, "admin-1")
    publish_listening_version(fake, listening_id, "admin-1")


class TestValidateMockTestWrapper:
    def test_fully_valid_pack_passes(self):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        result = validate_mock_test(fake, 1)
        assert result["valid"] is True, result["errors"]

    def test_empty_slot_fails(self):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["mock_tests"][0]["writing_scenario_id"] = None
        result = validate_mock_test(fake, 1)
        assert any(e["code"] == "slot_empty" and e["field"] == "writing_scenario" for e in result["errors"])

    def test_referenced_reading_invalid_fails(self):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        # Break the referenced Reading test's own content after it was published.
        fake.tables["reading_passages"] = [p for p in fake.tables["reading_passages"] if p["part"] != "C"]
        result = validate_mock_test(fake, 1)
        assert not result["valid"]
        assert any(e["code"] == "reading_test_invalid" for e in result["errors"])
        assert any(e["field"].startswith("reading_test.") for e in result["errors"])

    def test_referenced_listening_invalid_fails(self):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["listening_sections"][0]["audio_url"] = None
        result = validate_mock_test(fake, 1)
        assert not result["valid"]
        assert any(e["code"] == "listening_test_invalid" for e in result["errors"])

    def test_reading_never_published_fails(self):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["reading_test_versions"] = []  # never published
        result = validate_mock_test(fake, 1)
        assert any(e["code"] == "reading_unpublished" for e in result["errors"])

    def test_listening_never_published_fails(self):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["listening_test_versions"] = []
        result = validate_mock_test(fake, 1)
        assert any(e["code"] == "listening_unpublished" for e in result["errors"])

    def test_inactive_writing_scenario_fails(self):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["scenarios"][0]["is_active"] = False
        result = validate_mock_test(fake, 1)
        assert any(e["code"] == "scenario_inactive" and e["field"] == "writing_scenario" for e in result["errors"])

    def test_missing_writing_field_fails(self):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["scenarios"][0]["scoring_criteria"] = {}
        result = validate_mock_test(fake, 1)
        assert any(e["code"] == "scenario_missing_field" and e["field"] == "writing_scenario" for e in result["errors"])

    def test_duplicate_speaking_scenario_ids_fails(self):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["mock_tests"][0]["speaking_scenario_id_2"] = 301  # same as speaking_scenario_id_1
        result = validate_mock_test(fake, 1)
        assert any(e["code"] == "duplicate_speaking_scenario" for e in result["errors"])

    def test_not_found_pack(self):
        fake = FakeSupabase()
        result = validate_mock_test(fake, 999)
        assert result["valid"] is False
        assert result["errors"][0]["code"] == "not_found"


# ═══════════════════════════════════════════════════════════════════════
# 3. Endpoint-level 409 gate: no version row, is_active unchanged, no
#    partial writes on failure; valid publish unaffected (RC4.1 unchanged).
# ═══════════════════════════════════════════════════════════════════════

def _seeded_reading_fake(complete=True):
    fake = FakeSupabase()
    fake.tables["reading_tests"] = [{"id": 1, "title": "Reading 1", "is_active": False}]
    if complete:
        _seed_valid_reading(fake, test_id=1)
    else:
        fake.tables["reading_passages"] = [{"id": 10, "title": "Only B", "part": "B", "test_id": 1, "is_active": True}]
        fake.tables["questions"] = [{"id": 100, "passage_id": 10, "type": "mcq", "content": "q", "options": json.dumps(["a", "b"]), "correct_answer": "a"}]
    return fake


class TestReadingPublishGate:
    def test_incomplete_reading_409s_and_writes_nothing(self, monkeypatch):
        fake = _seeded_reading_fake(complete=False)
        monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            reading_router.set_test_active(1, ReadingSetActiveRequest(is_active=True), admin=_ADMIN)
        assert exc.value.status_code == 409
        assert exc.value.detail["valid"] is False
        assert fake.tables.get("reading_test_versions", []) == []
        assert fake.tables["reading_tests"][0]["is_active"] is False

    def test_blank_answer_409s(self, monkeypatch):
        fake = _seeded_reading_fake(complete=True)
        fake.tables["questions"][0]["correct_answer"] = None
        monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            reading_router.set_test_active(1, ReadingSetActiveRequest(is_active=True), admin=_ADMIN)
        assert exc.value.status_code == 409
        assert any(e["code"] == "blank_answer" for e in exc.value.detail["errors"])
        assert fake.tables.get("reading_test_versions", []) == []

    def test_dangling_answer_409s(self, monkeypatch):
        fake = _seeded_reading_fake(complete=True)
        fake.tables["questions"][0]["correct_answer"] = "not-an-option"
        monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            reading_router.set_test_active(1, ReadingSetActiveRequest(is_active=True), admin=_ADMIN)
        assert exc.value.status_code == 409
        assert any(e["code"] == "dangling_answer" for e in exc.value.detail["errors"])

    def test_duplicate_options_409s(self, monkeypatch):
        fake = _seeded_reading_fake(complete=True)
        fake.tables["questions"][0]["options"] = json.dumps(["a", "a"])
        monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            reading_router.set_test_active(1, ReadingSetActiveRequest(is_active=True), admin=_ADMIN)
        assert any(e["code"] == "duplicate_option" for e in exc.value.detail["errors"])

    def test_duplicate_question_text_409s(self, monkeypatch):
        fake = _seeded_reading_fake(complete=True)
        fake.tables["questions"].append({
            "id": 9999, "passage_id": fake.tables["questions"][0]["passage_id"], "type": "mcq",
            "content": fake.tables["questions"][0]["content"], "options": json.dumps(["c", "d"]), "correct_answer": "c",
        })
        monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            reading_router.set_test_active(1, ReadingSetActiveRequest(is_active=True), admin=_ADMIN)
        assert any(e["code"] == "duplicate_question_text" for e in exc.value.detail["errors"])

    def test_missing_question_409s(self, monkeypatch):
        fake = _seeded_reading_fake(complete=True)
        first_passage_id = fake.tables["questions"][0]["passage_id"]
        fake.tables["questions"] = [q for q in fake.tables["questions"] if q["passage_id"] != first_passage_id]
        monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            reading_router.set_test_active(1, ReadingSetActiveRequest(is_active=True), admin=_ADMIN)
        assert any(e["code"] == "no_questions" for e in exc.value.detail["errors"])

    def test_valid_reading_publishes_exactly_as_rc41(self, monkeypatch):
        """Unaffected happy path -- proves RC4.2 didn't touch RC4.1's own
        version-cut mechanics, only gates the call to it."""
        fake = _seeded_reading_fake(complete=True)
        monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
        result = reading_router.set_test_active(1, ReadingSetActiveRequest(is_active=True), admin=_ADMIN)
        assert result == {"success": True, "is_active": True}
        assert len(fake.tables["reading_test_versions"]) == 1
        assert fake.tables["reading_tests"][0]["is_active"] is True

    def test_unpublish_never_gated_even_when_incomplete(self, monkeypatch):
        fake = _seeded_reading_fake(complete=False)
        fake.tables["reading_tests"][0]["is_active"] = True
        monkeypatch.setattr(reading_router, "get_supabase", lambda: fake)
        result = reading_router.set_test_active(1, ReadingSetActiveRequest(is_active=False), admin=_ADMIN)
        assert result == {"success": True, "is_active": False}


def _seeded_listening_fake(complete=True):
    fake = FakeSupabase()
    fake.tables["listening_tests"] = [{"id": 2, "title": "Listening 1", "is_active": False, "part_audio": {}, "part_audio_times": {}}]
    if complete:
        _seed_valid_listening(fake, test_id=2)
    else:
        fake.tables["listening_sections"] = [{"id": 20, "title": "Only B", "part": "B", "test_id": 2, "is_active": True, "audio_url": "https://x/b.mp3"}]
        fake.tables["questions"] = [{"id": 200, "section_id": 20, "type": "mcq", "content": "q", "options": json.dumps(["a", "b"]), "correct_answer": "a"}]
    return fake


class TestListeningPublishGate:
    def test_incomplete_listening_409s_and_writes_nothing(self, monkeypatch):
        fake = _seeded_listening_fake(complete=False)
        monkeypatch.setattr(listening_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            listening_router.set_test_active(2, ListeningSetActiveRequest(is_active=True), admin=_ADMIN)
        assert exc.value.status_code == 409
        assert fake.tables.get("listening_test_versions", []) == []
        assert fake.tables["listening_tests"][0]["is_active"] is False

    def test_missing_audio_409s(self, monkeypatch):
        fake = _seeded_listening_fake(complete=True)
        fake.tables["listening_sections"][0]["audio_url"] = None
        monkeypatch.setattr(listening_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            listening_router.set_test_active(2, ListeningSetActiveRequest(is_active=True), admin=_ADMIN)
        assert exc.value.status_code == 409
        assert any(e["code"] == "missing_audio" for e in exc.value.detail["errors"])
        assert fake.tables.get("listening_test_versions", []) == []

    def test_valid_listening_publishes_exactly_as_rc41(self, monkeypatch):
        fake = _seeded_listening_fake(complete=True)
        monkeypatch.setattr(listening_router, "get_supabase", lambda: fake)
        result = listening_router.set_test_active(2, ListeningSetActiveRequest(is_active=True), admin=_ADMIN)
        assert result == {"success": True, "is_active": True}
        assert len(fake.tables["listening_test_versions"]) == 1


class TestMockPublishGate:
    def test_incomplete_mock_409s_and_writes_nothing(self, monkeypatch):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["mock_tests"][0]["writing_scenario_id"] = None
        monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
        versions_before = len(fake.tables.get("mock_test_versions", []))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mock_router.admin_publish_mock_test_version(1, current_user=_ADMIN))
        assert exc.value.status_code == 409
        assert len(fake.tables.get("mock_test_versions", [])) == versions_before

    def test_referenced_reading_invalid_409s(self, monkeypatch):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["reading_passages"] = [p for p in fake.tables["reading_passages"] if p["part"] != "C"]
        monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mock_router.admin_publish_mock_test_version(1, current_user=_ADMIN))
        assert exc.value.status_code == 409
        assert any(e["code"] == "reading_test_invalid" for e in exc.value.detail["errors"])

    def test_referenced_listening_invalid_409s(self, monkeypatch):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["listening_sections"][0]["audio_url"] = None
        monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mock_router.admin_publish_mock_test_version(1, current_user=_ADMIN))
        assert exc.value.status_code == 409
        assert any(e["code"] == "listening_test_invalid" for e in exc.value.detail["errors"])

    def test_reading_unpublished_409s(self, monkeypatch):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["reading_test_versions"] = []
        monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mock_router.admin_publish_mock_test_version(1, current_user=_ADMIN))
        assert any(e["code"] == "reading_unpublished" for e in exc.value.detail["errors"])

    def test_listening_unpublished_409s(self, monkeypatch):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["listening_test_versions"] = []
        monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mock_router.admin_publish_mock_test_version(1, current_user=_ADMIN))
        assert any(e["code"] == "listening_unpublished" for e in exc.value.detail["errors"])

    def test_inactive_speaking_scenario_409s(self, monkeypatch):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["scenarios"][1]["is_active"] = False  # speaking_scenario_id_1
        monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mock_router.admin_publish_mock_test_version(1, current_user=_ADMIN))
        assert any(e["code"] == "scenario_inactive" and e["field"] == "speaking_scenario_1" for e in exc.value.detail["errors"])

    def test_duplicate_speaking_ids_409s(self, monkeypatch):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        fake.tables["mock_tests"][0]["speaking_scenario_id_2"] = fake.tables["mock_tests"][0]["speaking_scenario_id_1"]
        monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mock_router.admin_publish_mock_test_version(1, current_user=_ADMIN))
        assert any(e["code"] == "duplicate_speaking_scenario" for e in exc.value.detail["errors"])

    def test_valid_mock_publishes_exactly_as_rc41(self, monkeypatch):
        fake = FakeSupabase()
        _seed_valid_mock(fake)
        monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
        result = asyncio.run(mock_router.admin_publish_mock_test_version(1, current_user=_ADMIN))
        assert result["version"] == 1
        assert len(fake.tables["mock_test_versions"]) == 1

    def test_still_404s_for_unknown_pack_before_validation_runs(self, monkeypatch):
        fake = FakeSupabase()
        monkeypatch.setattr(mock_router, "get_supabase", lambda: fake)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(mock_router.admin_publish_mock_test_version(999, current_user=_ADMIN))
        assert exc.value.status_code == 404


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
