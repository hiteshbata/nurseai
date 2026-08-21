"""E2.2 integration -- Wrong-Answer Notebook enrichment with mistake `pattern`.

GET /listening/mistakes stays built entirely from submissions.feedback (E2.1
storage untouched); this only adds a `pattern` field per item, sourced from
listening_mistake_intelligence.get_mistake_profile(). Enrichment is best-effort:
a profile failure must not break the notebook (still 200, pattern=None).
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import listening


def _run(coro):
    return asyncio.run(coro)


class FakeQuery:
    def __init__(self, rows):
        self._filtered = list(rows)
        self._limit = None
        self._order_col = None
        self._desc = False

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) == val]
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self._filtered = [r for r in self._filtered if r.get(col) in vals]
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = self._filtered
        if self._order_col:
            rows = sorted(rows, key=lambda r: r.get(self._order_col), reverse=self._desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows)


class FakeSupabase:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return FakeQuery(self._tables.get(name, []))


def _submission(user_id, results, created_at="2026-08-01T00:00:00Z"):
    return {
        "user_id": user_id,
        "module": "listening",
        "created_at": created_at,
        "feedback": json.dumps({"results": results}),
    }


def _question(qid, section_id=1):
    return {
        "id": qid, "content": f"Q{qid}", "options": json.dumps(["A", "B"]),
        "correct_answer": "A", "section_id": section_id, "explanation": None,
    }


def _mistake_event(id, user_id, question_id, is_correct, part="A"):
    return {
        "id": id, "user_id": user_id, "question_id": question_id, "part": part,
        "is_correct": is_correct, "selected_option": "B", "correct_answer": "A",
        "created_at": "2026-08-01T00:00:00Z",
    }


_SECTIONS = [{"id": 1, "title": "Sec 1"}]
_USER = SimpleNamespace(id="student-1", is_anonymous=False)
_OTHER = SimpleNamespace(id="student-2", is_anonymous=False)


def _fake(submissions, questions, mistake_events):
    return FakeSupabase({
        "submissions": submissions,
        "questions": questions,
        "listening_sections": _SECTIONS,
        "listening_mistake_events": mistake_events,
    })


def test_persistent_question_gets_persistent_pattern():
    subs = [_submission("student-1", [{"questionId": 100, "is_correct": False, "selected": "B"}])]
    events = [_mistake_event(i, "student-1", 100, False) for i in range(1, 4)]  # 3x wrong
    supabase = _fake(subs, [_question(100)], events)
    with patch.object(listening, "get_supabase", return_value=supabase):
        result = _run(listening.list_mistakes(current_user=_USER, user_db=supabase))
    assert result[0]["pattern"] == "persistent"


def test_repeated_but_not_persistent_gets_repeated_pattern():
    subs = [_submission("student-1", [{"questionId": 200, "is_correct": False, "selected": "B"}])]
    events = [_mistake_event(1, "student-1", 200, False), _mistake_event(2, "student-1", 200, False)]  # 2x wrong
    supabase = _fake(subs, [_question(200)], events)
    with patch.object(listening, "get_supabase", return_value=supabase):
        result = _run(listening.list_mistakes(current_user=_USER, user_db=supabase))
    assert result[0]["pattern"] == "repeated"


def test_one_off_wrong_gets_null_pattern():
    subs = [_submission("student-1", [{"questionId": 300, "is_correct": False, "selected": "B"}])]
    events = [_mistake_event(1, "student-1", 300, False)]  # 1x wrong
    supabase = _fake(subs, [_question(300)], events)
    with patch.object(listening, "get_supabase", return_value=supabase):
        result = _run(listening.list_mistakes(current_user=_USER, user_db=supabase))
    assert result[0]["pattern"] is None


def test_corrected_mistake_not_in_current_wrong_answer_list():
    # Latest submission has it right -- resolve_latest_wrong_answers drops it
    # entirely regardless of what mistake intelligence says about its history.
    subs = [_submission("student-1", [{"questionId": 400, "is_correct": True, "selected": "A"}])]
    events = [_mistake_event(1, "student-1", 400, False), _mistake_event(2, "student-1", 400, True)]
    supabase = _fake(subs, [_question(400)], events)
    with patch.object(listening, "get_supabase", return_value=supabase):
        result = _run(listening.list_mistakes(current_user=_USER, user_db=supabase))
    assert result == []


def test_existing_response_fields_unchanged_alongside_new_pattern_field():
    subs = [_submission("student-1", [{"questionId": 100, "is_correct": False, "selected": "B"}])]
    supabase = _fake(subs, [_question(100)], [])
    with patch.object(listening, "get_supabase", return_value=supabase):
        result = _run(listening.list_mistakes(current_user=_USER, user_db=supabase))
    item = result[0]
    assert item["questionId"] == 100
    assert item["content"] == "Q100"
    assert item["options"] == ["A", "B"]
    assert item["correct_answer"] == "A"
    assert item["your_answer"] == "B"
    assert item["section_title"] == "Sec 1"
    assert item["explanation"] is None
    assert set(item.keys()) == {
        "questionId", "content", "options", "correct_answer",
        "your_answer", "section_title", "explanation", "pattern",
    }


def test_empty_mistake_profile_gives_null_pattern():
    subs = [_submission("student-1", [{"questionId": 100, "is_correct": False, "selected": "B"}])]
    supabase = _fake(subs, [_question(100)], [])  # no mistake events at all
    with patch.object(listening, "get_supabase", return_value=supabase):
        result = _run(listening.list_mistakes(current_user=_USER, user_db=supabase))
    assert result[0]["pattern"] is None


def test_intelligence_service_failure_still_returns_200_with_null_pattern():
    subs = [_submission("student-1", [{"questionId": 100, "is_correct": False, "selected": "B"}])]
    events = [_mistake_event(i, "student-1", 100, False) for i in range(1, 4)]
    supabase = _fake(subs, [_question(100)], events)
    with patch.object(listening, "get_supabase", return_value=supabase), \
         patch.object(listening, "get_mistake_profile", side_effect=RuntimeError("boom")):
        result = _run(listening.list_mistakes(current_user=_USER, user_db=supabase))
    assert result[0]["pattern"] is None
    assert result[0]["questionId"] == 100  # notebook itself still intact


def test_user_isolation_across_notebook_and_mistake_profile():
    subs = [
        _submission("student-1", [{"questionId": 100, "is_correct": False, "selected": "B"}]),
        _submission("student-2", [{"questionId": 100, "is_correct": False, "selected": "B"}]),
    ]
    events = [
        *[_mistake_event(i, "student-1", 100, False) for i in range(1, 4)],  # persistent for student-1
        _mistake_event(4, "student-2", 100, False),  # one-off for student-2
    ]
    supabase = _fake(subs, [_question(100)], events)
    with patch.object(listening, "get_supabase", return_value=supabase):
        result_1 = _run(listening.list_mistakes(current_user=_USER, user_db=supabase))
        result_2 = _run(listening.list_mistakes(current_user=_OTHER, user_db=supabase))
    assert result_1[0]["pattern"] == "persistent"
    assert result_2[0]["pattern"] is None


def test_no_wrong_answers_returns_empty_list_unaffected_by_enrichment():
    supabase = _fake([], [], [])
    with patch.object(listening, "get_supabase", return_value=supabase):
        result = _run(listening.list_mistakes(current_user=_USER, user_db=supabase))
    assert result == []


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
