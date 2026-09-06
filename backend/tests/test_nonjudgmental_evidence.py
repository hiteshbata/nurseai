"""Tests for the Relationship Building non-judgmental approach (A3) detector
(Step 21I). Same style as test_attentiveness_evidence.py -- purely regex/
keyword-based, every assertion checked against the detector's actual output.
No score/band/judgement assignments anywhere: only presence/absence of
evidence (module docstring's HARD RULE).
"""
from app.services.nonjudgmental_evidence import (
    EVENT_POTENTIALLY_JUDGMENTAL,
    EVENT_SUPPORTIVE_NONJUDGMENTAL,
    EVENT_UNCERTAIN_JUDGMENT,
    PROVENANCE_DETERMINISTIC,
    NonJudgmentalEvent,
    NonJudgmentalEvidence,
    detect_nonjudgmental_events,
    detect_nonjudgmental_evidence,
)


def _turns(*pairs):
    return [{"role": role, "content": content} for role, content in pairs]


# ── Potentially judgmental golden cases ──────────────────────────────────

def test_explicit_blame_should_have():
    events = detect_nonjudgmental_events(_turns(
        ("patient", "I stopped taking the medication because it was painful."),
        ("nurse", "You should have continued it."),
    ))
    assert len(events) == 1
    assert events[0].event_type == EVENT_POTENTIALLY_JUDGMENTAL
    assert events[0].turn_index == 1
    assert events[0].evidence_text == "You should have continued it."
    assert events[0].related_patient_turns == [0]


def test_explicit_non_compliance_judgement():
    events = detect_nonjudgmental_events(_turns(("nurse", "You didn't follow the advice.")))
    assert len(events) == 1 and events[0].event_type == EVENT_POTENTIALLY_JUDGMENTAL


def test_explicit_criticism_careless():
    events = detect_nonjudgmental_events(_turns(("nurse", "You've been careless with your medication.")))
    assert len(events) == 1 and events[0].event_type == EVENT_POTENTIALLY_JUDGMENTAL


def test_explicit_criticism_ignored():
    events = detect_nonjudgmental_events(_turns(("nurse", "You ignored the instructions.")))
    assert len(events) == 1 and events[0].event_type == EVENT_POTENTIALLY_JUDGMENTAL


def test_only_yourself_to_blame():
    events = detect_nonjudgmental_events(_turns(("nurse", "You've only got yourself to blame.")))
    assert len(events) == 1 and events[0].event_type == EVENT_POTENTIALLY_JUDGMENTAL


def test_should_have_known_better():
    events = detect_nonjudgmental_events(_turns(("nurse", "You should have known better.")))
    assert len(events) == 1 and events[0].event_type == EVENT_POTENTIALLY_JUDGMENTAL


# ── Clinical instruction false positives (Step 9/24) ─────────────────────

def test_clinical_should_false_positive():
    assert detect_nonjudgmental_events(_turns(
        ("nurse", "You should call us if the pain gets worse."),
    )) == []


def test_clinical_must_false_positive():
    assert detect_nonjudgmental_events(_turns(
        ("nurse", "You must go to the emergency department if you become severely short of breath."),
    )) == []


def test_clinical_need_to_false_positive():
    assert detect_nonjudgmental_events(_turns(
        ("nurse", "You need to take this medication twice daily."),
    )) == []


# ── Uncertain golden cases (Step 8/11) ────────────────────────────────────

def test_why_didnt_you_uncertain():
    events = detect_nonjudgmental_events(_turns(("nurse", "Why didn't you take the medication?")))
    assert len(events) == 1 and events[0].event_type == EVENT_UNCERTAIN_JUDGMENT


def test_why_havent_you_uncertain():
    events = detect_nonjudgmental_events(_turns(("nurse", "Why haven't you been doing this?")))
    assert len(events) == 1 and events[0].event_type == EVENT_UNCERTAIN_JUDGMENT


def test_why_didnt_you_never_upgraded_to_judgmental_by_word_order_alone():
    """A question ('didn't you follow') has the opposite word order from
    the declarative judgmental pattern ('you didn't follow') -- must stay
    uncertain, not be promoted to judgmental."""
    events = detect_nonjudgmental_events(_turns(("nurse", "Why didn't you follow the advice?")))
    assert len(events) == 1 and events[0].event_type == EVENT_UNCERTAIN_JUDGMENT


# ── Supportive golden cases ───────────────────────────────────────────────

def test_supportive_normalisation():
    events = detect_nonjudgmental_events(_turns(
        ("nurse", "It's understandable that you struggled with this."),
    ))
    assert len(events) == 1 and events[0].event_type == EVENT_SUPPORTIVE_NONJUDGMENTAL


def test_supportive_many_people_find_this_difficult():
    events = detect_nonjudgmental_events(_turns(("nurse", "Many people find this difficult.")))
    assert len(events) == 1 and events[0].event_type == EVENT_SUPPORTIVE_NONJUDGMENTAL


def test_supportive_thank_you_for_being_honest():
    events = detect_nonjudgmental_events(_turns(("nurse", "Thank you for being honest about that.")))
    assert len(events) == 1 and events[0].event_type == EVENT_SUPPORTIVE_NONJUDGMENTAL


# ── Speaker attribution (Step 13) ─────────────────────────────────────────

def test_patient_speaker_false_positive():
    assert detect_nonjudgmental_events(_turns(
        ("patient", "You should have told me sooner."),
    )) == []


