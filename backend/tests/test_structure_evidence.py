"""Tests for the Providing Structure (C2/C3) detector (Step 21B).

Same style as test_question_behaviour.py -- detect_structure_events /
detect_organization_sequences are keyword/regex-based, every assertion here
was checked against the detector's actual output on a literal phrase.
"""
from app.services.structure_evidence import (
    detect_organization_marker_events,
    detect_organization_sequences,
    detect_structure_events,
)


def _events(text):
    return {e["event"] for e in detect_structure_events(text)}


# ── C2 signposting ──────────────────────────────────────────────────────

def test_clear_topic_signpost():
    events = detect_structure_events("Now let's talk about your medication.")
    assert events == [
        {"event": "signposting_detected", "evidence": "Now let's talk about your medication."},
        {"event": "topic_transition_detected", "evidence": "your medication"},
    ]


def test_multiple_topic_signposts_in_one_turn():
    text = "Let's talk about your medication. Now let's move on to your diet."
    events = _events(text)
    assert events == {"signposting_detected", "topic_transition_detected"}
    assert sum(1 for e in detect_structure_events(text) if e["event"] == "signposting_detected") == 2


def test_ordinary_then_is_not_a_signpost():
    assert detect_structure_events("Then I felt better.") == []


def test_uncertain_transition():
    events = detect_structure_events("Now, about your diet, how much salt do you use?")
    assert events == [{"event": "signposting_uncertain", "evidence": "Now, about your diet, how much salt do you use?"}]


def test_topic_transition_without_explicit_marker_leaves_no_evidence():
    # A genuine topic change with no lexical marker at all -- Step 4: leave
    # the field unavailable rather than guessing.
    assert detect_structure_events("How is your appetite these days?") == []


def test_question_and_signpost_same_turn():
    events = detect_structure_events("Now let's talk about your medication. How often are you taking it?")
    assert "signposting_detected" in _events(
        "Now let's talk about your medication. How often are you taking it?"
    )
    assert any(e["event"] == "topic_transition_detected" for e in events)


def test_no_signposting():
    assert detect_structure_events("I understand this has been difficult for you.") == []


# ── C3 explanation organization ──────────────────────────────────────────

def _history(*nurse_turns):
    return [{"role": "nurse", "content": t} for t in nurse_turns]


def test_clear_numbered_explanation_opener():
    seqs = detect_organization_sequences(_history("There are three things I'd like to explain."))
    assert len(seqs) == 1
    assert seqs[0]["markers"][0]["type"] == "opener"


def test_first_second_finally_sequence_across_turns():
    history = [
        {"role": "nurse", "content": "There are three things I'd like to explain."},
        {"role": "patient", "content": "Okay."},
        {"role": "nurse", "content": "First, your medication."},
        {"role": "nurse", "content": "Second, your diet."},
        {"role": "nurse", "content": "Finally, your follow-up."},
    ]
    seqs = detect_organization_sequences(history)
    assert len(seqs) == 1
    seq = seqs[0]
    assert seq["turn_indexes"] == [0, 2, 3, 4]
    assert seq["partial"] is False
    assert [m["type"] for m in seq["markers"]] == ["opener", "ordinal", "ordinal", "ordinal"]


def test_partial_sequence():
    seqs = detect_organization_sequences(_history("First, let's look at your chart."))
    assert len(seqs) == 1
    assert seqs[0]["partial"] is True


def test_recap_summary_marker():
    seqs = detect_organization_sequences(_history("To recap, you'll take this twice daily."))
    assert len(seqs) == 1
    assert seqs[0]["markers"][0]["type"] == "summary"


def test_explanation_without_explicit_markers_is_no_sequence():
    history = _history(
        "First I checked your chart, then I confirmed with the doctor, then I called you in.",
    )
    assert detect_organization_sequences(history) == []


def test_multiple_explanation_sequences():
    history = [
        {"role": "nurse", "content": "First, your medication."},
        {"role": "nurse", "content": "Second, your dosage."},
        {"role": "patient", "content": "I see."},
        {"role": "nurse", "content": "How are you feeling otherwise?"},
        {"role": "patient", "content": "Fine, thanks."},
        {"role": "nurse", "content": "First, your diet."},
        {"role": "nurse", "content": "Second, your exercise."},
    ]
    seqs = detect_organization_sequences(history)
    assert len(seqs) == 2
    assert all(not s["partial"] for s in seqs)


def test_ambiguous_organizational_phrases_are_not_markers():
    history = _history(
        "First thing in the morning I take my medication.",
        "Next week you'll see the doctor.",
        "One thing led to another.",
    )
    assert detect_organization_sequences(history) == []


# ── Flattened events / integration shape ──────────────────────────────────

def test_organization_marker_events_flattening():
    history = [
        {"role": "nurse", "content": "First, your medication."},
        {"role": "nurse", "content": "Second, your diet."},
    ]
    events = detect_organization_marker_events(history)
    assert events == [
        {"event": "organization_marker", "turn_index": 0, "evidence": "First, your medication."},
        {"event": "organization_marker", "turn_index": 1, "evidence": "Second, your diet."},
    ]


def test_organization_marker_events_partial_naming():
    events = detect_organization_marker_events(_history("First, let's look at your chart."))
    assert events == [{"event": "organization_marker_partial", "turn_index": 0, "evidence": "First, let's look at your chart."}]


def test_determinism():
    text = "Now let's talk about your medication."
    assert detect_structure_events(text) == detect_structure_events(text)
    history = _history("First, your medication.", "Second, your diet.")
    assert detect_organization_sequences(history) == detect_organization_sequences(history)
