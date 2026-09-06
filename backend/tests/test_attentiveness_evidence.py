"""Tests for the Relationship Building attentive/respectful interaction (A2)
detector (Step 21H). Same style as test_information_gathering_evidence.py --
purely regex/keyword-based, every assertion checked against the detector's
actual output. No score assignments anywhere (Step 20/32 of the task spec):
only presence/absence of evidence.
"""
from app.services.attentiveness_evidence import (
    EVENT_ACKNOWLEDGEMENT,
    EVENT_ACKNOWLEDGEMENT_UNCERTAIN,
    EVENT_REFLECTIVE_RESPONSE,
    EVENT_REFLECTIVE_RESPONSE_UNCERTAIN,
    PROVENANCE_DETERMINISTIC,
    AcknowledgementEvent,
    AttentivenessEvidence,
    ReflectiveResponseEvent,
    detect_acknowledgement_events,
    detect_attentiveness_evidence,
    detect_reflective_response_events,
)


def _turns(*pairs):
    return [{"role": role, "content": content} for role, content in pairs]


# ── Acknowledgement golden cases ─────────────────────────────────────────

def test_explicit_interpersonal_acknowledgement():
    events = detect_acknowledgement_events(_turns(("nurse", "I see.")))
    assert events == [AcknowledgementEvent(
        turn_index=0, evidence_text="I see.", event_type=EVENT_ACKNOWLEDGEMENT,
    )]


def test_acknowledgement_following_patient_concern():
    events = detect_acknowledgement_events(_turns(
        ("patient", "I've been struggling with the injections."),
        ("nurse", "I see. Tell me more about what's worrying you."),
    ))
    assert len(events) == 1
    assert events[0].turn_index == 1
    assert events[0].evidence_text == "I see."


def test_multiple_acknowledgement_forms():
    for text in [
        "I understand.", "I hear you.", "That makes sense.",
        "Thank you for telling me.", "Thank you for sharing that.",
        "Thank you for explaining.", "Thanks for explaining that.",
        "I see what you mean.", "Okay, I understand.",
    ]:
        events = detect_acknowledgement_events(_turns(("nurse", text)))
        assert len(events) == 1 and events[0].event_type == EVENT_ACKNOWLEDGEMENT, text


def test_clinical_i_understand_false_positive():
    """Step 22: must NOT automatically become attentive interaction."""
    assert detect_acknowledgement_events(_turns(
        ("nurse", "I understand the medication schedule."),
    )) == []


def test_okay_prefix_false_positive():
    """Step 22: must NOT become acknowledgement merely because it begins
    with 'Okay'."""
    assert detect_acknowledgement_events(_turns(
        ("nurse", "Okay, take this twice daily."),
    )) == []


def test_patient_speaker_false_positive():
    """Step 9/22: patient turns must never become candidate evidence."""
    assert detect_acknowledgement_events(_turns(("patient", "I understand."))) == []


def test_ambiguous_uncertain_acknowledgement_contrastive_pivot():
    events = detect_acknowledgement_events(_turns(
        ("nurse", "I understand, but we still need to proceed."),
    ))
    assert len(events) == 1
    assert events[0].event_type == EVENT_ACKNOWLEDGEMENT_UNCERTAIN


def test_multiple_acknowledgement_events_in_one_session():
    events = detect_acknowledgement_events(_turns(
        ("nurse", "I see."),
        ("patient", "It's been hard."),
        ("nurse", "Thank you for sharing that."),
    ))
    assert len(events) == 2
    assert [e.turn_index for e in events] == [0, 2]


def test_determinism():
    turns = _turns(("nurse", "I see."))
    assert detect_acknowledgement_events(turns) == detect_acknowledgement_events(turns)


def test_provenance_and_evidence_level():
    events = detect_acknowledgement_events(_turns(("nurse", "I see.")))
    assert events[0].provenance == PROVENANCE_DETERMINISTIC
    assert events[0].evidence_level == "L2_deterministic"


def test_acknowledgement_serialization_round_trip():
    events = detect_acknowledgement_events(_turns(("nurse", "I see.")))
    restored = AcknowledgementEvent.model_validate(events[0].model_dump())
    assert restored == events[0]


# ── Reflective response golden cases ─────────────────────────────────────

def test_reflective_response_with_lexical_overlap():
    events = detect_reflective_response_events(_turns(
        ("patient", "I'm worried about the injections."),
        ("nurse", "You're worried the injections may be painful."),
    ))
    assert len(events) == 1
    assert events[0].event_type == EVENT_REFLECTIVE_RESPONSE
    assert events[0].turn_index == 1
    assert events[0].related_patient_turns == [0]


def test_reflective_response_uncertain_no_overlap():
    events = detect_reflective_response_events(_turns(
        ("patient", "I'm worried about the injections."),
        ("nurse", "You're feeling quite nervous today."),
    ))
    assert len(events) == 1
    assert events[0].event_type == EVENT_REFLECTIVE_RESPONSE_UNCERTAIN


def test_reflective_response_delayed_never_invents_relationship():
    """A reflection-shaped sentence still links only to the immediately
    preceding patient turn, never back to an earlier one (Step 2)."""
    events = detect_reflective_response_events(_turns(
        ("patient", "I'm worried about the injections."),
        ("nurse", "Let's talk about your medication first."),
        ("patient", "Okay."),
        ("nurse", "You're worried about the injections."),
    ))
    assert len(events) == 1
    assert events[0].related_patient_turns == [2]
    assert events[0].event_type == EVENT_REFLECTIVE_RESPONSE_UNCERTAIN


def test_reflective_response_no_preceding_patient_turn():
    events = detect_reflective_response_events(_turns(
        ("patient", "I'm worried about the injections."),
        ("nurse", "You're worried about the injections."),
        ("nurse", "You're worried about the injections, right?"),
    ))
    assert len(events) == 1
    assert events[0].turn_index == 1


def test_reflective_response_speaker_attribution():
    assert detect_reflective_response_events(_turns(
        ("patient", "I'm worried."),
        ("patient", "You're right, it's scary."),
    )) == []


def test_reflective_response_serialization_round_trip():
    events = detect_reflective_response_events(_turns(
        ("patient", "I'm worried about the injections."),
        ("nurse", "You're worried the injections may be painful."),
    ))
    restored = ReflectiveResponseEvent.model_validate(events[0].model_dump())
    assert restored == events[0]


# ── Dismissive evidence reuse (Step 7) ───────────────────────────────────

def test_dismissive_reuse_via_bundling_view():
    bundled = detect_attentiveness_evidence(_turns(
        ("patient", "I'm scared."),
        ("nurse", "Don't worry, you'll be fine."),
    ))
    assert len(bundled.dismissive_interaction_events) == 1
    assert bundled.dismissive_interaction_events[0]["turn_index"] == 1


def test_no_dismissive_evidence_is_empty_not_positive():
    bundled = detect_attentiveness_evidence(_turns(("nurse", "I see.")))
    assert bundled.dismissive_interaction_events == []


# ── Bundle model ──────────────────────────────────────────────────────────

def test_bundle_shape_and_limitations_present():
    bundled = detect_attentiveness_evidence(_turns(("nurse", "I see.")))
    assert isinstance(bundled, AttentivenessEvidence)
    assert len(bundled.acknowledgement_events) == 1
    assert bundled.limitations  # non-empty, documents the detector's own ceiling


def test_empty_history_is_empty_not_negative():
    bundled = detect_attentiveness_evidence([])
    assert bundled.acknowledgement_events == []
    assert bundled.reflective_response_events == []
    assert bundled.dismissive_interaction_events == []
