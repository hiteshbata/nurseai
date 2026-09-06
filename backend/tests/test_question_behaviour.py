"""Tests for the Information Gathering question-behaviour detector (Step 21A).

detect_question_events is keyword/regex-based, same style as
patient_state.detect_nurse_events -- every assertion here was checked
against the detector's actual output on a literal phrase it matches.
"""
from app.services.question_behaviour import detect_question_events


def _events(text):
    return {e["event"] for e in detect_question_events(text)}


def test_statement_has_no_question_events():
    assert detect_question_events("You have hypertension, we need to monitor it.") == []


def test_wh_word_is_open_question():
    events = detect_question_events("What brings you in today?")
    assert events == [{"event": "open_question", "evidence": "What brings you in today?"}]


def test_tell_me_about_phrase_is_open_even_with_closed_starter():
    # "Can you..." starts with a closed-form auxiliary, but the invitation
    # phrase makes this functionally an open question -- the phrase check
    # must win over the bare first-word aux check.
    assert "open_question" in _events("Can you tell me about your symptoms?")


def test_aux_starter_is_closed_question():
    events = detect_question_events("Do you have any allergies?")
    assert events == [{"event": "closed_question", "evidence": "Do you have any allergies?"}]


def test_two_question_marks_in_one_turn_is_compound():
    assert "compound_question" in _events("Do you smoke? Do you drink alcohol?")


def test_and_joined_closed_clauses_is_compound():
    assert "compound_question" in _events("Have you had this before and is it getting worse?")


def test_single_simple_question_is_not_compound():
    assert "compound_question" not in _events("How long have you had this pain?")


def test_tag_question_is_leading():
    events = detect_question_events("You don't smoke, do you?")
    assert any(e["event"] == "leading_question" for e in events)


def test_presupposition_phrase_is_leading():
    assert "leading_question" in _events("Don't you think you should cut down on salt?")


def test_plain_question_is_not_leading():
    assert "leading_question" not in _events("What medications are you currently taking?")


def test_leading_tag_question_still_gets_open_or_closed_classification():
    # A leading question is still ONE question with its own D2 shape --
    # D2 and D3 are independent axes on the same turn.
    events = detect_question_events("You don't smoke, do you?")
    event_names = {e["event"] for e in events}
    assert "leading_question" in event_names
    assert "closed_question" in event_names
