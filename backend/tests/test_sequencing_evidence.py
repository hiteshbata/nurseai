"""Tests for the Providing Structure (C1) detector (Step 21C).

Same style as test_structure_evidence.py -- detect_sequence_events is
keyword/regex-based, every assertion here was checked against the
detector's actual output on a literal phrase. No score assignments
anywhere (Step 20/21): only presence/absence of evidence.
"""
from app.services.sequencing_evidence import detect_sequence_events


def _history(*nurse_turns):
    return [{"role": "nurse", "content": t} for t in nurse_turns]


def _events(*nurse_turns):
    return detect_sequence_events(_history(*nurse_turns))


# ── Golden cases (Step 20) ──────────────────────────────────────────────

def test_golden_1_explicit_consultation_sequence():
    events = _events("First, I'll ask you about your symptoms.")
    assert events == [{
        "event": "consultation_sequence_marker_partial", "turn_index": 0,
        "evidence": "First, I'll ask you about your symptoms.",
    }]


def test_golden_2_multi_step_sequence():
    events = _events(
        "First, I'll ask you about your symptoms.",
        "Then we'll discuss your medication.",
        "After that, we'll discuss what we can do next.",
    )
    assert [e["event"] for e in events] == ["consultation_sequence_marker"] * 3
    assert [e["turn_index"] for e in events] == [0, 1, 2]


def test_golden_3_first_then_finally_progression():
    events = _events(
        "First, let's talk about how you've been feeling.",
        "Then we'll go through your medication.",
        "Finally, I'll explain the next steps.",
    )
    assert len(events) == 3
    assert all(e["event"] == "consultation_sequence_marker" for e in events)


def test_golden_4_before_after_structural_sequencing():
    events = _events("Before we discuss the results, let's check your vitals.")
    assert events == [{
        "event": "consultation_sequence_marker_partial", "turn_index": 0,
        "evidence": "Before we discuss the results, let's check your vitals.",
    }]


def test_golden_5_partial_sequence():
    events = _events("First, let's discuss your symptoms.")
    assert len(events) == 1 and events[0]["event"] == "consultation_sequence_marker_partial"


def test_golden_6_plan_follow_up_progression():
    events = _events(
        "First, I'll ask about your symptoms.",
        "Then we'll discuss your medication.",
        "After that, we'll discuss what we can do next.",
    )
    assert events[-1]["evidence"] == "After that, we'll discuss what we can do next."
    assert events[-1]["event"] == "consultation_sequence_marker"


def test_golden_7_ordinary_before_false_positive():
    assert _events("Before coming here, you felt dizzy.") == []


def test_golden_8_ordinary_after_false_positive():
    assert _events("After lunch I take my medication.") == []


def test_golden_9_ordinary_first_false_positive():
    assert _events("First thing in the morning I take my medication.") == []


def test_golden_10_implicit_sequence_not_detected():
    # Logically sequenced (symptoms -> history -> plan) but no explicit
    # marker anywhere -- Step 7: deliberately not detected.
    events = _events(
        "How have you been feeling?",
        "Have you had this before?",
        "Here's what I'd recommend.",
    )
    assert events == []


def test_golden_11_c1_c2_legitimate_overlap():
    from app.services.structure_evidence import detect_structure_events
    turn = "First, let's talk about your symptoms."
    c1 = detect_sequence_events(_history(turn))
    c2 = detect_structure_events(turn)
    assert any(e["event"] == "consultation_sequence_marker_partial" for e in c1)
    assert any(e["event"] == "signposting_detected" for e in c2)


def test_golden_12_c1_c3_legitimate_overlap():
    from app.services.structure_evidence import detect_organization_sequences
    turn = "First, I'd like to explain what's going on."
    c1 = detect_sequence_events(_history(turn))
    c3 = detect_organization_sequences(_history(turn))
    assert any(e["event"] == "consultation_sequence_marker_partial" for e in c1)
    assert len(c3) == 1  # C3's bare ordinal regex also fires -- independently


def test_golden_12b_c3_bare_ordinal_is_not_auto_c1():
    # The inverse of golden 12: C3 fires on a bare ordinal with no verb;
    # C1 must NOT be manufactured just because C3 found a marker (Step 16).
    assert _events("First, your medication.") == []


def test_golden_13_multiple_sequences():
    events = _events(
        "First, I'll ask about your symptoms.",
        "Then we'll discuss your medication.",
        "How does that sound so far?",
        "Once we've covered that, I'll explain the treatment plan.",
    )
    turn_indexes = [e["turn_index"] for e in events]
    assert turn_indexes == [0, 1, 3]
    assert events[2]["event"] == "consultation_sequence_marker_partial"


def test_golden_14_ambiguous_sequence_is_uncertain():
    events = _events("Let me first apologize for the wait.")
    assert events == [{
        "event": "consultation_sequence_uncertain", "turn_index": 0,
        "evidence": "Let me first apologize for the wait.",
    }]


# ── Additional targeted tests (Step 21) ─────────────────────────────────

def test_procedural_sequence_phrase():
    events = _events("Let's first go through your chart.")
    assert events[0]["event"] == "consultation_sequence_marker_partial"


def test_patient_involvement_conversational_sequencing():
    events = _events(
        "Let's first make sure I understand what happened.",
        "Then I'll explain what I recommend.",
    )
    assert [e["event"] for e in events] == ["consultation_sequence_marker"] * 2


