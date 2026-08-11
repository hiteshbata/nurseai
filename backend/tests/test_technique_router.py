import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.routers import technique
from app.services import technique_grading


def _run(coro):
    return asyncio.run(coro)


class FakeQuery:
    def __init__(self, rows, on_insert=None):
        self._rows = rows
        self._filters = []
        self._on_insert = on_insert

    def select(self, columns="*", **_k):
        self._columns = [c.strip() for c in columns.split(",")] if columns and columns != "*" else None
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

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, row):
        if self._on_insert is not None:
            self._on_insert(row)
        return FakeQuery([row])

    def execute(self):
        rows = [r for r in self._rows if all(f(r) for f in self._filters)]
        if getattr(self, "_limit", None) is not None:
            rows = rows[: self._limit]
        columns = getattr(self, "_columns", None)
        if columns:
            rows = [{c: r[c] for c in columns if c in r} for r in rows]
        return SimpleNamespace(data=rows)


class FakeSupabase:
    def __init__(self, tables, inserted=None):
        self._tables = tables
        self._inserted = inserted if inserted is not None else {}

    def table(self, name):
        return FakeQuery(self._tables.get(name, []), on_insert=self._inserted.setdefault(name, []).append)


def _fake(tables, inserted):
    return FakeSupabase(tables, inserted)


_USER = SimpleNamespace(id="student-1", is_anonymous=False)
_OTHER_USER = SimpleNamespace(id="student-2", is_anonymous=False)

_TECHNIQUES = [
    {"id": 1, "module": "reading", "skill_tag": "skimming", "slug": "skimming", "name": "Skimming",
     "description": "d", "learning_objective": "o", "difficulty": "easy", "estimated_minutes": 4,
     "sort_order": 1, "active": True, "lesson_content": {"what": "..."}},
    {"id": 2, "module": "reading", "skill_tag": "scanning", "slug": "scanning", "name": "Scanning",
     "description": "d", "learning_objective": "o", "difficulty": "easy", "estimated_minutes": 4,
     "sort_order": 2, "active": True, "lesson_content": {"what": "..."}},
    {"id": 3, "module": "listening", "skill_tag": "pre_listening", "slug": "pre-listening", "name": "Pre-listening",
     "description": "d", "learning_objective": "o", "difficulty": "easy", "estimated_minutes": 3,
     "sort_order": 1, "active": True, "lesson_content": {"what": "..."}},
]

_MICRO_PRACTICES = [
    {"id": 10, "technique_id": 1, "title": "Skim it", "instructions": "go", "active": True,
     "content": {"passage": "p", "options": ["A", "B"]},
     "expected_response": {"correct_answer": "A"}, "scoring_type": "rule_based"},
]

_STATS = [
    {"user_id": "student-1", "skill_tag": "technique:skimming", "attempts": 3, "ema_score": 5.5},
]


def _tables(techniques=None, micro_practices=None, stats=None):
    return {
        "techniques": techniques if techniques is not None else _TECHNIQUES,
        "micro_practices": micro_practices if micro_practices is not None else _MICRO_PRACTICES,
        "user_skill_stats": stats if stats is not None else _STATS,
    }


def test_list_techniques_includes_every_module_and_mastery():
    supabase = _fake(_tables(), {})
    with patch.object(technique, "get_supabase", return_value=supabase):
        result = technique.list_techniques(current_user=_USER, user_db=supabase)
    by_slug = {r["slug"]: r for r in result}
    assert set(by_slug) == {"skimming", "scanning", "pre-listening"}
    assert by_slug["skimming"]["mastery"] == {"level": "strong", "attempts": 3, "band": 5.5}
    assert by_slug["scanning"]["mastery"] == {"level": "not_started", "attempts": 0, "band": None}


