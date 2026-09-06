"""Tests for the Information Gathering clarification & summarisation (D4/D5)
detector (Step 21D). Same style as test_sequencing_evidence.py/
test_structure_evidence.py -- purely regex/keyword-based, every assertion
checked against the detector's actual output. No score assignments anywhere
(Step 20/21 of the task spec): only presence/absence of evidence.
"""
from app.services.information_gathering_evidence import (
    EVENT_CLARIFICATION_REQUEST,
    EVENT_CLARIFICATION_UNCERTAIN,
    EVENT_SUMMARY,
    EVENT_SUMMARY_CHECK,
    EVENT_SUMMARY_UNCERTAIN,
    ClarificationEvent,
    SummaryEvent,
    detect_clarification_events,
    detect_information_gathering_evidence,
    detect_summary_events,
)


def _turns(*pairs):
    return [{"role": role, "content": content} for role, content in pairs]


# ── D4 golden cases ───────────────────────────────────────────────────────

def test_d4_golden_1_explicit_clarification():
    events = detect_clarification_events(_turns(("nurse", "What do you mean by that?")))
    assert len(events) == 1
    assert events[0].event_type == EVENT_CLARIFICATION_REQUEST
    assert events[0].evidence_text == "What do you mean by that?"


def test_d4_golden_2_clarification_linked_to_prior_vague_statement():
    events = detect_clarification_events(_turns(
        ("patient", "It's been getting worse."),
        ("nurse", "What do you mean by worse?"),
    ))
    assert len(events) == 1
    assert events[0].turn_index == 1
    assert events[0].related_patient_turns == [0]


def test_d4_golden_3_clarification_followed_by_patient_response():
    events = detect_clarification_events(_turns(
        ("patient", "It's been strange."),
        ("nurse", "What do you mean by strange?"),
        ("patient", "It feels like the room is spinning."),
    ))
    assert len(events) == 1
    assert events[0].related_patient_turns == [0]
    assert events[0].response_patient_turn == 2


def test_d4_golden_4_elaboration_request_not_clarification():
    assert detect_clarification_events(_turns(("nurse", "Can you tell me more about your pain?"))) == []


def test_d4_golden_5_ordinary_follow_up_question_not_clarification():
    assert detect_clarification_events(_turns(("nurse", "When did the pain start?"))) == []


def test_d4_golden_6_multiple_clarification_turns():
    events = detect_clarification_events(_turns(
        ("nurse", "What do you mean by that?"),
        ("patient", "It's hard to explain."),
        ("nurse", "Could you clarify what you mean by hard?"),
    ))
    assert [e.turn_index for e in events] == [0, 2]


def test_d4_golden_7_ambiguous_clarification_is_uncertain():
    events = detect_clarification_events(_turns(("nurse", "Could you tell me more about that?")))
    assert len(events) == 1 and events[0].event_type == EVENT_CLARIFICATION_UNCERTAIN


# ── D5 golden cases ──────────────────────────────────────────────────────

def test_d5_golden_1_explicit_summary():
    events = detect_summary_events(_turns(("nurse", "Just to summarise, you've had a headache for two days.")))
    summaries = [e for e in events if e.event_type == EVENT_SUMMARY]
    assert len(summaries) == 1


def test_d5_golden_2_multi_turn_summary():
    events = detect_summary_events(_turns(
        ("patient", "I've had pain for three days."),
        ("nurse", "Okay, thank you."),
        ("patient", "It's worse when I walk."),
        ("nurse", "I see."),
        ("patient", "I'm worried about work."),
        ("nurse", "So you've had pain for three days, it's worse when you walk, and you're concerned about work."),
    ))
    summaries = [e for e in events if e.event_type == EVENT_SUMMARY]
    assert len(summaries) == 1
    assert summaries[0].related_patient_turns == [0, 2, 4]