# ── A3 vs A4 / A2 independence (Step 4/5/9, Step 18/19) ───────────────────

def test_a3_supportive_and_a4_empathy_overlap_not_deduplicated():
    """'I can understand why...' fires A4's empathy lexicon (patient_state);
    'there's no need to feel embarrassed' independently fires this module's
    supportive pattern -- both must survive, on the same turn."""
    from app.services.patient_state import detect_nurse_events

    text = "I can understand why that happened, and there's no need to feel embarrassed about it."
    nurse_events = detect_nurse_events(text)
    assert any(e["event"] == "empathy_acknowledgement" for e in nurse_events)

    a3_events = detect_nonjudgmental_events(_turns(("nurse", text)))
    assert any(e.event_type == EVENT_SUPPORTIVE_NONJUDGMENTAL for e in a3_events)


def test_a3_supportive_and_a2_acknowledgement_overlap_not_deduplicated():
    """'Thank you for telling me.' fires A2's acknowledgement lexicon
    (attentiveness_evidence); 'Many people find this difficult.' independently
    fires this module's supportive pattern -- both fire, same turn."""
    from app.services.attentiveness_evidence import detect_acknowledgement_events

    history = _turns(("nurse", "Thank you for telling me. Many people find this difficult."))
    a2_events = detect_acknowledgement_events(history)
    assert len(a2_events) == 1 and a2_events[0].evidence_text == "Thank you for telling me."

    a3_events = detect_nonjudgmental_events(history)
    assert len(a3_events) == 1
    assert a3_events[0].evidence_text == "Many people find this difficult."
    assert a3_events[0].event_type == EVENT_SUPPORTIVE_NONJUDGMENTAL


def test_a3_uncertain_and_d_family_open_question_coexist():
    """A judgmental-shaped question independently remains D-family open-
    question evidence -- this detector never suppresses or changes
    question_behaviour's own output."""
    from app.services.question_behaviour import detect_question_events

    text = "Why didn't you follow the advice?"
    q_events = detect_question_events(text)
    assert any(e["event"] == "open_question" for e in q_events)

    a3_events = detect_nonjudgmental_events(_turns(("nurse", text)))
    assert len(a3_events) == 1 and a3_events[0].event_type == EVENT_UNCERTAIN_JUDGMENT


# ── Multi-turn context linkage (Step 12) ──────────────────────────────────

def test_multi_turn_linkage_to_immediately_preceding_patient_turn():
    events = detect_nonjudgmental_events(_turns(
        ("patient", "I stopped taking it because the injections hurt."),
        ("nurse", "You should have continued it."),
    ))
    assert events[0].related_patient_turns == [0]


def test_no_linkage_when_preceding_turn_is_not_patients():
    events = detect_nonjudgmental_events(_turns(
        ("nurse", "Let's talk about your medication."),
        ("nurse", "You should have continued it."),
    ))
    assert len(events) == 1 and events[0].related_patient_turns == []


def test_no_linkage_at_start_of_transcript():
    events = detect_nonjudgmental_events(_turns(("nurse", "You should have continued it.")))
    assert events[0].related_patient_turns == []


# ── Determinism / provenance / evidence level / serialization ────────────

def test_determinism():
    turns = _turns(("nurse", "You should have continued it."))
    assert detect_nonjudgmental_events(turns) == detect_nonjudgmental_events(turns)


def test_provenance_and_evidence_level():
    events = detect_nonjudgmental_events(_turns(("nurse", "You should have continued it.")))
    assert events[0].provenance == PROVENANCE_DETERMINISTIC
    assert events[0].evidence_level == "L2_deterministic"


def test_serialization_round_trip():
    events = detect_nonjudgmental_events(_turns(("nurse", "You should have continued it.")))
    restored = NonJudgmentalEvent.model_validate(events[0].model_dump())
    assert restored == events[0]


# ── Missing vs negative (Step 16/17) ──────────────────────────────────────

def test_no_judgmental_language_is_empty_not_positive():
    """Absence of a potentially_judgmental event must never be surfaced as
    proof of a non-judgmental performance -- see module docstring HARD RULE."""
    bundled = detect_nonjudgmental_evidence(_turns(("nurse", "Hello, how are you today?")))
    assert bundled.potentially_judgmental_events == []
    assert bundled.supportive_nonjudgmental_events == []
    assert bundled.uncertain_events == []


def test_empty_history_is_empty_not_negative():
    bundled = detect_nonjudgmental_evidence([])
    assert bundled.potentially_judgmental_events == []
    assert bundled.supportive_nonjudgmental_events == []
    assert bundled.uncertain_events == []


# ── Bundle model ────────────────────────────────────────────────────────

def test_bundle_shape_and_limitations_present():
    bundled = detect_nonjudgmental_evidence(_turns(("nurse", "You should have continued it.")))
    assert isinstance(bundled, NonJudgmentalEvidence)
    assert len(bundled.potentially_judgmental_events) == 1
    assert bundled.limitations  # non-empty, documents the detector's own ceiling


def test_multiple_a3_events_across_session():
    events = detect_nonjudgmental_events(_turns(
        ("nurse", "You should have continued it."),
        ("patient", "I was scared."),
        ("nurse", "It's understandable that you struggled with this."),
    ))
    assert len(events) == 2
    assert [e.turn_index for e in events] == [0, 2]
    assert {e.event_type for e in events} == {EVENT_POTENTIALLY_JUDGMENTAL, EVENT_SUPPORTIVE_NONJUDGMENTAL}
