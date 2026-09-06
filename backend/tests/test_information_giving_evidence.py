"""Tests for the Information Giving (E1/E2/E3/E5) detector (Step 21E). Same
style as test_information_gathering_evidence.py -- purely regex/keyword-based,
every assertion checked against the detector's actual output. No score
assignments anywhere (Step 20/21 of the task spec): only presence/absence of
evidence.
"""
from app.services.information_giving_evidence import (
    EVENT_CONTRIBUTION_INVITATION,
    EVENT_CONTRIBUTION_INVITATION_UNCERTAIN,
    EVENT_FURTHER_INFORMATION_CHECK,
    EVENT_FURTHER_INFORMATION_UNCERTAIN,
    EVENT_PRIOR_KNOWLEDGE_CHECK,
    EVENT_PRIOR_KNOWLEDGE_UNCERTAIN,
    EVENT_REACTION_RESPONSE,
    EVENT_REACTION_RESPONSE_UNCERTAIN,
    ContributionInvitationEvent,
    FurtherInformationEvent,
    PriorKnowledgeEvent,
    ReactionResponseEvent,
    detect_contribution_invitation_events,
    detect_further_information_events,
    detect_information_giving_evidence,
    detect_prior_knowledge_events,
    detect_reaction_response_events,
)


def _turns(*pairs):
    return [{"role": role, "content": content} for role, content in pairs]


# ── E1 golden cases (1-5) ────────────────────────────────────────────────

def test_e1_golden_1_prior_knowledge_about_treatment():
    events = detect_prior_knowledge_events(_turns(("nurse", "What do you already know about insulin?")))
    assert len(events) == 1
    assert events[0].event_type == EVENT_PRIOR_KNOWLEDGE_CHECK
    assert events[0].target == "insulin"


def test_e1_golden_2_prior_knowledge_about_condition():
    events = detect_prior_knowledge_events(_turns(("nurse", "How much do you know about your condition?")))
    assert len(events) == 1 and events[0].event_type == EVENT_PRIOR_KNOWLEDGE_CHECK
    assert events[0].target == "your condition"


def test_e1_golden_3_relevant_prior_information():
    events = detect_prior_knowledge_events(_turns(("nurse", "What have you been told about the medication?")))
    assert len(events) == 1 and events[0].event_type == EVENT_PRIOR_KNOWLEDGE_CHECK


def test_e1_golden_4_unrelated_knowledge_question():
    assert detect_prior_knowledge_events(_turns(("nurse", "Do you know where the clinic is?"))) == []
    assert detect_prior_knowledge_events(_turns(("nurse", "What medication are you taking?"))) == []


def test_e1_golden_5_ambiguous_knowledge_question():
    events = detect_prior_knowledge_events(_turns(("nurse", "Do you know much about diabetes?")))
    assert len(events) == 1 and events[0].event_type == EVENT_PRIOR_KNOWLEDGE_UNCERTAIN


# ── E2 golden cases (6-10) ───────────────────────────────────────────────

def test_e2_golden_6_information_reaction_response_sequence():
    events = detect_reaction_response_events(_turns(
        ("nurse", "Insulin injections can sometimes cause bruising."),
        ("patient", "I'm worried they'll hurt."),
        ("nurse", "I can see why that worries you. Let's talk about ways to make it more comfortable."),
    ))
    assert len(events) == 1
    assert events[0].event_type == EVENT_REACTION_RESPONSE
    assert events[0].related_patient_turns == [1]
    assert events[0].related_information_turns == [0]


def test_e2_golden_7_explicit_response_to_worry():
    events = detect_reaction_response_events(_turns(
        ("nurse", "You'll need to take this medication every morning."),
        ("patient", "That sounds like a lot to remember."),
        ("nurse", "I understand this may be difficult to hear."),
    ))
    assert len(events) == 1 and events[0].event_type == EVENT_REACTION_RESPONSE


def test_e2_golden_8_repeat_rephrase_after_reaction():
    events = detect_reaction_response_events(_turns(
        ("nurse", "The surgery will take about two hours."),
        ("patient", "I don't understand."),
        ("nurse", "Would you like me to explain that again?"),
    ))
    assert len(events) == 1 and events[0].event_type == EVENT_REACTION_RESPONSE


