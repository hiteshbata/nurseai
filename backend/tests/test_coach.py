"""
Tests for the coach-agent study plan's rule-based core: weak-criteria
detection and the criteria-averaging it's built on (app.services.coach).

Pure unit tests only -- no network, no Supabase, no AI calls. The
AI-generated narrative in build_study_plan() is intentionally not covered
here (that would require mocking _call_ai); this file guards the
deterministic aggregation/ranking logic that decides which criteria the
plan is built around in the first place.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.coach import (
    compute_criteria_averages,
    identify_weak_criteria,
    weeks_until,
    MIN_SESSIONS_FOR_CRITERION,
)


def _feedback(**scores) -> str:
    return json.dumps({"scores": {k: {"score": v} for k, v in scores.items()}})


# ── compute_criteria_averages ────────────────────────────────────────

def test_criteria_average_requires_minimum_sessions():
    rows = [_feedback(fluency=5) for _ in range(MIN_SESSIONS_FOR_CRITERION - 1)]
    result = compute_criteria_averages(rows)
    assert result["fluency"] is None


def test_criteria_average_computed_once_minimum_reached():
    rows = [_feedback(fluency=4), _feedback(fluency=5), _feedback(fluency=6)]
    result = compute_criteria_averages(rows)
    assert result["fluency"] == 5.0


def test_criteria_average_ignores_missing_criteria_in_a_session():
    rows = [
        _feedback(fluency=6, grammar=6),
        _feedback(fluency=6, grammar=6),
        _feedback(fluency=6),  # grammar not scored this session
    ]
    result = compute_criteria_averages(rows)
    assert result["fluency"] == 6.0
    assert result["grammar"] is None  # only 2 sessions scored grammar


def test_criteria_average_falls_back_to_relationship_building_for_empathy():
    # 3-criteria (free/basic) scoring uses "relationship_building" instead
    # of "empathy" -- the aggregator must recognize both under "empathy".
    rows = [
        json.dumps({"scores": {"relationship_building": {"score": 4}}}),
        json.dumps({"scores": {"relationship_building": {"score": 5}}}),
        json.dumps({"scores": {"relationship_building": {"score": 6}}}),
    ]
    result = compute_criteria_averages(rows)
    assert result["empathy"] == 5.0


def test_criteria_average_handles_malformed_json():
    rows = ["not json", None, ""]
    result = compute_criteria_averages(rows)
    assert all(v is None for v in result.values())


# ── identify_weak_criteria ───────────────────────────────────────────

def test_identify_weak_criteria_sorts_worst_first():
    averages = {
        "empathy": 5.0,
        "fluency": 2.0,
        "grammar": 3.5,
        "patient_perspective": None,
        "providing_structure": None,
        "information_gathering": None,
        "information_giving": None,
        "intelligibility": None,
        "appropriateness_of_language": None,
    }
    weak = identify_weak_criteria(averages, top_n=2)
    assert weak == ["fluency", "grammar"]


def test_identify_weak_criteria_excludes_criteria_without_enough_data():
    averages = {"fluency": None, "grammar": 3.0}
    weak = identify_weak_criteria(averages, top_n=5)
    assert weak == ["grammar"]


def test_identify_weak_criteria_empty_when_no_data():
    averages = {"fluency": None, "grammar": None}
    assert identify_weak_criteria(averages) == []


# ── weeks_until ───────────────────────────────────────────────────────

def test_weeks_until_computes_whole_weeks():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    exam = datetime(2026, 1, 22, tzinfo=timezone.utc)  # 21 days
    assert weeks_until(now, exam) == 3


def test_weeks_until_never_negative_for_past_exam_date():
    now = datetime(2026, 1, 22, tzinfo=timezone.utc)
    exam = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert weeks_until(now, exam) == 0


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    tests = [f for name, f in vars(mod).items() if name.startswith("test_") and inspect.isfunction(f)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
