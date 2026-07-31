"""
Tests for the feedback splitter behind GET /submissions/{id}
(app.routers.submissions._parse_feedback).

Pure unit test -- no Supabase. The invariant that matters: the session-detail
page gets either a scored dict or plain text, never both and never a raw JSON
fragment, no matter which era the row was written in.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.submissions import _parse_feedback


def test_scored_json_object_becomes_the_dict():
    stored = json.dumps({"scores": {"purpose": {"score": 2}}, "overall_score": 350})
    feedback, text = _parse_feedback(stored)
    assert text is None
    assert feedback["overall_score"] == 350
    assert feedback["scores"]["purpose"]["score"] == 2


def test_plain_text_row_becomes_text():
    feedback, text = _parse_feedback("Nice work on empathy.")
    assert feedback is None
    assert text == "Nice work on empathy."


def test_no_feedback_placeholder_is_text_not_json():
    feedback, text = _parse_feedback("No feedback")
    assert feedback is None
    assert text == "No feedback"


def test_truncated_json_does_not_raise():
    # /progress/stats truncates to 100 chars; a row saved that way is invalid
    # JSON and must degrade to text rather than 500 the request.
    feedback, text = _parse_feedback('{"scores": {"purpose": {"sco')
    assert feedback is None
    assert text == '{"scores": {"purpose": {"sco'


def test_json_scalar_is_text_not_dict():
    feedback, text = _parse_feedback("42")
    assert feedback is None
    assert text == "42"


def test_json_list_is_text_not_dict():
    feedback, text = _parse_feedback('["a", "b"]')
    assert feedback is None
    assert text is not None


def test_empty_and_null_yield_nothing():
    assert _parse_feedback(None) == (None, None)
    assert _parse_feedback("") == (None, None)


if __name__ == "__main__":
    test_scored_json_object_becomes_the_dict()
    test_plain_text_row_becomes_text()
    test_no_feedback_placeholder_is_text_not_json()
    test_truncated_json_does_not_raise()
    test_json_scalar_is_text_not_dict()
    test_json_list_is_text_not_dict()
    test_empty_and_null_yield_nothing()
    print("ok")
