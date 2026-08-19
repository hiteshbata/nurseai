"""Phase 3B -- deterministic structural validation for a freshly-generated
Listening Part B draft (locked contract: 6 independent extracts, each with a
non-empty transcript and exactly 1 mcq question over exactly 3 options, at
prep_seconds=15, audio_mode="dialogue"). Pure unit tests against
_validate_listening_part_b -- no supabase, no AI call. _validate() wiring is
covered by the "raises" tests at the bottom.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.draft_generator import _validate, _validate_listening_part_b, DraftGenerationError

_TRANSCRIPT = [{"speaker": "Nurse", "text": "Handover for bed 4."}, {"speaker": "Colleague", "text": "Noted, thanks."}]


def _mcq_q(n=1, answer="Option B"):
    return {"content": f"What does extract {n} say about this?", "type": "mcq", "options": ["Option A", "Option B", "Option C"], "correct_answer": answer}


def _extract(n=1):
    return {"title": f"Extract {n}", "transcript": _TRANSCRIPT, "questions": [_mcq_q(n)]}


def _valid_extracts():
    return [_extract(n) for n in range(1, 7)]


def _valid_content():
    return {"part": "B", "prep_seconds": 15, "audio_mode": "dialogue", "extracts": _valid_extracts()}


# ── A. valid structure passes ────────────────────────────────────────────

def test_valid_payload_passes():
    assert _validate_listening_part_b(_valid_content()) == []


# ── B/C. wrong extract count ─────────────────────────────────────────────

def test_five_extracts_fails():
    content = {**_valid_content(), "extracts": _valid_extracts()[:5]}
    errors = _validate_listening_part_b(content)
    assert any("exactly 6 extracts" in e and "5" in e for e in errors)


def test_seven_extracts_fails():
    content = {**_valid_content(), "extracts": _valid_extracts() + [_extract(7)]}
    errors = _validate_listening_part_b(content)
    assert any("exactly 6 extracts" in e and "7" in e for e in errors)


# ── D/E. wrong question count per extract ────────────────────────────────

def test_extract_with_zero_questions_fails():
    extracts = _valid_extracts()
    extracts[0] = {**extracts[0], "questions": []}
    errors = _validate_listening_part_b({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 must have exactly 1 questions" in e and "0" in e for e in errors)


def test_extract_with_two_questions_fails():
    extracts = _valid_extracts()
    extracts[2] = {**extracts[2], "questions": [_mcq_q(3), _mcq_q(3)]}
    errors = _validate_listening_part_b({**_valid_content(), "extracts": extracts})
    assert any("Extract 3 must have exactly 1 questions" in e and "2" in e for e in errors)


# ── F. missing transcript ────────────────────────────────────────────────

def test_missing_transcript_fails():
    extracts = _valid_extracts()
    extracts[0] = {**extracts[0], "transcript": None}
    errors = _validate_listening_part_b({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 must have a non-empty transcript" in e for e in errors)


# ── G. short_answer question fails ───────────────────────────────────────

def test_short_answer_question_fails():
    extracts = _valid_extracts()
    extracts[1]["questions"][0] = {**_mcq_q(2), "type": "short_answer"}
    errors = _validate_listening_part_b({**_valid_content(), "extracts": extracts})
    assert any("Extract 2 question 1 must be type 'mcq'" in e for e in errors)


# ── H/I. wrong option count ───────────────────────────────────────────────

def test_four_option_mcq_fails():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = {**_mcq_q(1), "options": ["A", "B", "C", "D"]}
    errors = _validate_listening_part_b({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 question 1 must have exactly 3 options" in e for e in errors)


def test_two_option_mcq_fails():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = {**_mcq_q(1), "options": ["A", "B"]}
    errors = _validate_listening_part_b({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 question 1 must have exactly 3 options" in e for e in errors)


# ── J. invalid correct_answer ─────────────────────────────────────────────

def test_invalid_correct_answer_fails():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = _mcq_q(1, answer="Option D")
    errors = _validate_listening_part_b({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 question 1 correct_answer must exactly match" in e for e in errors)


# ── K. duplicate options ──────────────────────────────────────────────────

def test_duplicate_options_fails():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = {**_mcq_q(1), "options": ["Option A", "Option A", "Option C"]}
    errors = _validate_listening_part_b({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 question 1 has duplicate options" in e for e in errors)


# ── L. wrong prep_seconds / audio_mode ────────────────────────────────────

def test_wrong_prep_seconds_fails():
    content = {**_valid_content(), "prep_seconds": 30}
    errors = _validate_listening_part_b(content)
    assert any("'prep_seconds' must be 15" in e for e in errors)


def test_wrong_audio_mode_fails():
    content = {**_valid_content(), "audio_mode": "monologue"}
    errors = _validate_listening_part_b(content)
    assert any("'audio_mode' must be 'dialogue'" in e for e in errors)


# ── M. duplicate question content ─────────────────────────────────────────

def test_duplicate_question_content_fails():
    extracts = _valid_extracts()
    extracts[1]["questions"][0] = {**_mcq_q(2), "content": extracts[0]["questions"][0]["content"]}
    errors = _validate_listening_part_b({**_valid_content(), "extracts": extracts})
    assert any("Duplicate question text" in e for e in errors)


# ── wiring into _validate() ───────────────────────────────────────────────

def test_validate_raises_on_structural_violation():
    content = {**_valid_content(), "extracts": _valid_extracts()[:5]}
    with pytest.raises(DraftGenerationError, match="locked contract"):
        _validate("listening", content)


def test_validate_passes_valid_part_b():
    assert _validate("listening", _valid_content()) == []