def test_e2_golden_9_empathy_outside_information_context():
    """No preceding patient turn at all -- isolated empathy, not E2 evidence."""
    events = detect_reaction_response_events(_turns(
        ("nurse", "I can see that's worrying you. Let's talk about that."),
    ))
    assert events == []


def test_e2_golden_10_ambiguous_adaptation():
    events = detect_reaction_response_events(_turns(
        ("patient", "I'm scared."),
        ("nurse", "I can see that's worrying you."),
    ))
    assert len(events) == 1 and events[0].event_type == EVENT_REACTION_RESPONSE_UNCERTAIN


# ── E3 golden cases (11-15) ──────────────────────────────────────────────

def test_e3_golden_11_explicit_invitation_for_reaction():
    events = detect_contribution_invitation_events(_turns(
        ("nurse", "Insulin can help control your blood sugar. How does that sound to you?"),
    ))
    assert len(events) == 1 and events[0].event_type == EVENT_CONTRIBUTION_INVITATION
    assert events[0].related_information_turns == [0]


def test_e3_golden_12_opinion_invitation_after_information():
    events = detect_contribution_invitation_events(_turns(
        ("nurse", "We'd like to start you on a new medication."),
        ("nurse", "What are your thoughts?"),
    ))
    assert len(events) == 1 and events[0].event_type == EVENT_CONTRIBUTION_INVITATION
    assert events[0].related_information_turns == [0]


def test_e3_golden_13_unrelated_open_question_not_e3():
    assert detect_contribution_invitation_events(_turns(("nurse", "What happened yesterday?"))) == []


def test_e3_golden_14_e3_b1_overlap():
    """Step 11: 'How do you feel about starting insulin?' names a topic (like
    B1's own concern-exploration phrasing), not the anaphoric 'that' E3's
    lexicon requires -- narrowest defensible interpretation leaves this to
    B1, not auto-duplicated into E3. The anaphoric form does fire E3."""
    topic_specific = detect_contribution_invitation_events(
        _turns(("nurse", "How do you feel about starting insulin?")),
    )
    anaphoric = detect_contribution_invitation_events(
        _turns(("nurse", "We'll start you on insulin."), ("nurse", "How do you feel about that?")),
    )
    assert topic_specific == []
    assert len(anaphoric) == 1 and anaphoric[0].event_type == EVENT_CONTRIBUTION_INVITATION


def test_e3_golden_15_ambiguous_context():
    events = detect_contribution_invitation_events(_turns(("nurse", "How does that sound?")))
    assert len(events) == 1 and events[0].event_type == EVENT_CONTRIBUTION_INVITATION_UNCERTAIN


# ── E5 golden cases (16-20) ──────────────────────────────────────────────

def test_e5_golden_16_other_questions_invitation():
    events = detect_further_information_events(_turns(("nurse", "Do you have any other questions?")))
    assert len(events) == 1 and events[0].event_type == EVENT_FURTHER_INFORMATION_CHECK


def test_e5_golden_17_anything_else_to_know():
    events = detect_further_information_events(_turns(("nurse", "Is there anything else you'd like to know?")))
    assert len(events) == 1 and events[0].event_type == EVENT_FURTHER_INFORMATION_CHECK


def test_e5_golden_18_further_explanation_request():
    events = detect_further_information_events(_turns(("nurse", "What else would you like me to explain?")))
    assert len(events) == 1 and events[0].event_type == EVENT_FURTHER_INFORMATION_CHECK


def test_e5_golden_19_e4_false_positive():
    assert detect_further_information_events(_turns(("nurse", "Do you understand?"))) == []
    assert detect_further_information_events(_turns(("nurse", "Does that make sense?"))) == []