def test_d5_golden_3_summary_with_correction_invitation():
    events = detect_summary_events(_turns(
        ("patient", "I've had headaches for three days and I'm worried about work."),
        ("nurse", (
            "So you've had headaches for three days and you're worried about work. "
            "Have I understood you correctly?"
        )),
    ))
    summaries = [e for e in events if e.event_type == EVENT_SUMMARY]
    checks = [e for e in events if e.event_type == EVENT_SUMMARY_CHECK]
    assert len(summaries) == 1
    assert len(checks) == 1
    assert checks[0].related_patient_turns == summaries[0].related_patient_turns


def test_d5_golden_4_simple_repetition_false_positive():
    events = detect_summary_events(_turns(
        ("patient", "I started feeling tired yesterday."),
        ("nurse", "You started feeling tired yesterday."),
    ))
    assert events == []


def test_d5_golden_5_ordinary_so_false_positive():
    assert detect_summary_events(_turns(("nurse", "So I'll give you some advice."))) == []
    assert detect_summary_events(_turns(("nurse", "So I'll explain the treatment now."))) == []


def test_d5_golden_6_multiple_summaries():
    events = detect_summary_events(_turns(
        ("patient", "I've had a cough for a week."),
        ("nurse", "Just to summarise, you've had a cough for a week."),
        ("patient", "It's worse at night."),
        ("nurse", "To recap, it's worse at night too."),
    ))
    summaries = [e for e in events if e.event_type == EVENT_SUMMARY]
    assert [e.turn_index for e in summaries] == [1, 3]


def test_d5_golden_7_summary_vs_c3_distinction():
    from app.services.structure_evidence import detect_structure_events
    turn = "So, you've had the symptoms for three days."
    d5 = detect_summary_events(_turns(("patient", "I've had symptoms for three days."), ("nurse", turn)))
    c3 = detect_structure_events("There are two things I want to explain.")
    assert any(e.event_type == EVENT_SUMMARY_UNCERTAIN or e.event_type == EVENT_SUMMARY for e in d5)
    assert c3 == []  # different turn/marker family entirely -- no shared vocabulary


def test_d5_golden_8_summary_vs_e4_distinction():
    events = detect_summary_events(_turns(("nurse", "Can you tell me how you'll take it when you get home?")))
    assert events == []  # E4 comprehension-check phrasing, not a D5 summary marker


# ── Combined overlap golden cases ────────────────────────────────────────

def test_combined_d4_d2_overlap():
    from app.services.question_behaviour import detect_question_events
    turn = "What do you mean by 'dizzy'?"
    d4 = detect_clarification_events(_turns(("nurse", turn)))
    d2 = detect_question_events(turn)
    assert len(d4) == 1 and d4[0].event_type == EVENT_CLARIFICATION_REQUEST
    assert any(e["event"] in ("open_question", "closed_question") for e in d2)


def test_combined_d5_d2_overlap():
    from app.services.question_behaviour import detect_question_events
    turn = "So, you've been having headaches, haven't you?"
    d5 = detect_summary_events(_turns(("patient", "I've been having headaches."), ("nurse", turn)))
    d2 = detect_question_events(turn)
    assert any(e.event_type in (EVENT_SUMMARY, EVENT_SUMMARY_UNCERTAIN, EVENT_SUMMARY_CHECK) for e in d5)
    assert any(e["event"] == "closed_question" for e in d2)


def test_combined_d5_c3_overlap():
    from app.services.structure_evidence import detect_organization_marker_events
    turn = "To recap, here's what we'll do next."
    d5 = detect_summary_events(_turns(("nurse", turn)))
    c3 = detect_organization_marker_events(_turns(("nurse", turn)))
    assert any(e.event_type == EVENT_SUMMARY for e in d5)
    assert any(e["event"].startswith("organization_marker") for e in c3)


# ── False-positive tests (Step 24) ────────────────────────────────────────

def test_false_positive_so_ill_explain_not_d5():
    assert detect_summary_events(_turns(("nurse", "So I'll explain the treatment now."))) == []


def test_false_positive_when_did_pain_start_not_d4():
    assert detect_clarification_events(_turns(("nurse", "When did the pain start?"))) == []


def test_false_positive_tell_me_more_not_auto_clarification():
    assert detect_clarification_events(_turns(("nurse", "Tell me more about your symptoms."))) == []