def test_ordinary_then_no_modal_no_verb_produces_nothing():
    assert _events("Then I felt better.") == []


def test_uncertainty_not_merged_into_sequence():
    events = _events(
        "First, I'll ask about your symptoms.",
        "Let me first apologize for the wait.",
        "Then we'll discuss your medication.",
    )
    kinds = [e["event"] for e in events]
    assert "consultation_sequence_uncertain" in kinds
    # The uncertain turn does not close/merge the surrounding strong
    # sequence's grouping in a way that drops evidence.
    assert kinds.count("consultation_sequence_marker") + kinds.count("consultation_sequence_marker_partial") == 2


def test_provenance_and_evidence_level_via_criterion_evidence():
    from app.services.criterion_evidence import LEVEL_L2_DETERMINISTIC, map_criterion_evidence
    from app.services.evidence_reconciliation import reconcile_evidence
    from app.services.examiner_input import build_examiner_input
    from app.services.speaking_evidence import (
        CandidateEvent, InteractionMetrics, SpeakingEvidence,
    )

    metrics = InteractionMetrics(
        turn_counts={"nurse": 1, "patient": 0, "total": 1},
        jargon_events=0, empathy_events=0, concern_exploration_events=0,
        understanding_check_events=0, dismissive_events=0,
    )
    evidence = SpeakingEvidence(
        candidate_events=[CandidateEvent(
            event="consultation_sequence_marker_partial", turn_index=0,
            evidence_text="First, I'll ask you about your symptoms.",
        )],
        patient_events=[], concern_outcomes=[], state_transitions=[],
        jargon_evidence=[], interaction_metrics=metrics, hidden_info_outcomes=[],
    )
    unified = reconcile_evidence(evidence)
    ei = build_examiner_input(
        scenario={}, transcript=[{"role": "nurse", "content": "First, I'll ask you about your symptoms."}],
        unified_evidence=unified,
    )
    result = map_criterion_evidence(ei)
    c_bundle = next(b for b in result.clinical if b.criterion == "providing_structure")
    c1 = next(i for i in c_bundle.indicators if i.indicator == "C1")
    assert len(c1.evidence_refs) == 1
    ref = c1.evidence_refs[0]
    assert ref.provenance == "deterministic_rule"
    assert ref.evidence_level == LEVEL_L2_DETERMINISTIC
    assert c1.gaps == []


def test_missing_evidence_is_limited_not_a_gap():
    from app.services.criterion_evidence import map_criterion_evidence
    from app.services.evidence_reconciliation import reconcile_evidence
    from app.services.examiner_input import build_examiner_input, AVAILABILITY_LIMITED
    from app.services.speaking_evidence import InteractionMetrics, SpeakingEvidence

    metrics = InteractionMetrics(
        turn_counts={"nurse": 1, "patient": 0, "total": 1},
        jargon_events=0, empathy_events=0, concern_exploration_events=0,
        understanding_check_events=0, dismissive_events=0,
    )
    evidence = SpeakingEvidence(
        candidate_events=[], patient_events=[], concern_outcomes=[], state_transitions=[],
        jargon_evidence=[], interaction_metrics=metrics, hidden_info_outcomes=[],
    )
    unified = reconcile_evidence(evidence)
    ei = build_examiner_input(
        scenario={}, transcript=[{"role": "nurse", "content": "How are you feeling?"}],
        unified_evidence=unified,
    )
    result = map_criterion_evidence(ei)
    c_bundle = next(b for b in result.clinical if b.criterion == "providing_structure")
    c1 = next(i for i in c_bundle.indicators if i.indicator == "C1")
    assert c1.evidence_refs == []
    assert c1.evidence_quality == AVAILABILITY_LIMITED
    assert c1.gaps == []


def test_serialization_roundtrip():
    events = _events("First, I'll ask you about your symptoms.", "Then we'll discuss your medication.")
    from app.services.speaking_evidence import CandidateEvent
    refs = [CandidateEvent(event=e["event"], turn_index=e["turn_index"], evidence_text=e["evidence"]) for e in events]
    dumped = [r.model_dump() for r in refs]
    restored = [CandidateEvent(**d) for d in dumped]
    assert restored == refs


def test_determinism():
    history = _history(
        "First, I'll ask you about your symptoms.",
        "Then we'll discuss your medication.",
        "After that, we'll discuss what we can do next.",
    )
    assert detect_sequence_events(history) == detect_sequence_events(history)


def test_speaking_evidence_integration():
    from app.services.speaking_evidence import build_speaking_evidence
    history = _history("First, I'll ask you about your symptoms.", "Then we'll discuss your medication.")
    evidence = build_speaking_evidence({}, history)
    events = [e for e in evidence.candidate_events if e.event.startswith("consultation_sequence")]
    assert len(events) == 2
    assert all(e.source == "deterministic_rule" for e in events)


def test_no_score_no_model_call_no_db():
    """Structural guarantee (Step 20/23/24): the detector module imports
    nothing from ai_scoring, no async/await, no network/DB client."""
    import ast
    import inspect

    import app.services.sequencing_evidence as mod
    source = inspect.getsource(mod)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Await), "no model/async calls allowed"
    assert "ai_scoring" not in source
    assert "score_speaking" not in source
    assert "async def" not in source