def test_e5_golden_20_multiple_invitations():
    events = detect_further_information_events(_turns(
        ("nurse", "Do you have any other questions?"),
        ("patient", "No, thank you."),
        ("nurse", "Is there anything else you want to ask?"),
    ))
    strong = [e for e in events if e.event_type == EVENT_FURTHER_INFORMATION_CHECK]
    assert [e.turn_index for e in strong] == [0, 2]


# ── Combined overlap golden cases (21-25) ─────────────────────────────────

def test_combined_21_e1_d2_overlap():
    from app.services.question_behaviour import detect_question_events
    turn = "What do you already know about insulin?"
    e1 = detect_prior_knowledge_events(_turns(("nurse", turn)))
    d2 = detect_question_events(turn)
    assert len(e1) == 1 and e1[0].event_type == EVENT_PRIOR_KNOWLEDGE_CHECK
    assert any(e["event"] in ("open_question", "closed_question") for e in d2)


def test_combined_22_e3_b1_overlap_no_dedup():
    e3 = detect_contribution_invitation_events(_turns(("nurse", "What are your thoughts?")))
    assert len(e3) == 1  # fires independently of patient_state's B1 detector -- no cross-module dedup


def test_combined_23_e3_e2_same_sentence_double_evidence():
    history = _turns(
        ("nurse", "Insulin injections can sometimes cause bruising."),
        ("patient", "I'm worried they'll hurt."),
        ("nurse", "How does that sound to you?"),
    )
    e2 = detect_reaction_response_events(history)
    e3 = detect_contribution_invitation_events(history)
    assert len(e2) == 1 and e2[0].event_type == EVENT_REACTION_RESPONSE
    assert len(e3) == 1 and e3[0].event_type == EVENT_CONTRIBUTION_INVITATION
    assert e2[0].turn_index == e3[0].turn_index == 2  # same turn, both detectors, no dedup


def test_combined_24_e4_vs_e5_distinction():
    from app.services.patient_state import detect_nurse_events
    e4_turn = "Can you tell me how you'll take it when you get home?"
    e5_turn = "Is there anything else you'd like to know?"
    assert detect_further_information_events(_turns(("nurse", e4_turn))) == []
    assert detect_further_information_events(_turns(("nurse", e5_turn)))[0].event_type == EVENT_FURTHER_INFORMATION_CHECK
    # E4's own understanding-check phrase list never overlaps E5's lexicon.
    assert detect_nurse_events("Does that make sense?")[0]["event"] == "understanding_checked"
    assert detect_further_information_events(_turns(("nurse", "Does that make sense?"))) == []


def test_combined_25_complete_information_giving_sequence():
    history = _turns(
        ("nurse", "What do you already know about insulin?"),
        ("patient", "Not much, really."),
        ("nurse", "Insulin helps control your blood sugar levels."),
        ("patient", "Will it hurt?"),
        ("nurse", "I can see that's worrying you. Most people find it's not too bad. How does that sound to you?"),
        ("patient", "Okay, I think I can manage that."),
        ("nurse", "Is there anything else you'd like to know?"),
    )
    result = detect_information_giving_evidence(history)
    assert len(result.prior_knowledge_events) == 1
    assert len(result.reaction_response_events) == 1
    assert len(result.contribution_invitation_events) == 1
    assert len(result.further_information_events) == 1


# ── Uncertainty / missing vs negative ─────────────────────────────────────

def test_uncertainty_never_forced():
    e1 = detect_prior_knowledge_events(_turns(("nurse", "Do you know much about diabetes?")))
    e2 = detect_reaction_response_events(_turns(
        ("patient", "I'm scared."), ("nurse", "I can see that's worrying you."),
    ))
    e3 = detect_contribution_invitation_events(_turns(("nurse", "How does that sound?")))
    e5 = detect_further_information_events(_turns(("nurse", "Do you have any questions?")))
    assert e1[0].event_type == EVENT_PRIOR_KNOWLEDGE_UNCERTAIN
    assert e2[0].event_type == EVENT_REACTION_RESPONSE_UNCERTAIN
    assert e3[0].event_type == EVENT_CONTRIBUTION_INVITATION_UNCERTAIN
    assert e5[0].event_type == EVENT_FURTHER_INFORMATION_UNCERTAIN