def test_false_positive_you_said_yesterday_not_auto_d5():
    assert detect_summary_events(_turns(
        ("patient", "I felt tired."),
        ("nurse", "You said yesterday that you felt tired."),
    )) == []


# ── Uncertainty / missing vs negative ─────────────────────────────────────

def test_uncertainty_explicit_for_clarification():
    events = detect_clarification_events(_turns(("nurse", "Could you tell me more about this?")))
    assert events[0].event_type == EVENT_CLARIFICATION_UNCERTAIN


def test_uncertainty_explicit_for_summary():
    events = detect_summary_events(_turns(("nurse", "So, you've been feeling tired.")))
    summaries = [e for e in events if e.event_type in (EVENT_SUMMARY, EVENT_SUMMARY_UNCERTAIN)]
    assert len(summaries) == 1 and summaries[0].event_type == EVENT_SUMMARY_UNCERTAIN


def test_missing_evidence_is_not_negative():
    """No D4/D5 phrasing anywhere -> empty lists, never a failure marker."""
    assert detect_clarification_events(_turns(("nurse", "How are you feeling today?"))) == []
    assert detect_summary_events(_turns(("nurse", "How are you feeling today?"))) == []


# ── Provenance / evidence level ───────────────────────────────────────────

def test_provenance_is_deterministic():
    events = detect_clarification_events(_turns(("nurse", "What do you mean by that?")))
    assert events[0].provenance == "deterministic_rule"
    assert events[0].evidence_level == "L2_deterministic"
    summary = detect_summary_events(_turns(("nurse", "Just to summarise, you've had a headache.")))
    assert all(e.provenance == "deterministic_rule" for e in summary)


# ── Serialization ──────────────────────────────────────────────────────────

def test_serialization_roundtrip_clarification():
    events = detect_clarification_events(_turns(
        ("patient", "It's been getting worse."), ("nurse", "What do you mean by worse?"),
    ))
    dumped = [e.model_dump() for e in events]
    restored = [ClarificationEvent(**d) for d in dumped]
    assert restored == events


def test_serialization_roundtrip_summary():
    events = detect_summary_events(_turns(
        ("patient", "I've had pain for three days."),
        ("nurse", "So you've had pain for three days. Is that right?"),
    ))
    dumped = [e.model_dump() for e in events]
    restored = [SummaryEvent(**d) for d in dumped]
    assert restored == events


# ── Determinism ────────────────────────────────────────────────────────────

def test_determinism():
    history = _turns(
        ("patient", "I've had pain for three days."),
        ("nurse", "So you've had pain for three days. Is that right?"),
    )
    assert detect_clarification_events(history) == detect_clarification_events(history)
    assert detect_summary_events(history) == detect_summary_events(history)


# ── SpeakingEvidence / CriterionEvidence integration ──────────────────────

def test_speaking_evidence_integration():
    from app.services.speaking_evidence import build_speaking_evidence
    history = _turns(
        ("patient", "It's been getting worse."),
        ("nurse", "What do you mean by worse?"),
    )
    evidence = build_speaking_evidence({}, history)
    events = [e for e in evidence.candidate_events if e.event.startswith("clarification")]
    assert len(events) == 1
    assert events[0].related_patient_turns == [0]
    assert events[0].source == "deterministic_rule"


def test_criterion_evidence_integration_d4():
    from app.services.criterion_evidence import LEVEL_L2_DETERMINISTIC, map_criterion_evidence
    from app.services.evidence_reconciliation import reconcile_evidence
    from app.services.examiner_input import build_examiner_input
    from app.services.speaking_evidence import CandidateEvent, InteractionMetrics, SpeakingEvidence

    metrics = InteractionMetrics(
        turn_counts={"nurse": 1, "patient": 1, "total": 2},
        jargon_events=0, empathy_events=0, concern_exploration_events=0,
        understanding_check_events=0, dismissive_events=0,
    )
    evidence = SpeakingEvidence(
        candidate_events=[CandidateEvent(
            event="clarification_request", turn_index=1,
            evidence_text="What do you mean by worse?", related_patient_turns=[0],
        )],
        patient_events=[], concern_outcomes=[], state_transitions=[],
        jargon_evidence=[], interaction_metrics=metrics, hidden_info_outcomes=[],
    )
    unified = reconcile_evidence(evidence)
    ei = build_examiner_input(
        scenario={}, transcript=[
            {"role": "patient", "content": "It's been getting worse."},
            {"role": "nurse", "content": "What do you mean by worse?"},
        ],
        unified_evidence=unified,
    )
    result = map_criterion_evidence(ei)
    d_bundle = next(b for b in result.clinical if b.criterion == "information_gathering")
    d4 = next(i for i in d_bundle.indicators if i.indicator == "D4")
    assert len(d4.evidence_refs) == 1
    ref = d4.evidence_refs[0]
    assert ref.provenance == "deterministic_rule"
    assert ref.evidence_level == LEVEL_L2_DETERMINISTIC
    assert ref.related_patient_turn == 0
    assert d4.gaps == []


