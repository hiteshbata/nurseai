"""Phase 3B-2 -- Reading prompt builder's Part A branch (app.services.prompt_builder).
Prompt-string assertions only. No AI calls, no Gemini spend.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.prompt_builder import build_reading_prompt

KWARGS = dict(difficulty="intermediate", specialty="cardiology", topic="heart failure")


def test_default_part_none_unchanged():
    _, user = build_reading_prompt(**KWARGS)
    assert "Part A" not in user
    assert "Text A" not in user
    assert "short_answer" not in user
    assert "roughly 700-900 words" in user


def test_part_a_contract():
    _, user = build_reading_prompt(**KWARGS, part="A")
    for marker in [
        "Reading Part A",
        "FOUR", "Text A", "Text B", "Text C", "Text D",
        "matching", "mcq", "short_answer", "options",
    ]:
        assert marker in user, f"missing: {marker}"
    assert "correct_answer" in user


def test_part_bc_untouched():
    _, user_default = build_reading_prompt(**KWARGS)
    _, user_none = build_reading_prompt(**KWARGS, part=None)
    assert user_default == user_none


def test_part_a_body_format_uses_standalone_headers():
    """Phase 3B-6A -- PART_A_HEADER (app/routers/reading.py) only matches a
    header on its own line; the prompt must demonstrate that form, not
    "Text A: ..." with content appended on the same line."""
    _, user = build_reading_prompt(**KWARGS, part="A")
    assert "Text A\n" in user
    assert "Text B\n" in user
    assert "Text C\n" in user
    assert "Text D\n" in user
    assert "Text A: " not in user
    assert "Text B: " not in user
    assert "Text C: " not in user
    assert "Text D: " not in user


def test_part_a_exact_question_distribution_instructed():
    """Phase 3B-6A -- the prompt must state the exact locked 5/8/7
    distribution _validate_reading_part_a enforces, not "roughly 20"."""
    _, user = build_reading_prompt(**KWARGS, part="A")
    assert "EXACTLY 20 questions" in user
    assert "Q1-Q5" in user and "EXACTLY 5" in user
    assert "Q6-Q13" in user and "EXACTLY 8" in user
    assert "Q14-Q20" in user and "EXACTLY 7" in user
    assert "5 mcq + 15 short_answer = 20" in user
    assert "roughly 20" not in user


def test_part_a_avoids_heading_question_leakage():
    """Phase 3B-8 -- Generation #2 review: Q1/Q2/Q5 were answerable by matching
    a text heading's wording to the question instead of scanning content."""
    _, user = build_reading_prompt(**KWARGS, part="A")
    assert "heading" in user.lower()
    assert "echo" in user.lower() or "keyword" in user.lower()
    assert "paraphrase" in user.lower() or "not restated" in user.lower()


def test_part_a_requires_source_diversity():
    """Phase 3B-8 -- all four texts used near-identical bullet/protocol style,
    reducing realism. Prompt must ask for varied source presentation."""
    _, user = build_reading_prompt(**KWARGS, part="A")
    assert "divers" in user.lower()
    assert "same" in user.lower() and "style" in user.lower()


def test_part_a_requires_unique_short_answer():
    """Phase 3B-8 -- Q9 accepted either "intramuscularly" or "subcutaneously"
    alone even though the text supported both; answer must be uniquely
    defensible."""
    _, user = build_reading_prompt(**KWARGS, part="A")
    assert "exactly one" in user.lower() or "uniquely defensible" in user.lower()
    assert "intramuscularly" in user.lower() or "more than one valid answer" in user.lower()


def test_part_a_requires_grammatical_completions():
    """Phase 3B-8 -- Q7 sentence-completion grammar was awkward once the
    answer was inserted into the blank."""
    _, user = build_reading_prompt(**KWARGS, part="A")
    assert "grammatical" in user.lower() or "grammatically natural" in user.lower()
    assert "QUESTION + CORRECT_ANSWER" in user or "inserted into the blank" in user.lower()


if __name__ == "__main__":
    test_default_part_none_unchanged()
    test_part_a_contract()
    test_part_bc_untouched()
    test_part_a_body_format_uses_standalone_headers()
    test_part_a_exact_question_distribution_instructed()
    test_part_a_avoids_heading_question_leakage()
    test_part_a_requires_source_diversity()
    test_part_a_requires_unique_short_answer()
    test_part_a_requires_grammatical_completions()
    print("ok")