def test_missing_evidence_is_not_negative():
    """No E1/E2/E3/E5 phrasing anywhere -> empty lists, never a failure marker."""
    history = _turns(("nurse", "How are you feeling today?"))
    assert detect_prior_knowledge_events(history) == []
    assert detect_reaction_response_events(history) == []
    assert detect_contribution_invitation_events(history) == []
    assert detect_further_information_events(history) == []


# ── Provenance / evidence level ───────────────────────────────────────────

def test_provenance_is_deterministic():
    e1 = detect_prior_knowledge_events(_turns(("nurse", "What do you already know about insulin?")))
    assert e1[0].provenance == "deterministic_rule"
    assert e1[0].evidence_level == "L2_deterministic"
    e5 = detect_further_information_events(_turns(("nurse", "Do you have any other questions?")))
    assert all(e.provenance == "deterministic_rule" for e in e5)


# ── Serialization ──────────────────────────────────────────────────────────

def test_serialization_roundtrip_prior_knowledge():
    events = detect_prior_knowledge_events(_turns(("nurse", "What do you already know about insulin?")))
    dumped = [e.model_dump() for e in events]
    restored = [PriorKnowledgeEvent(**d) for d in dumped]
    assert restored == events


def test_serialization_roundtrip_reaction_response():
    events = detect_reaction_response_events(_turns(
        ("nurse", "Insulin injections can sometimes cause bruising."),
        ("patient", "I'm worried they'll hurt."),
        ("nurse", "I can see why that worries you."),
    ))
    dumped = [e.model_dump() for e in events]
    restored = [ReactionResponseEvent(**d) for d in dumped]
    assert restored == events


def test_serialization_roundtrip_contribution_invitation():
    events = detect_contribution_invitation_events(_turns(("nurse", "What are your thoughts?")))
    dumped = [e.model_dump() for e in events]
    restored = [ContributionInvitationEvent(**d) for d in dumped]
    assert restored == events


def test_serialization_roundtrip_further_information():
    events = detect_further_information_events(_turns(("nurse", "Do you have any other questions?")))
    dumped = [e.model_dump() for e in events]
    restored = [FurtherInformationEvent(**d) for d in dumped]
    assert restored == events


# ── Determinism ────────────────────────────────────────────────────────────

def test_determinism():
    history = _turns(
        ("nurse", "What do you already know about insulin?"),
        ("patient", "Not much."),
        ("nurse", "I can see that's worrying you. How does that sound to you?"),
    )
    assert detect_prior_knowledge_events(history) == detect_prior_knowledge_events(history)
    assert detect_reaction_response_events(history) == detect_reaction_response_events(history)
    assert detect_contribution_invitation_events(history) == detect_contribution_invitation_events(history)
    assert detect_further_information_events(history) == detect_further_information_events(history)


# ── SpeakingEvidence integration ───────────────────────────────────────────

def test_speaking_evidence_integration():
    from app.services.speaking_evidence import build_speaking_evidence
    history = _turns(
        ("nurse", "Insulin injections can sometimes cause bruising."),
        ("patient", "I'm worried they'll hurt."),
        ("nurse", "I can see why that worries you."),
    )
    evidence = build_speaking_evidence({}, history)
    events = [e for e in evidence.candidate_events if e.event.startswith("reaction_response")]
    assert len(events) == 1
    assert events[0].related_patient_turns == [1]
    assert events[0].related_information_turns == [0]
    assert events[0].source == "deterministic_rule"


# ── CriterionEvidence integration ─────────────────────────────────────────