def test_criterion_evidence_integration_d5_multi_turn():
    from app.services.criterion_evidence import map_criterion_evidence
    from app.services.evidence_reconciliation import reconcile_evidence
    from app.services.examiner_input import build_examiner_input
    from app.services.speaking_evidence import CandidateEvent, InteractionMetrics, SpeakingEvidence

    metrics = InteractionMetrics(
        turn_counts={"nurse": 1, "patient": 3, "total": 4},
        jargon_events=0, empathy_events=0, concern_exploration_events=0,
        understanding_check_events=0, dismissive_events=0,
    )
    evidence = SpeakingEvidence(
        candidate_events=[CandidateEvent(
            event="summary_statement", turn_index=3,
            evidence_text="So you've had pain, it's worse when you walk, and you're worried about work.",
            related_patient_turns=[0, 1, 2],
        )],
        patient_events=[], concern_outcomes=[], state_transitions=[],
        jargon_evidence=[], interaction_metrics=metrics, hidden_info_outcomes=[],
    )
    unified = reconcile_evidence(evidence)
    ei = build_examiner_input(scenario={}, transcript=[], unified_evidence=unified)
    result = map_criterion_evidence(ei)
    d_bundle = next(b for b in result.clinical if b.criterion == "information_gathering")
    d5 = next(i for i in d_bundle.indicators if i.indicator == "D5")
    # One EvidenceRef PER related patient turn (Step 8/21D) -- not one ref total.
    assert len(d5.evidence_refs) == 3
    assert sorted(r.related_patient_turn for r in d5.evidence_refs) == [0, 1, 2]


def test_missing_evidence_is_limited_not_a_gap():
    from app.services.criterion_evidence import map_criterion_evidence
    from app.services.evidence_reconciliation import reconcile_evidence
    from app.services.examiner_input import AVAILABILITY_LIMITED, build_examiner_input
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
    ei = build_examiner_input(scenario={}, transcript=[{"role": "nurse", "content": "Hi."}], unified_evidence=unified)
    result = map_criterion_evidence(ei)
    d_bundle = next(b for b in result.clinical if b.criterion == "information_gathering")
    for indicator in ("D4", "D5"):
        ind = next(i for i in d_bundle.indicators if i.indicator == indicator)
        assert ind.evidence_refs == []
        assert ind.evidence_quality == AVAILABILITY_LIMITED
        assert ind.gaps == []


def test_no_score_no_model_call_no_db():
    """Structural guarantee (Step 19/20/22 of the task spec): the detector
    module imports nothing from ai_scoring, no async/await, no network/DB."""
    import ast
    import inspect

    import app.services.information_gathering_evidence as mod
    source = inspect.getsource(mod)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Await), "no model/async calls allowed"
    assert "ai_scoring" not in source
    assert "score_speaking" not in source
    assert "async def" not in source
    assert "gemini" not in source.lower()
    assert "openrouter" not in source.lower()


def test_dedicated_model_bundles_both_detectors():
    result = detect_information_gathering_evidence(_turns(
        ("patient", "It's been getting worse."),
        ("nurse", "What do you mean by worse? So you've been getting worse. Is that right?"),
    ))
    assert len(result.clarification_events) == 1
    assert len(result.summary_events) >= 1
    assert result.limitations
