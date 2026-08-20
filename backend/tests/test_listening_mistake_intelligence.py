"""E2.2 -- Mistake Intelligence (read-only classifier) for Listening.

Two layers under test:
  1. classify_mistakes -- pure function over plain event-row dicts. Most
     cases live here since no DB/async plumbing is needed.
  2. get_mistake_profile -- the user-scoped read wrapper. Verified against a
     local FakeSupabase (same shape as test_listening_mistake_engine.py's)
     to confirm it filters by user_id, orders by id, and touches only
     listening_mistake_events -- never skill_graph or user_skill_stats.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.listening_mistake_intelligence import (
    PERSISTENT_MISTAKE_MIN_WRONG,
    classify_mistakes,
    get_mistake_profile,
)


def _event(id, question_id, part, is_correct, created_at="2026-08-01T00:00:00Z",
           selected_option="x", correct_answer="y"):
    return {
        "id": id,
        "question_id": question_id,
        "part": part,
        "is_correct": is_correct,
        "selected_option": selected_option,
        "correct_answer": correct_answer,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# classify_mistakes -- core classification
# ---------------------------------------------------------------------------

def test_empty_history():
    result = classify_mistakes([])
    assert result["recent_mistakes"] == []
    assert result["corrected_mistakes"] == []
    assert result["repeated_mistakes"] == []
    assert result["persistent_mistakes"] == []
    assert result["part_patterns"] == {}
    assert result["frequency"] == {"total_events": 0, "total_wrong": 0, "distinct_questions_wrong": 0}


def test_one_wrong_attempt():
    rows = [_event(1, 100, "A", False)]
    result = classify_mistakes(rows)
    assert [m["question_id"] for m in result["recent_mistakes"]] == [100]
    assert result["corrected_mistakes"] == []
    assert result["repeated_mistakes"] == []
    assert result["persistent_mistakes"] == []


def test_wrong_then_correct_is_corrected():
    rows = [_event(1, 100, "A", False), _event(2, 100, "A", True)]
    result = classify_mistakes(rows)
    assert result["recent_mistakes"] == []
    assert [m["question_id"] for m in result["corrected_mistakes"]] == [100]
    assert result["corrected_mistakes"][0]["wrong_count"] == 1
    assert result["repeated_mistakes"] == []
    assert result["persistent_mistakes"] == []


def test_correct_then_wrong_is_recent_not_corrected():
    rows = [_event(1, 100, "A", True), _event(2, 100, "A", False)]
    result = classify_mistakes(rows)
    assert [m["question_id"] for m in result["recent_mistakes"]] == [100]
    assert result["corrected_mistakes"] == []


def test_wrong_twice_is_repeated_not_persistent():
    rows = [_event(1, 100, "A", False), _event(2, 100, "A", False)]
    result = classify_mistakes(rows)
    assert [m["question_id"] for m in result["repeated_mistakes"]] == [100]
    assert result["repeated_mistakes"][0]["wrong_count"] == 2
    assert result["persistent_mistakes"] == []


def test_wrong_three_times_unresolved_is_persistent():
    rows = [_event(1, 100, "A", False), _event(2, 100, "A", False), _event(3, 100, "A", False)]
    result = classify_mistakes(rows)
    assert [m["question_id"] for m in result["repeated_mistakes"]] == [100]
    assert [m["question_id"] for m in result["persistent_mistakes"]] == [100]
    assert result["persistent_mistakes"][0]["wrong_count"] == 3
    assert result["persistent_mistakes"][0]["last_wrong_at"] == "2026-08-01T00:00:00Z"


def test_wrong_three_then_correct_is_repeated_and_corrected_not_persistent():
    rows = [
        _event(1, 100, "A", False), _event(2, 100, "A", False),
        _event(3, 100, "A", False), _event(4, 100, "A", True),
    ]
    result = classify_mistakes(rows)
    assert [m["question_id"] for m in result["repeated_mistakes"]] == [100]
    assert [m["question_id"] for m in result["corrected_mistakes"]] == [100]
    assert result["corrected_mistakes"][0]["wrong_count"] == 3
    assert result["persistent_mistakes"] == []


def test_multiple_questions_same_part():
    rows = [_event(1, 100, "A", False), _event(2, 101, "A", False)]
    result = classify_mistakes(rows)
    ids = {m["question_id"] for m in result["recent_mistakes"]}
    assert ids == {100, 101}


def test_abc_isolation():
    rows = [
        _event(1, 100, "A", False), _event(2, 100, "A", False),
        _event(3, 200, "B", True), _event(4, 200, "B", False),
        _event(5, 300, "C", True), _event(6, 300, "C", True),
    ]
    result = classify_mistakes(rows)
    assert result["part_patterns"]["A"] == {"wrong": 2, "total": 2, "rate": 1.0}
    assert result["part_patterns"]["B"] == {"wrong": 1, "total": 2, "rate": 0.5}
    assert result["part_patterns"]["C"] == {"wrong": 0, "total": 2, "rate": 0.0}


def test_part_pattern_minimum_attempt_gate():
    rows = [_event(1, 100, "A", False)]
    result = classify_mistakes(rows)
    assert "A" not in result["part_patterns"]
    assert result["part_patterns"] == {}


def test_latest_mistake_resolution_uses_id_not_created_at():
    """created_at is identical/out of order -- id must decide which event is
    latest, so this is correct (wrong then correct with the later id)."""
    rows = [
        _event(2, 100, "A", True, created_at="2026-08-01T00:00:00Z"),
        _event(1, 100, "A", False, created_at="2026-08-01T00:00:00Z"),
    ]
    result = classify_mistakes(rows)
    assert result["recent_mistakes"] == []
    assert [m["question_id"] for m in result["corrected_mistakes"]] == [100]


def test_id_ordering_with_identical_created_at():
    rows = [
        _event(10, 100, "A", False, created_at="2026-08-01T00:00:00Z"),
        _event(11, 100, "A", False, created_at="2026-08-01T00:00:00Z"),
        _event(12, 100, "A", True, created_at="2026-08-01T00:00:00Z"),
    ]
    result = classify_mistakes(rows)
    assert result["recent_mistakes"] == []
    assert result["corrected_mistakes"][0]["wrong_count"] == 2


def test_duplicate_events_increase_count_not_distinct_identity():
    rows = [_event(1, 100, "A", False), _event(2, 100, "A", False), _event(3, 100, "A", False)]
    result = classify_mistakes(rows)
    assert len(result["persistent_mistakes"]) == 1
    assert result["persistent_mistakes"][0]["wrong_count"] == 3
    assert result["frequency"]["distinct_questions_wrong"] == 1
    assert result["frequency"]["total_wrong"] == 3


def test_mixed_history_all_categories():
    rows = [
        _event(1, 100, "A", False),                                   # recent
        _event(2, 200, "A", False), _event(3, 200, "A", True),        # corrected
        _event(4, 300, "B", False), _event(5, 300, "B", False),       # repeated
        _event(6, 400, "B", False), _event(7, 400, "B", False), _event(8, 400, "B", False),  # persistent
    ]
    result = classify_mistakes(rows)
    assert {m["question_id"] for m in result["recent_mistakes"]} == {100, 300, 400}
    assert {m["question_id"] for m in result["corrected_mistakes"]} == {200}
    assert {m["question_id"] for m in result["repeated_mistakes"]} == {300, 400}
    assert {m["question_id"] for m in result["persistent_mistakes"]} == {400}


def test_frequency_calculations():
    rows = [_event(1, 100, "A", False), _event(2, 100, "A", True), _event(3, 200, "B", False)]
    result = classify_mistakes(rows)
    assert result["frequency"] == {"total_events": 3, "total_wrong": 2, "distinct_questions_wrong": 2}


def test_distinct_questions_wrong_dedupes_per_question():
    rows = [_event(1, 100, "A", False), _event(2, 100, "A", False), _event(3, 200, "A", False)]
    result = classify_mistakes(rows)
    assert result["frequency"]["distinct_questions_wrong"] == 2


def test_persistent_is_always_subset_of_repeated():
    scenarios = [
        [_event(1, 1, "A", False)],
        [_event(1, 1, "A", False), _event(2, 1, "A", False)],
        [_event(1, 1, "A", False), _event(2, 1, "A", False), _event(3, 1, "A", False)],
        [_event(1, 1, "A", False), _event(2, 1, "A", False), _event(3, 1, "A", False), _event(4, 1, "A", True)],
        [_event(i, i, "A", False) for i in range(1, 6)],
    ]
    for rows in scenarios:
        result = classify_mistakes(rows)
        repeated_ids = {m["question_id"] for m in result["repeated_mistakes"]}
        persistent_ids = {m["question_id"] for m in result["persistent_mistakes"]}
        assert persistent_ids.issubset(repeated_ids)


def test_persistent_threshold_is_named_constant():
    assert PERSISTENT_MISTAKE_MIN_WRONG == 3


# ---------------------------------------------------------------------------
# get_mistake_profile -- user-scoped read wrapper
# ---------------------------------------------------------------------------

class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, supabase, table_name):
        self.supabase = supabase
        self.table_name = table_name
        self.rows = supabase.tables.setdefault(table_name, [])
        self.filters = []
        self.order_col = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def order(self, col, desc=False):
        self.order_col = col
        return self

    def execute(self):
        self.supabase.queried_tables.append(self.table_name)
        rows = [r for r in self.rows if all(r.get(c) == v for c, v in self.filters)]
        if self.order_col:
            rows = sorted(rows, key=lambda r: r.get(self.order_col))
        return FakeResult(rows)


class FakeSupabase:
    def __init__(self):
        self.tables = {}
        self.queried_tables = []

    def table(self, name):
        return FakeQuery(self, name)


def _seeded_fake():
    fake = FakeSupabase()
    fake.tables["listening_mistake_events"] = [
        {"id": 1, "user_id": "user-a", "question_id": 100, "part": "A", "is_correct": False,
         "selected_option": "x", "correct_answer": "y", "created_at": "2026-08-01T00:00:00Z"},
        {"id": 2, "user_id": "user-a", "question_id": 100, "part": "A", "is_correct": False,
         "selected_option": "x", "correct_answer": "y", "created_at": "2026-08-01T00:01:00Z"},
        {"id": 3, "user_id": "user-b", "question_id": 999, "part": "C", "is_correct": False,
         "selected_option": "x", "correct_answer": "y", "created_at": "2026-08-01T00:02:00Z"},
    ]
    return fake


def test_learner_isolation_at_query_wrapper_level():
    fake = _seeded_fake()
    result = asyncio.run(get_mistake_profile(fake, "user-a"))
    ids = {m["question_id"] for m in result["repeated_mistakes"]}
    assert ids == {100}
    assert 999 not in {m["question_id"] for m in result["recent_mistakes"]}


def test_wrapper_orders_by_id_and_filters_by_user():
    fake = _seeded_fake()
    asyncio.run(get_mistake_profile(fake, "user-a"))
    query = fake.table("listening_mistake_events")
    assert query.order_col is None  # fresh query object, just confirms table shape below

    # Re-derive the actual filter/order applied via a spy table wrapper.
    class SpyFakeSupabase(FakeSupabase):
        def table(self, name):
            q = super().table(name)
            orig_execute = q.execute

            def spy_execute():
                SpyFakeSupabase.last_filters = q.filters
                SpyFakeSupabase.last_order_col = q.order_col
                return orig_execute()

            q.execute = spy_execute
            return q

    spy = SpyFakeSupabase()
    spy.tables["listening_mistake_events"] = fake.tables["listening_mistake_events"]
    asyncio.run(get_mistake_profile(spy, "user-a"))
    assert SpyFakeSupabase.last_filters == [("user_id", "user-a")]
    assert SpyFakeSupabase.last_order_col == "id"


def test_no_skill_graph_or_user_skill_stats_access():
    fake = _seeded_fake()
    asyncio.run(get_mistake_profile(fake, "user-a"))
    assert fake.queried_tables == ["listening_mistake_events"]
    assert "skill_graph" not in fake.queried_tables
    assert "user_skill_stats" not in fake.queried_tables
