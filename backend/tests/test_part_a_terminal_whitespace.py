"""Phase 3B-10 -- normalize whitespace before terminal punctuation in
Reading Part A generated question content. Gemini generation #3 report
flagged Q8/Q9/Q11/Q12/Q13 rendering as "...below ." -- exact raw strings
weren't retained, so these tests exercise the normalization rule directly
(remove whitespace immediately before terminal . ? !), not a reproduction
of that specific output.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.draft_generator import (
    _strip_terminal_punct_whitespace,
    _normalize_part_a_question_content,
)


def test_whitespace_before_period_removed():
    assert _strip_terminal_punct_whitespace("foo .") == "foo."


def test_multiple_spaces_before_period_removed():
    assert _strip_terminal_punct_whitespace("foo   .") == "foo."


def test_whitespace_before_question_mark_removed():
    assert _strip_terminal_punct_whitespace("foo ?") == "foo?"


def test_whitespace_before_exclamation_removed():
    assert _strip_terminal_punct_whitespace("foo !") == "foo!"


def test_no_whitespace_unchanged():
    assert _strip_terminal_punct_whitespace("foo.") == "foo."


def test_internal_whitespace_unchanged():
    text = "The patient should be monitored closely for signs of distress."
    assert _strip_terminal_punct_whitespace(text) == text


def test_decimal_numbers_unchanged():
    text = "Administer 0.5 mg via IV push."
    assert _strip_terminal_punct_whitespace(text) == text


def test_ranges_unchanged():
    text = "Normal range is 10-20 mmHg."
    assert _strip_terminal_punct_whitespace(text) == text


def test_blank_placeholder_preserved():
    assert _strip_terminal_punct_whitespace("The patient should be monitored ______ .") == \
        "The patient should be monitored ______."


def test_mid_sentence_period_not_touched():
    # "e.g." has no space before its periods to begin with -- untouched by construction.
    text = "Use PRN meds (e.g. paracetamol) as ordered."
    assert _strip_terminal_punct_whitespace(text) == text


def test_normalize_part_a_question_content_only_touches_content_field():
    content = {
        "title": "t",
        "part": "A",
        "body": "Text A\nSome information ............ .\n\nText B\nmore",
        "questions": [
            {"content": "In which text is X mentioned ?", "type": "mcq",
             "options": ["Text A", "Text B", "Text C", "Text D"], "correct_answer": "Text B ."},
            {"content": "The nurse should assess the patient ______ .", "type": "short_answer",
             "options": [], "correct_answer": "immediately ."},
        ],
    }
    _normalize_part_a_question_content(content)

    # question content cleaned
    assert content["questions"][0]["content"] == "In which text is X mentioned?"
    assert content["questions"][1]["content"] == "The nurse should assess the patient ______."
    # body (Text A-D) and answer strings left alone
    assert content["body"] == "Text A\nSome information ............ .\n\nText B\nmore"
    assert content["questions"][0]["correct_answer"] == "Text B ."
    assert content["questions"][1]["correct_answer"] == "immediately ."


def test_normalize_part_a_question_content_no_questions_key_is_noop():
    content = {"title": "t", "part": "A", "body": "x"}
    _normalize_part_a_question_content(content)  # must not raise
    assert content == {"title": "t", "part": "A", "body": "x"}


def test_normal_existing_short_answer_question_unchanged():
    q_content = "What device is used to administer oxygen to the patient?"
    assert _strip_terminal_punct_whitespace(q_content) == q_content