def test_get_technique_returns_lesson_and_withheld_practice():
    supabase = _fake(_tables(), {})
    with patch.object(technique, "get_supabase", return_value=supabase):
        result = technique.get_technique("skimming", current_user=_USER, user_db=supabase)
    assert result["slug"] == "skimming"
    assert result["lesson_content"] == {"what": "..."}
    assert result["practice"]["id"] == 10
    assert "expected_response" not in result["practice"]  # never leak the answer key


def test_get_technique_without_seeded_practice_returns_null_practice_not_an_error():
    supabase = _fake(_tables(micro_practices=[]), {})
    with patch.object(technique, "get_supabase", return_value=supabase):
        result = technique.get_technique("pre-listening", current_user=_USER, user_db=supabase)
    assert result["practice"] is None


def test_get_technique_unknown_slug_404s():
    supabase = _fake(_tables(), {})
    with patch.object(technique, "get_supabase", return_value=supabase):
        try:
            technique.get_technique("does-not-exist", current_user=_USER, user_db=supabase)
            assert False, "expected 404"
        except HTTPException as e:
            assert e.status_code == 404


def test_submit_attempt_correct_answer_grades_and_records():
    inserted = {"practice_attempts": []}
    supabase = _fake(_tables(stats=[]), inserted)
    req = technique.TechniqueAttemptRequest(micro_practice_id=10, answer="A")
    with patch.object(technique, "get_supabase", return_value=supabase), \
         patch.object(technique.technique_progress, "record_technique_progress", new=AsyncMock()) as record_mock:
        result = _run(technique.submit_technique_attempt("skimming", req, current_user=_USER, user_db=supabase))

    assert result["score"] == 6.0
    assert result["feedback"]["is_correct"] is True
    assert result["mistakes"] == []
    record_mock.assert_called_once_with("student-1", "skimming", 6.0)
    assert len(inserted["practice_attempts"]) == 1
    saved = inserted["practice_attempts"][0]
    assert saved["user_id"] == "student-1"  # always the caller, never client-supplied
    assert saved["technique_id"] == 1
    assert saved["micro_practice_id"] == 10


def test_submit_attempt_wrong_answer_records_a_mistake():
    inserted = {"practice_attempts": []}
    supabase = _fake(_tables(stats=[]), inserted)
    req = technique.TechniqueAttemptRequest(micro_practice_id=10, answer="B")
    with patch.object(technique, "get_supabase", return_value=supabase), \
         patch.object(technique.technique_progress, "record_technique_progress", new=AsyncMock()):
        result = _run(technique.submit_technique_attempt("skimming", req, current_user=_USER, user_db=supabase))

    assert result["score"] == 0.0
    assert result["mistakes"] == [{"reason": "incorrect_selection", "expected": "A", "given": "B"}]


def test_submit_attempt_ownership_always_uses_the_authenticated_caller():
    # Even if two different users submit against the same technique/practice
    # in sequence, each attempt is recorded under its own caller -- nothing
    # in the request lets a learner write into another user's row.
    inserted = {"practice_attempts": []}
    supabase = _fake(_tables(stats=[]), inserted)
    req = technique.TechniqueAttemptRequest(micro_practice_id=10, answer="A")
    with patch.object(technique, "get_supabase", return_value=supabase), \
         patch.object(technique.technique_progress, "record_technique_progress", new=AsyncMock()):
        _run(technique.submit_technique_attempt("skimming", req, current_user=_USER, user_db=supabase))
        _run(technique.submit_technique_attempt("skimming", req, current_user=_OTHER_USER, user_db=supabase))

    assert [row["user_id"] for row in inserted["practice_attempts"]] == ["student-1", "student-2"]


def test_submit_attempt_unknown_technique_404s():
    supabase = _fake(_tables(), {"practice_attempts": []})
    req = technique.TechniqueAttemptRequest(micro_practice_id=10, answer="A")
    with patch.object(technique, "get_supabase", return_value=supabase):
        try:
            _run(technique.submit_technique_attempt("does-not-exist", req, current_user=_USER, user_db=supabase))
            assert False, "expected 404"
        except HTTPException as e:
            assert e.status_code == 404


