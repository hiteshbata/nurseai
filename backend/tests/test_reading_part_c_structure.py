"""Phase 4C-3 -- deterministic structural validation for a freshly-generated
Reading Part C draft (the locked contract: 2 independent long-form texts,
each its own passage with exactly 8 mcq questions over exactly 4 options).
Pure unit tests against _validate_reading_part_c -- no supabase, no AI call.
_validate() wiring is covered by the "raises" tests at the bottom, mirroring
test_reading_part_a_structure.py / test_reading_part_b_structure.py's pattern.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.draft_generator import _validate, _validate_reading_part_c, DraftGenerationError


def _mcq_q(n=1, q=1, answer="Option B"):
    return {
        "content": f"What does text {n} question {q} ask about?",
        "type": "mcq",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": answer,
    }


def _text(n=1):
    return {
        "title": f"Feature {n}",
        "body": f"This is the long-form journalistic body of feature {n}.",
        "questions": [_mcq_q(n, q) for q in range(1, 9)],
    }


def _valid_texts():
    return [_text(n) for n in range(1, 3)]


def _valid_content():
    return {"part": "C", "texts": _valid_texts()}


# ── A. valid structure passes ────────────────────────────────────────────

def test_valid_payload_passes():
    assert _validate_reading_part_c(_valid_content()) == []


# ── B. wrong part value fails ────────────────────────────────────────────

def test_wrong_part_fails():
    content = {**_valid_content(), "part": "B"}
    errors = _validate_reading_part_c(content)
    assert any("'part' must be 'C'" in e for e in errors)


# ── C. missing texts fails ───────────────────────────────────────────────

def test_missing_texts_fails():
    content = {"part": "C"}
    errors = _validate_reading_part_c(content)
    assert any("'texts' must be a list" in e for e in errors)


# ── D/E. wrong text count ────────────────────────────────────────────────

def test_one_text_fails():
    content = {**_valid_content(), "texts": _valid_texts()[:1]}
    errors = _validate_reading_part_c(content)
    assert any("exactly 2 texts" in e and "1" in e for e in errors)


def test_three_texts_fails():
    content = {**_valid_content(), "texts": _valid_texts() + [_text(3)]}
    errors = _validate_reading_part_c(content)
    assert any("exactly 2 texts" in e and "3" in e for e in errors)


# ── F/G. wrong question count per text ───────────────────────────────────

def test_text_with_seven_questions_fails():
    texts = _valid_texts()
    texts[0] = {**texts[0], "questions": texts[0]["questions"][:7]}
    errors = _validate_reading_part_c({**_valid_content(), "texts": texts})
    assert any("Text 1 must have exactly 8 questions" in e and "7" in e for e in errors)


def test_text_with_nine_questions_fails():
    texts = _valid_texts()
    texts[1] = {**texts[1], "questions": texts[1]["questions"] + [_mcq_q(2, 9)]}
    errors = _validate_reading_part_c({**_valid_content(), "texts": texts})
    assert any("Text 2 must have exactly 8 questions" in e and "9" in e for e in errors)


# ── H. wrong question type fails ─────────────────────────────────────────

def test_short_answer_question_fails():
    texts = _valid_texts()
    texts[0]["questions"][0] = {**_mcq_q(1, 1), "type": "short_answer"}
    errors = _validate_reading_part_c({**_valid_content(), "texts": texts})
    assert any("Text 1 question 1 must be type 'mcq'" in e for e in errors)


# ── I/J. wrong option count ──────────────────────────────────────────────

def test_three_option_mcq_fails():
    texts = _valid_texts()
    texts[0]["questions"][0] = {**_mcq_q(1, 1), "options": ["A", "B", "C"]}
    errors = _validate_reading_part_c({**_valid_content(), "texts": texts})
    assert any("Text 1 question 1 must have exactly 4 options" in e for e in errors)


def test_five_option_mcq_fails():
    texts = _valid_texts()
    texts[0]["questions"][0] = {**_mcq_q(1, 1), "options": ["A", "B", "C", "D", "E"]}
    errors = _validate_reading_part_c({**_valid_content(), "texts": texts})
    assert any("Text 1 question 1 must have exactly 4 options" in e for e in errors)


# ── K. invalid correct_answer ────────────────────────────────────────────

def test_invalid_correct_answer_fails():
    texts = _valid_texts()
    texts[0]["questions"][0] = _mcq_q(1, 1, answer="Option E")
    errors = _validate_reading_part_c({**_valid_content(), "texts": texts})
    assert any("Text 1 question 1 correct_answer must exactly match" in e for e in errors)


# ── L. duplicate question content fails ──────────────────────────────────

def test_duplicate_question_content_fails():
    texts = _valid_texts()
    texts[1]["questions"][0] = {**_mcq_q(2, 1), "content": texts[0]["questions"][0]["content"]}
    errors = _validate_reading_part_c({**_valid_content(), "texts": texts})
    assert any("Duplicate question text" in e for e in errors)


# ── duplicate/empty options ──────────────────────────────────────────────

def test_duplicate_options_fails():
    texts = _valid_texts()
    texts[0]["questions"][0] = {**_mcq_q(1, 1), "options": ["Option A", "Option A", "Option C", "Option D"]}
    errors = _validate_reading_part_c({**_valid_content(), "texts": texts})
    assert any("Text 1 question 1 has duplicate options" in e for e in errors)


# ── Part A/B still pass, Part C doesn't affect non-reading modules ──────

def test_validate_passes_valid_part_a_content():
    from app.services.draft_generator import _validate_reading_part_a
    body = "Text A\nfirst\n\nText B\nsecond\n\nText C\nthird\n\nText D\nfourth"
    questions = [
        {"content": f"q{n}", "type": "mcq", "options": ["Text A", "Text B", "Text C", "Text D"], "correct_answer": "Text B"}
        for n in range(1, 6)
    ] + [
        {"content": f"q{n}", "type": "short_answer", "options": [], "correct_answer": f"a{n}"}
        for n in range(6, 21)
    ]
    content = {"title": "t", "part": "A", "body": body, "questions": questions}
    assert _validate_reading_part_a(content) == []
    assert _validate("reading", content) == []


def test_validate_passes_valid_part_b_content():
    from app.services.draft_generator import _validate_reading_part_b
    passages = [
        {
            "title": f"Extract {n}",
            "body": f"Body {n}",
            "questions": [{"content": f"q{n}", "type": "mcq", "options": ["A", "B", "C"], "correct_answer": "B"}],
        }
        for n in range(1, 7)
    ]
    content = {"part": "B", "passages": passages}
    assert _validate_reading_part_b(content) == []
    assert _validate("reading", content) == []


def test_validate_ignores_part_c_for_non_reading_modules():
    """A non-reading draft happening to contain part='C' must never be routed
    through the Part C validator -- that dispatch is gated on module=='reading'."""
    content = {"title": "t", "setting": "s", "nurse_card": {"role": "r"}, "interlocutor_card": {"persona": "p"}, "part": "C"}
    assert _validate("speaking", content) == []


# ── wiring into _validate() ───────────────────────────────────────────────

def test_validate_raises_on_structural_violation():
    content = {**_valid_content(), "texts": _valid_texts()[:1]}
    with pytest.raises(DraftGenerationError, match="locked contract"):
        _validate("reading", content)


def test_validate_passes_valid_part_c():
    assert _validate("reading", _valid_content()) == []


if __name__ == "__main__":
    import types
    mod = types.SimpleNamespace()
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok ({len(tests)} tests)")