def test_criterion_evidence_integration_e1():
    from app.services.criterion_evidence import LEVEL_L2_DETERMINISTIC, map_criterion_evidence
    from app.services.evidence_reconciliation import reconcile_evidence
    from app.services.examiner_input import build_examiner_input
    from app.services.speaking_evidence import CandidateEvent, InteractionMetrics, SpeakingEvidence

    metrics = InteractionMetrics(
        turn_counts={"nurse": 1, "patient": 0, "total": 1},
        jargon_events=0, empathy_events=0, concern_exploration_events=0,
        understanding_check_events=0, dismissive_events=0,
    )
    evidence = SpeakingEvidence(
        candidate_events=[CandidateEvent(
            event="prior_knowledge_check", turn_index=0,
            evidence_text="What do you already know about insulin?",
        )],
        patient_events=[], concern_outcomes=[], state_transitions=[],
        jargon_evidence=[], interaction_metrics=metrics, hidden_info_outcomes=[],
    )
    unified = reconcile_evidence(evidence)
    ei = build_examiner_input(
        scenario={}, transcript=[{"role": "nurse", "content": "What do you already know about insulin?"}],
        unified_evidence=unified,
    )
    result = map_criterion_evidence(ei)
    e_bundle = next(b for b in result.clinical if b.criterion == "information_giving")
    e1 = next(i for i in e_bundle.indicators if i.indicator == "E1")
    assert len(e1.evidence_refs) == 1
    ref = e1.evidence_refs[0]
    assert ref.provenance == "deterministic_rule"
    assert ref.evidence_level == LEVEL_L2_DETERMINISTIC
    assert e1.gaps == []


def test_criterion_evidence_integration_e2_related_turns():
    from app.services.criterion_evidence import map_criterion_evidence
    from app.services.evidence_reconciliation import reconcile_evidence
    from app.services.examiner_input import build_examiner_input
    from app.services.speaking_evidence import CandidateEvent, InteractionMetrics, SpeakingEvidence

    metrics = InteractionMetrics(
        turn_counts={"nurse": 2, "patient": 1, "total": 3},
        jargon_events=0, empathy_events=0, concern_exploration_events=0,
        understanding_check_events=0, dismissive_events=0,
    )
    evidence = SpeakingEvidence(
        candidate_events=[CandidateEvent(
            event="reaction_response", turn_index=2,
            evidence_text="I can see why that worries you.",
            related_patient_turns=[1], related_information_turns=[0],
        )],
        patient_events=[], concern_outcomes=[], state_transitions=[],
        jargon_evidence=[], interaction_metrics=metrics, hidden_info_outcomes=[],
    )
    unified = reconcile_evidence(evidence)
    ei = build_examiner_input(scenario={}, transcript=[], unified_evidence=unified)
    result = map_criterion_evidence(ei)
    e_bundle = next(b for b in result.clinical if b.criterion == "information_giving")
    e2 = next(i for i in e_bundle.indicators if i.indicator == "E2")
    assert len(e2.evidence_refs) == 1
    ref = e2.evidence_refs[0]
    assert ref.related_patient_turn == 1
    assert ref.metadata.get("related_information_turns") == [0]


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
    e_bundle = next(b for b in result.clinical if b.criterion == "information_giving")
    for indicator in ("E1", "E2", "E3", "E5"):
        ind = next(i for i in e_bundle.indicators if i.indicator == indicator)
        assert ind.evidence_refs == []
        assert ind.evidence_quality == AVAILABILITY_LIMITED
        assert ind.gaps == []


def test_no_score_no_model_call_no_db():
    """Structural guarantee (Step 25/26/27 of the task spec): the detector
    module imports nothing from ai_scoring, no async/await, no network/DB."""
    import ast
    import inspect

    import app.services.information_giving_evidence as mod
    source = inspect.getsource(mod)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Await), "no model/async calls allowed"
    assert "ai_scoring" not in source
    assert "score_speaking" not in source
    assert "async def" not in source
    assert "gemini" not in source.lower()
    assert "openrouter" not in source.lower()


def test_dedicated_model_bundles_all_four_detectors():
    result = detect_information_giving_evidence(_turns(
        ("nurse", "What do you already know about insulin?"),
        ("patient", "Not much."),
        ("nurse", "I can see that's worrying you. How does that sound to you?"),
        ("nurse", "Do you have any other questions?"),
    ))
    assert len(result.prior_knowledge_events) == 1
    assert len(result.reaction_response_events) == 1
    assert len(result.contribution_invitation_events) == 1
    assert len(result.further_information_events) == 1
    assert result.limitations
