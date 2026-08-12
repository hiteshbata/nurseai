import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services import technique_grading


def _mp(scoring_type="rule_based", expected_response=None, content=None, instructions=""):
    return {
        "scoring_type": scoring_type,
        "instructions": instructions,
        "content": content or {},
        "expected_response": expected_response or {},
    }


def test_rule_based_correct_answer_gives_full_band_and_no_mistakes():
    result = technique_grading.grade_rule_based(
        {"correct_answer": "B"}, {"answer": "B"},
    )
    assert result["score"] == 6.0
    assert result["feedback"]["is_correct"] is True
    assert result["mistakes"] == []


def test_rule_based_wrong_answer_gives_zero_band_and_records_mistake():
    result = technique_grading.grade_rule_based(
        {"correct_answer": "B"}, {"answer": "A"},
    )
    assert result["score"] == 0.0
    assert result["feedback"]["is_correct"] is False
    assert result["mistakes"] == [{"reason": "incorrect_selection", "expected": "B", "given": "A"}]


def test_rule_based_correct_answer_includes_explanation_when_content_supplies_one():
    result = technique_grading.grade_rule_based(
        {"correct_answer": "B", "explanation": "B is correct because..."}, {"answer": "B"},
    )
    assert result["feedback"]["explanation"] == "B is correct because..."


def test_rule_based_wrong_answer_with_no_distractor_metadata_stays_the_old_shape():
    # No `distractors` on expected_response -- must not fabricate a mistake_type.
    result = technique_grading.grade_rule_based(
        {"correct_answer": "B"}, {"answer": "A"},
    )
    assert result["mistakes"] == [{"reason": "incorrect_selection", "expected": "B", "given": "A"}]
    assert "mistake_type" not in result["mistakes"][0]


def test_rule_based_wrong_answer_with_distractor_metadata_includes_mistake_type_and_explanation():
    expected_response = {
        "correct_answer": "B",
        "distractors": [
            {"option": "A", "mistake_type": "distractor_confusion", "explanation": "A sounds plausible but..."},
        ],
    }
    result = technique_grading.grade_rule_based(expected_response, {"answer": "A"})
    assert result["mistakes"] == [{
        "reason": "incorrect_selection", "expected": "B", "given": "A",
        "mistake_type": "distractor_confusion", "explanation": "A sounds plausible but...",
    }]


def test_rule_based_wrong_answer_for_an_untagged_option_omits_mistake_type():
    # distractors metadata exists for the technique but not for the option
    # this particular learner picked -- still must not guess.
    expected_response = {
        "correct_answer": "B",
        "distractors": [{"option": "C", "mistake_type": "vocabulary", "explanation": "..."}],
    }
    result = technique_grading.grade_rule_based(expected_response, {"answer": "A"})
    assert result["mistakes"] == [{"reason": "incorrect_selection", "expected": "B", "given": "A"}]


def test_rule_based_wrong_answer_with_null_distractors_falls_back_safely():
    expected_response = {"correct_answer": "B", "distractors": None}
    result = technique_grading.grade_rule_based(expected_response, {"answer": "A"})
    assert result["mistakes"] == [{"reason": "incorrect_selection", "expected": "B", "given": "A"}]


def test_rule_based_wrong_answer_with_non_dict_distractor_items_falls_back_safely():
    expected_response = {"correct_answer": "B", "distractors": ["bad", None]}
    result = technique_grading.grade_rule_based(expected_response, {"answer": "A"})
    assert result["mistakes"] == [{"reason": "incorrect_selection", "expected": "B", "given": "A"}]


def test_rule_based_wrong_answer_with_malformed_distractor_shape_falls_back_safely():
    expected_response = {"correct_answer": "B", "distractors": [{"unexpected": "shape"}]}
    result = technique_grading.grade_rule_based(expected_response, {"answer": "A"})
    assert result["mistakes"] == [{"reason": "incorrect_selection", "expected": "B", "given": "A"}]


def test_grade_micro_practice_dispatches_rule_based_without_calling_ai():
    mp = _mp(scoring_type="rule_based", expected_response={"correct_answer": "B"})
    with patch.object(technique_grading, "_call_ai", new=AsyncMock()) as ai_mock:
        result = _run(technique_grading.grade_micro_practice(mp, {"answer": "B"}))
    ai_mock.assert_not_called()
    assert result["score"] == 6.0


def test_rule_based_with_no_correct_answer_configured_never_grades_as_correct():
    # Malformed micro_practice (admin forgot to set expected_response) must
    # never be graded "correct" by accident -- mcq_grading.grade_exact_match
    # skips ungraded questions, so this stays band 0.0, not a false pass.
    result = technique_grading.grade_rule_based({}, {"answer": None})
    assert result["score"] == 0.0
    assert result["feedback"]["is_correct"] is False


def test_grade_micro_practice_rejects_unknown_scoring_type():
    mp = _mp(scoring_type="essay_writing")
    with pytest.raises(technique_grading.InvalidScoringType):
        _run(technique_grading.grade_micro_practice(mp, {"answer": "anything"}))


def _run(coro):
    import asyncio
    return asyncio.run(coro)


class AiGradingTests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_scoring_type_dispatches_to_call_ai_with_own_purpose(self):
        mp = _mp(scoring_type="ai", instructions="Rewrite the note professionally.")
        with patch.object(technique_grading, "_call_ai", new=AsyncMock(return_value={
            "score": 4.5, "correct_points": "Good tone", "incorrect_points": "",
            "reasoning": "Matches clinical register", "improvement_tip": "Be more concise",
            "suggested_retry": False,
        })) as ai_mock:
            result = await technique_grading.grade_micro_practice(mp, {"answer": "Patient reports pain."})

        ai_mock.assert_called_once()
        assert ai_mock.call_args.kwargs["purpose"] == "technique_micro_practice_feedback"
        assert ai_mock.call_args.kwargs["json_mode"] is True
        assert result["score"] == 4.5
        assert result["mistakes"] == []  # no incorrect_points -> no mistake recorded

    async def test_ai_provider_failure_returns_no_score_not_a_fake_zero(self):
        mp = _mp(scoring_type="ai")
        with patch.object(technique_grading, "_call_ai", new=AsyncMock(return_value={
            "provider_failure": True, "raw_feedback": "unavailable",
        })):
            result = await technique_grading.grade_micro_practice(mp, {"answer": "x"})

        assert result["score"] is None
        assert result["provider_failure"] is True

    async def test_ai_json_missing_score_key_is_treated_as_failure_not_crash(self):
        # A malformed-but-parseable AI JSON response (no provider_failure
        # flag, but no "score" either) must not crash or fabricate a score.
        mp = _mp(scoring_type="ai")
        with patch.object(technique_grading, "_call_ai", new=AsyncMock(return_value={
            "correct_points": "ok", "finish_reason": "stop",
        })):
            result = await technique_grading.grade_micro_practice(mp, {"answer": "x"})

        assert result["score"] is None
        assert result["provider_failure"] is True

    async def test_ai_incorrect_points_recorded_as_a_mistake(self):
        mp = _mp(scoring_type="ai")
        with patch.object(technique_grading, "_call_ai", new=AsyncMock(return_value={
            "score": 2.0, "incorrect_points": "Missed the purpose statement",
        })):
            result = await technique_grading.grade_micro_practice(mp, {"answer": "x"})

        assert result["mistakes"] == [{"reason": "Missed the purpose statement"}]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