def test_submit_attempt_practice_id_not_belonging_to_technique_404s():
    # Malformed/tampered input: micro_practice_id valid, but for a different
    # technique than the one in the URL.
    supabase = _fake(_tables(), {"practice_attempts": []})
    req = technique.TechniqueAttemptRequest(micro_practice_id=10, answer="A")
    with patch.object(technique, "get_supabase", return_value=supabase):
        try:
            _run(technique.submit_technique_attempt("scanning", req, current_user=_USER, user_db=supabase))
            assert False, "expected 404"
        except HTTPException as e:
            assert e.status_code == 404


def test_submit_attempt_unknown_practice_id_404s():
    supabase = _fake(_tables(), {"practice_attempts": []})
    req = technique.TechniqueAttemptRequest(micro_practice_id=999, answer="A")
    with patch.object(technique, "get_supabase", return_value=supabase):
        try:
            _run(technique.submit_technique_attempt("skimming", req, current_user=_USER, user_db=supabase))
            assert False, "expected 404"
        except HTTPException as e:
            assert e.status_code == 404


def test_submit_attempt_invalid_scoring_type_returns_503_not_a_crash():
    bad_mp = [{**_MICRO_PRACTICES[0], "scoring_type": "essay_writing"}]
    supabase = _fake(_tables(micro_practices=bad_mp), {"practice_attempts": []})
    req = technique.TechniqueAttemptRequest(micro_practice_id=10, answer="A")
    with patch.object(technique, "get_supabase", return_value=supabase):
        try:
            _run(technique.submit_technique_attempt("skimming", req, current_user=_USER, user_db=supabase))
            assert False, "expected 503"
        except HTTPException as e:
            assert e.status_code == 503


def test_submit_attempt_rate_limited_returns_429():
    supabase = _fake(_tables(), {"practice_attempts": []})
    req = technique.TechniqueAttemptRequest(micro_practice_id=10, answer="A")
    with patch.object(technique, "get_supabase", return_value=supabase), \
         patch.object(technique._attempt_rate_limiter, "is_rate_limited", return_value=True):
        try:
            _run(technique.submit_technique_attempt("skimming", req, current_user=_USER, user_db=supabase))
            assert False, "expected 429"
        except HTTPException as e:
            assert e.status_code == 429


def test_submit_attempt_missing_answer_grades_as_incorrect_not_a_crash():
    # answer defaults to None if omitted -- must grade cleanly as wrong,
    # never raise or false-positive as correct.
    inserted = {"practice_attempts": []}
    supabase = _fake(_tables(stats=[]), inserted)
    req = technique.TechniqueAttemptRequest(micro_practice_id=10)
    with patch.object(technique, "get_supabase", return_value=supabase), \
         patch.object(technique.technique_progress, "record_technique_progress", new=AsyncMock()):
        result = _run(technique.submit_technique_attempt("skimming", req, current_user=_USER, user_db=supabase))
    assert result["feedback"]["is_correct"] is False


def test_submit_attempt_retry_after_a_wrong_answer_records_a_second_attempt_not_an_overwrite():
    inserted = {"practice_attempts": []}
    supabase = _fake(_tables(stats=[]), inserted)
    wrong = technique.TechniqueAttemptRequest(micro_practice_id=10, answer="B")
    right = technique.TechniqueAttemptRequest(micro_practice_id=10, answer="A")
    with patch.object(technique, "get_supabase", return_value=supabase), \
         patch.object(technique.technique_progress, "record_technique_progress", new=AsyncMock()):
        _run(technique.submit_technique_attempt("skimming", wrong, current_user=_USER, user_db=supabase))
        _run(technique.submit_technique_attempt("skimming", right, current_user=_USER, user_db=supabase))

    assert len(inserted["practice_attempts"]) == 2
    assert [row["score"] for row in inserted["practice_attempts"]] == [0.0, 6.0]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
