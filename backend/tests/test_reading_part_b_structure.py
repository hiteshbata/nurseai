"""Phase 4A -- deterministic structural validation for a freshly-generated
Reading Part B draft (the locked contract: 6 independent short extracts,
each its own passage with exactly 1 mcq question over exactly 3 options).
Pure unit tests against _validate_reading_part_b -- no supabase, no AI call.
_validate() wiring is covered by the "raises" tests at the bottom, mirroring
test_reading_part_a_structure.py's pattern.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.draft_generator import _validate, _validate_reading_part_b, DraftGenerationError


def _mcq_q(n=1, answer="Option B"):
    return {
        "content": f"What does extract {n} say about this?",
        "type": "mcq",
        "options": ["Option A", "Option B", "Option C"],
        "correct_answer": answer,
    }


def _passage(n=1):
    return {
        "title": f"Extract {n}",
        "body": f"This is the body text of extract {n}, a short workplace document.",
        "questions": [_mcq_q(n)],
    }


def _valid_passages():
    return [_passage(n) for n in range(1, 7)]


def _valid_content():
    return {"part": "B", "passages": _valid_passages()}


# ── A. valid structure passes ────────────────────────────────────────────

def test_valid_payload_passes():
    assert _validate_reading_part_b(_valid_content()) == []


# ── B/C. wrong passage count ─────────────────────────────────────────────

def test_five_passages_fails():
    content = {**_valid_content(), "passages": _valid_passages()[:5]}
    errors = _validate_reading_part_b(content)
    assert any("exactly 6 passages" in e and "5" in e for e in errors)


def test_seven_passages_fails():
    content = {**_valid_content(), "passages": _valid_passages() + [_passage(7)]}
    errors = _validate_reading_part_b(content)
    assert any("exactly 6 passages" in e and "7" in e for e in errors)


# ── D/E. wrong question count per passage ────────────────────────────────

def test_passage_with_zero_questions_fails():
    passages = _valid_passages()
    passages[0] = {**passages[0], "questions": []}
    errors = _validate_reading_part_b({**_valid_content(), "passages": passages})
    assert any("Passage 1 must have exactly 1 question" in e and "0" in e for e in errors)


def test_passage_with_two_questions_fails():
    passages = _valid_passages()
    passages[2] = {**passages[2], "questions": [_mcq_q(3), _mcq_q(3)]}
    errors = _validate_reading_part_b({**_valid_content(), "passages": passages})
    assert any("Passage 3 must have exactly 1 question" in e and "2" in e for e in errors)


# ── F. short_answer question fails ───────────────────────────────────────

def test_short_answer_question_fails():
    passages = _valid_passages()
    passages[1]["questions"][0] = {**_mcq_q(2), "type": "short_answer"}
    errors = _validate_reading_part_b({**_valid_content(), "passages": passages})
    assert any("Passage 2 question 1 must be type 'mcq'" in e for e in errors)


# ── G/H. wrong option count ───────────────────────────────────────────────

def test_four_option_mcq_fails():
    passages = _valid_passages()
    passages[0]["questions"][0] = {**_mcq_q(1), "options": ["A", "B", "C", "D"]}
    errors = _validate_reading_part_b({**_valid_content(), "passages": passages})
    assert any("Passage 1 question 1 must have exactly 3 options" in e for e in errors)


def test_two_option_mcq_fails():
    passages = _valid_passages()
    passages[0]["questions"][0] = {**_mcq_q(1), "options": ["A", "B"]}
    errors = _validate_reading_part_b({**_valid_content(), "passages": passages})
    assert any("Passage 1 question 1 must have exactly 3 options" in e for e in errors)


# ── I. invalid correct_answer ─────────────────────────────────────────────

def test_invalid_correct_answer_fails():
    passages = _valid_passages()
    passages[0]["questions"][0] = _mcq_q(1, answer="Option D")
    errors = _validate_reading_part_b({**_valid_content(), "passages": passages})
    assert any("Passage 1 question 1 correct_answer must exactly match" in e for e in errors)


# ── J. duplicate options ──────────────────────────────────────────────────

def test_duplicate_options_fails():
    passages = _valid_passages()
    passages[0]["questions"][0] = {**_mcq_q(1), "options": ["Option A", "Option A", "Option C"]}
    errors = _validate_reading_part_b({**_valid_content(), "passages": passages})
    assert any("Passage 1 question 1 has duplicate options" in e for e in errors)


# ── K. duplicate question content ─────────────────────────────────────────

def test_duplicate_question_content_fails():
    passages = _valid_passages()
    passages[1]["questions"][0] = {**_mcq_q(2), "content": passages[0]["questions"][0]["content"]}
    errors = _validate_reading_part_b({**_valid_content(), "passages": passages})
    assert any("Duplicate question text" in e for e in errors)


# ── wiring into _validate() ───────────────────────────────────────────────

def test_validate_raises_on_structural_violation():
    content = {**_valid_content(), "passages": _valid_passages()[:5]}
    with pytest.raises(DraftGenerationError, match="locked contract"):
        _validate("reading", content)


def test_validate_passes_valid_part_b():
    assert _validate("reading", _valid_content()) == []
