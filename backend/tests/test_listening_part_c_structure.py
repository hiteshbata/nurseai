"""Phase 3B -- deterministic structural validation for a freshly-generated
Listening Part C draft (locked contract: 2 independent extracts, each with a
non-empty transcript, a per-extract audio_mode ("dialogue" or "monologue"),
and exactly 6 mcq questions over exactly 3 options, at prep_seconds=90).
Pure unit tests against _validate_listening_part_c -- no supabase, no AI
call. _validate() wiring is covered by the "raises" tests at the bottom.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.draft_generator import _validate, _validate_listening_part_c, DraftGenerationError

_TRANSCRIPT = [{"speaker": "Interviewer", "text": "Tell us about your research."}, {"speaker": "Guest", "text": "Sure, it started five years ago."}]


def _mcq_q(extract_n=1, question_n=1, answer="Option B"):
    return {"content": f"Extract {extract_n} question {question_n}: what does this say?", "type": "mcq", "options": ["Option A", "Option B", "Option C"], "correct_answer": answer}


def _extract(n=1, audio_mode="dialogue"):
    return {"title": f"Extract {n}", "audio_mode": audio_mode, "transcript": _TRANSCRIPT, "questions": [_mcq_q(n, q) for q in range(1, 7)]}


def _valid_extracts():
    return [_extract(1, "dialogue"), _extract(2, "monologue")]


def _valid_content():
    return {"part": "C", "prep_seconds": 90, "extracts": _valid_extracts()}


# ── A. valid structure passes ────────────────────────────────────────────

def test_valid_payload_passes():
    assert _validate_listening_part_c(_valid_content()) == []


# ── B/C. wrong extract count ─────────────────────────────────────────────

def test_one_extract_fails():
    content = {**_valid_content(), "extracts": _valid_extracts()[:1]}
    errors = _validate_listening_part_c(content)
    assert any("exactly 2 extracts" in e and "1" in e for e in errors)


def test_three_extracts_fails():
    content = {**_valid_content(), "extracts": _valid_extracts() + [_extract(3)]}
    errors = _validate_listening_part_c(content)
    assert any("exactly 2 extracts" in e and "3" in e for e in errors)


# ── D/E. wrong question count per extract ────────────────────────────────

def test_extract_with_five_questions_fails():
    extracts = _valid_extracts()
    extracts[0] = {**extracts[0], "questions": extracts[0]["questions"][:5]}
    errors = _validate_listening_part_c({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 must have exactly 6 questions" in e and "5" in e for e in errors)


def test_extract_with_seven_questions_fails():
    extracts = _valid_extracts()
    extracts[1] = {**extracts[1], "questions": extracts[1]["questions"] + [_mcq_q(2, 7)]}
    errors = _validate_listening_part_c({**_valid_content(), "extracts": extracts})
    assert any("Extract 2 must have exactly 6 questions" in e and "7" in e for e in errors)


# ── F. missing transcript ────────────────────────────────────────────────

def test_missing_transcript_fails():
    extracts = _valid_extracts()
    extracts[0] = {**extracts[0], "transcript": []}
    errors = _validate_listening_part_c({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 must have a non-empty transcript" in e for e in errors)


# ── G. invalid per-extract audio_mode ─────────────────────────────────────

def test_invalid_audio_mode_fails():
    extracts = _valid_extracts()
    extracts[0] = {**extracts[0], "audio_mode": "narration"}
    errors = _validate_listening_part_c({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 'audio_mode' must be one of" in e for e in errors)


def test_missing_audio_mode_fails():
    extracts = _valid_extracts()
    extracts[1] = {k: v for k, v in extracts[1].items() if k != "audio_mode"}
    errors = _validate_listening_part_c({**_valid_content(), "extracts": extracts})
    assert any("Extract 2 'audio_mode' must be one of" in e for e in errors)


# ── H. wrong option count / wrong type ─────────────────────────────────────

def test_short_answer_question_fails():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = {**_mcq_q(1), "type": "short_answer"}
    errors = _validate_listening_part_c({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 question 1 must be type 'mcq'" in e for e in errors)


def test_four_option_mcq_fails():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = {**_mcq_q(1), "options": ["A", "B", "C", "D"]}
    errors = _validate_listening_part_c({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 question 1 must have exactly 3 options" in e for e in errors)


# ── I. invalid correct_answer ─────────────────────────────────────────────

def test_invalid_correct_answer_fails():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = _mcq_q(1, answer="Option D")
    errors = _validate_listening_part_c({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 question 1 correct_answer must exactly match" in e for e in errors)


# ── J. duplicate options ──────────────────────────────────────────────────

def test_duplicate_options_fails():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = {**_mcq_q(1), "options": ["Option A", "Option A", "Option C"]}
    errors = _validate_listening_part_c({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 question 1 has duplicate options" in e for e in errors)


# ── K. wrong prep_seconds ─────────────────────────────────────────────────

def test_wrong_prep_seconds_fails():
    content = {**_valid_content(), "prep_seconds": 15}
    errors = _validate_listening_part_c(content)
    assert any("'prep_seconds' must be 90" in e for e in errors)


# ── L. duplicate question content ─────────────────────────────────────────

def test_duplicate_question_content_fails():
    extracts = _valid_extracts()
    extracts[1]["questions"][0] = {**_mcq_q(2), "content": extracts[0]["questions"][0]["content"]}
    errors = _validate_listening_part_c({**_valid_content(), "extracts": extracts})
    assert any("Duplicate question text" in e for e in errors)


# ── wiring into _validate() ───────────────────────────────────────────────

def test_validate_raises_on_structural_violation():
    content = {**_valid_content(), "extracts": _valid_extracts()[:1]}
    with pytest.raises(DraftGenerationError, match="locked contract"):
        _validate("listening", content)


def test_validate_passes_valid_part_c():
    assert _validate("listening", _valid_content()) == []
