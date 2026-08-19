"""Phase 3B -- deterministic structural validation for a freshly-generated
Listening Part A draft (locked contract: 2 independent extracts, each with a
non-empty transcript, a note-completion body template, and exactly 12
short_answer questions -- 24 total -- at prep_seconds=30, audio_mode=
"dialogue"). Pure unit tests against _validate_listening_part_a -- no
supabase, no AI call. _validate() wiring is covered by the "raises" tests at
the bottom, mirroring test_reading_part_a_structure.py's pattern.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.draft_generator import _validate, _validate_listening_part_a, DraftGenerationError

_TRANSCRIPT = [{"speaker": "Nurse", "text": "Good morning, what brings you in today?"}, {"speaker": "Patient", "text": "I've had a headache for three days."}]


def _short_q(extract_n=1, blank_n=1, answer="three days"):
    return {"content": f"Extract {extract_n} blank ({blank_n}): symptom detail?", "type": "short_answer", "options": [], "correct_answer": answer}


def _extract(n=1):
    return {
        "title": f"Extract {n}",
        "transcript": _TRANSCRIPT,
        "body": f"Extract {n} notes\n- context bullet\n\n1. Symptom duration: ______",
        "questions": [_short_q(n, i) for i in range(1, 13)],
    }


def _valid_extracts():
    return [_extract(1), _extract(2)]


def _valid_content():
    return {"part": "A", "prep_seconds": 30, "audio_mode": "dialogue", "extracts": _valid_extracts()}


# ── A. valid structure passes ────────────────────────────────────────────

def test_valid_payload_passes():
    assert _validate_listening_part_a(_valid_content()) == []


# ── B/C. wrong extract count ─────────────────────────────────────────────

def test_one_extract_fails():
    content = {**_valid_content(), "extracts": _valid_extracts()[:1]}
    errors = _validate_listening_part_a(content)
    assert any("exactly 2 extracts" in e and "1" in e for e in errors)


def test_three_extracts_fails():
    content = {**_valid_content(), "extracts": _valid_extracts() + [_extract(3)]}
    errors = _validate_listening_part_a(content)
    assert any("exactly 2 extracts" in e and "3" in e for e in errors)


# ── D/E. wrong question count per extract ────────────────────────────────

def test_extract_with_eleven_questions_fails():
    extracts = _valid_extracts()
    extracts[0] = {**extracts[0], "questions": extracts[0]["questions"][:11]}
    errors = _validate_listening_part_a({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 must have exactly 12 questions" in e and "11" in e for e in errors)


def test_extract_with_thirteen_questions_fails():
    extracts = _valid_extracts()
    extracts[1] = {**extracts[1], "questions": extracts[1]["questions"] + [_short_q(2, 13)]}
    errors = _validate_listening_part_a({**_valid_content(), "extracts": extracts})
    assert any("Extract 2 must have exactly 12 questions" in e and "13" in e for e in errors)


# ── F. non-short_answer question fails ───────────────────────────────────

def test_mcq_question_fails():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = {**_short_q(1), "type": "mcq", "options": ["a", "b"]}
    errors = _validate_listening_part_a({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 question 1 must be type 'short_answer'" in e for e in errors)


# ── G. missing transcript ────────────────────────────────────────────────

def test_missing_transcript_fails():
    extracts = _valid_extracts()
    extracts[0] = {**extracts[0], "transcript": None}
    errors = _validate_listening_part_a({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 must have a non-empty transcript" in e for e in errors)


def test_empty_transcript_fails():
    extracts = _valid_extracts()
    extracts[1] = {**extracts[1], "transcript": []}
    errors = _validate_listening_part_a({**_valid_content(), "extracts": extracts})
    assert any("Extract 2 must have a non-empty transcript" in e for e in errors)


# ── H. missing body ───────────────────────────────────────────────────────

def test_missing_body_fails():
    extracts = _valid_extracts()
    extracts[0] = {**extracts[0], "body": ""}
    errors = _validate_listening_part_a({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 is missing a body" in e for e in errors)


# ── I. invalid answers ────────────────────────────────────────────────────

def test_blank_correct_answer_fails():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = _short_q(1, answer="")
    errors = _validate_listening_part_a({**_valid_content(), "extracts": extracts})
    assert any("Extract 1 question 1 must have a non-empty correct_answer" in e for e in errors)


def test_accepted_answers_must_be_list_of_strings():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = {**_short_q(1), "accepted_answers": "not a list"}
    errors = _validate_listening_part_a({**_valid_content(), "extracts": extracts})
    assert any("'accepted_answers' must be a list of non-empty strings" in e for e in errors)


def test_accepted_answers_valid_list_passes():
    extracts = _valid_extracts()
    extracts[0]["questions"][0] = {**_short_q(1), "accepted_answers": ["3 days", "three days"]}
    assert _validate_listening_part_a({**_valid_content(), "extracts": extracts}) == []


# ── J. wrong prep_seconds / audio_mode ────────────────────────────────────

def test_wrong_prep_seconds_fails():
    content = {**_valid_content(), "prep_seconds": 15}
    errors = _validate_listening_part_a(content)
    assert any("'prep_seconds' must be 30" in e for e in errors)


def test_wrong_audio_mode_fails():
    content = {**_valid_content(), "audio_mode": "monologue"}
    errors = _validate_listening_part_a(content)
    assert any("'audio_mode' must be 'dialogue'" in e for e in errors)


# ── K. duplicate question content ─────────────────────────────────────────

def test_duplicate_question_content_fails():
    extracts = _valid_extracts()
    extracts[1]["questions"][0] = {**_short_q(1), "content": extracts[0]["questions"][0]["content"]}
    errors = _validate_listening_part_a({**_valid_content(), "extracts": extracts})
    assert any("Duplicate question text" in e for e in errors)


# ── wiring into _validate() ───────────────────────────────────────────────

def test_validate_raises_on_structural_violation():
    content = {**_valid_content(), "extracts": _valid_extracts()[:1]}
    with pytest.raises(DraftGenerationError, match="locked contract"):
        _validate("listening", content)


def test_validate_passes_valid_part_a():
    assert _validate("listening", _valid_content()) == []
