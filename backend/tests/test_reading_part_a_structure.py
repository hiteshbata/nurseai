"""Phase 3B-4 -- deterministic structural validation for a freshly-generated
Reading Part A draft (the locked contract from Phase 3B-3: 4 texts, 20
questions, Q1-5 matching MCQ, Q6-20 short_answer). Pure unit tests against
_validate_reading_part_a -- no supabase, no AI call. _validate() wiring is
covered by the "raises" tests at the bottom, which exercise the same
DraftGenerationError path admin_content_studio.py's router relies on.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.draft_generator import _validate, _validate_reading_part_a, DraftGenerationError

_BODY = "Text A:\nfirst text\n\nText B:\nsecond text\n\nText C:\nthird text\n\nText D:\nfourth text"
_MATCH_OPTIONS = ["Text A", "Text B", "Text C", "Text D"]


def _match_q(n=1, answer="Text B"):
    return {"content": f"In which text is topic {n} mentioned?", "type": "mcq", "options": list(_MATCH_OPTIONS), "correct_answer": answer}


def _short_q(n):
    return {"content": f"question {n}", "type": "short_answer", "options": [], "correct_answer": f"answer {n}"}


def _valid_questions():
    return [_match_q(n) for n in range(1, 6)] + [_short_q(n) for n in range(6, 21)]


def _valid_content():
    return {"title": "t", "part": "A", "body": _BODY, "questions": _valid_questions()}


def test_valid_payload_passes():
    assert _validate_reading_part_a(_valid_content()) == []


def test_missing_text_section():
    content = {**_valid_content(), "body": _BODY.replace("Text C:\nthird text\n\n", "")}
    errors = _validate_reading_part_a(content)
    assert any("Text C" in e for e in errors)


def test_wrong_question_count_short():
    content = {**_valid_content(), "questions": _valid_questions()[:19]}
    errors = _validate_reading_part_a(content)
    assert any("exactly 20 questions" in e and "19" in e for e in errors)


def test_wrong_question_count_long():
    content = {**_valid_content(), "questions": _valid_questions() + [_short_q(21)]}
    errors = _validate_reading_part_a(content)
    assert any("exactly 20 questions" in e and "21" in e for e in errors)


def test_q1_wrong_type():
    qs = _valid_questions()
    qs[0] = _short_q(1)
    errors = _validate_reading_part_a({**_valid_content(), "questions": qs})
    assert any("Question 1 must be type 'mcq'" in e for e in errors)


def test_q6_wrong_type():
    qs = _valid_questions()
    qs[5] = _match_q()
    errors = _validate_reading_part_a({**_valid_content(), "questions": qs})
    assert any("Question 6 must be type 'short_answer'" in e for e in errors)


def test_wrong_mcq_options():
    qs = _valid_questions()
    qs[0] = {**_match_q(1), "options": ["A", "B", "C", "D"]}
    errors = _validate_reading_part_a({**_valid_content(), "questions": qs})
    assert any("Question 1 options must be exactly" in e for e in errors)


def test_wrong_mcq_answer():
    qs = _valid_questions()
    qs[0] = _match_q(1, answer="Text E")
    errors = _validate_reading_part_a({**_valid_content(), "questions": qs})
    assert any("Question 1 correct_answer must be one of" in e for e in errors)


def test_short_answer_nonempty_options():
    qs = _valid_questions()
    qs[9] = {**_short_q(10), "options": ["Text A"]}
    errors = _validate_reading_part_a({**_valid_content(), "questions": qs})
    assert any("Question 10 options must be an empty array" in e for e in errors)


def test_short_answer_empty_answer():
    qs = _valid_questions()
    qs[15] = {**_short_q(16), "correct_answer": "  "}
    errors = _validate_reading_part_a({**_valid_content(), "questions": qs})
    assert any("Question 16 must have a non-empty correct_answer" in e for e in errors)


def test_duplicate_question_content():
    qs = _valid_questions()
    qs[6] = {**_short_q(7), "content": qs[7]["content"]}
    errors = _validate_reading_part_a({**_valid_content(), "questions": qs})
    assert any("Duplicate question text" in e for e in errors)


def test_repeated_matching_answer_is_not_a_duplicate():
    """Q1 and Q4 both answering 'Text B' is explicitly valid per the locked
    contract -- a text may legitimately be used more than once."""
    qs = _valid_questions()
    qs[0] = _match_q(1, answer="Text B")
    qs[3] = _match_q(4, answer="Text B")
    assert _validate_reading_part_a({**_valid_content(), "questions": qs}) == []


def test_validate_raises_on_structural_violation():
    with pytest.raises(DraftGenerationError, match="locked contract"):
        _validate("reading", {**_valid_content(), "questions": _valid_questions()[:19]})


def test_validate_passes_valid_part_a():
    assert _validate("reading", _valid_content()) == []


def test_part_c_content_does_not_run_part_a_validator():
    """Part C reading content must not run the Part A (or Part B) structural
    gate -- Part C now has its own dedicated validator (Phase 4C-3, see
    test_reading_part_c_structure.py), which requires the "texts" container
    rather than this old flat body/questions shape, so it's rejected here
    for violating *that* contract instead of ever reaching Part A's."""
    content = {"title": "t", "body": "some passage", "part": "C", "questions": [_short_q(1)]}
    with pytest.raises(DraftGenerationError, match="locked contract"):
        _validate("reading", content)
