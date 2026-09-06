"""Tests for the Criterion Evidence Mapper (Step 20).

Builds ExaminerInput via build_examiner_input (already covered by
test_examiner_input.py) and exercises map_criterion_evidence's pure
mapping/gap/quality logic on top of it.
"""
import pytest

from app.services.criterion_evidence import (
    LEVEL_L2_DETERMINISTIC,
    LEVEL_L3_SEMANTIC,
    LEVEL_L4_PATIENT_OUTCOME,
    map_criterion_evidence,
)
from app.services.evidence_reconciliation import UnifiedEvidence, reconcile_evidence
from app.services.examiner_input import (
    ALL_CRITERIA,
    AVAILABILITY_INSUFFICIENT,
    CRITERION_APPROPRIATENESS_OF_LANGUAGE,
    CRITERION_FLUENCY,
    CRITERION_INFORMATION_GIVING,
    CRITERION_INTELLIGIBILITY,
    CRITERION_PATIENT_PERSPECTIVE,
    CRITERION_PROVIDING_STRUCTURE,
    CRITERION_RELATIONSHIP_BUILDING,
    CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION,
    build_examiner_input,
)
from app.services.speaking_evidence import (
    CandidateEvent,
    ConcernOutcome,
    InteractionMetrics,
    JargonEvidence,
    SOURCE_DETERMINISTIC,
    SOURCE_SEMANTIC,
    SpeakingEvidence,
)

EMPTY_METRICS = InteractionMetrics(
    turn_counts={"nurse": 0, "patient": 0, "total": 0},
    jargon_events=0, empathy_events=0, concern_exploration_events=0,
    understanding_check_events=0, dismissive_events=0,
)


def _speaking_evidence(**overrides) -> SpeakingEvidence:
    base = dict(
        candidate_events=[], patient_events=[], concern_outcomes=[],
        state_transitions=[], jargon_evidence=[], interaction_metrics=EMPTY_METRICS,
        hidden_info_outcomes=[],
    )
    base.update(overrides)
    return SpeakingEvidence(**base)


def _unified(**overrides) -> UnifiedEvidence:
    return reconcile_evidence(_speaking_evidence(**overrides))


BASE_SCENARIO = {
    "id": 42, "title": "Post-op wound care", "setting": "Surgical ward",
    "interlocutor_card": {
        "patient_name": "Sam", "mood": "anxious",
        "questions_to_ask": ["Will I be able to walk again?"],
        "information_to_withhold": ["History of falls at home"],
        "emotional_triggers": ["mention of independence"],
    },
}

BASE_TRANSCRIPT = [
    {"role": "nurse", "content": "Hello Sam, how are you feeling today?"},
    {"role": "patient", "content": "A bit worried, to be honest."},
]

ELITE_AUDIO_EVIDENCE = {
    "method": "azure",
    "azure": {
        "available": True, "overall_score": 82.5, "fluency_score": 79.0,
        "completeness_score": 95.0, "words": [], "problem_words": [],
        "transcript": "Hello Sam how are you feeling today",
    },
    "pattern_analysis": [{"pattern": "V/W confusion", "word_said": "wery", "word_correct": "very", "tip": "practice"}],
    "has_azure": True,
}

SESSION_CONTEXT = {"pipeline": "realtime", "session_usage_id": 1, "duration_seconds": 100.0, "interrupted_count": 2}


def _ei(unified=None, scenario=BASE_SCENARIO, transcript=BASE_TRANSCRIPT, session=SESSION_CONTEXT, audio=None):
    return build_examiner_input(scenario, transcript, unified or _unified(), session, audio)


# ── Coverage (1-3) ──────────────────────────────────────────────────────

def test_1_all_9_criteria_represented():
    result = map_criterion_evidence(_ei())
    criteria = {b.criterion for b in result.clinical} | {b.criterion for b in result.linguistic}
    assert criteria == set(ALL_CRITERIA)
    assert len(result.clinical) == 5
    assert len(result.linguistic) == 4


def test_2_all_20_clinical_indicators_represented():
    result = map_criterion_evidence(_ei())
    all_indicators = [i.indicator for b in result.clinical for i in b.indicators]
    assert len(all_indicators) == 20
    assert set(all_indicators) == {
        "A1", "A2", "A3", "A4", "B1", "B2", "B3", "C1", "C2", "C3",
        "D1", "D2", "D3", "D4", "D5", "E1", "E2", "E3", "E4", "E5",
    }


def test_3_correct_family_per_criterion():
    result = map_criterion_evidence(_ei())
    for b in result.clinical:
        assert b.family == "clinical"
    for b in result.linguistic:
        assert b.family == "linguistic"


def test_3b_linguistic_bundles_carry_no_indicator_field():
    result = map_criterion_evidence(_ei())
    for b in result.linguistic:
        assert not hasattr(b, "indicators")


# ── Mapping (4-11) ────────────────────────────────────────────────────────

def test_4_a4_maps_empathy_to_relationship_building():
    unified = _unified(candidate_events=[
        CandidateEvent(event="empathy_acknowledgement", turn_index=0, evidence_text="i understand you"),
    ])
    result = map_criterion_evidence(_ei(unified))
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a4 = next(i for i in rb.indicators if i.indicator == "A4")
    assert any(r.evidence_text == "i understand you" for r in a4.evidence_refs)
    assert a4.gaps == []


def test_5_b1_maps_concern_exploration():
    unified = _unified(candidate_events=[
        CandidateEvent(event="concern_exploration", turn_index=0, evidence_text="what worries you"),
    ])
    result = map_criterion_evidence(_ei(unified))
    pp = next(b for b in result.clinical if b.criterion == CRITERION_PATIENT_PERSPECTIVE)
    b1 = next(i for i in pp.indicators if i.indicator == "B1")
    assert any(r.evidence_text == "what worries you" for r in b1.evidence_refs)


def test_6_b2_no_detector_gap_when_no_cues_raised():
    from app.services.examiner_input import AVAILABILITY_LIMITED
    result = map_criterion_evidence(_ei())
    pp = next(b for b in result.clinical if b.criterion == CRITERION_PATIENT_PERSPECTIVE)
    b2 = next(i for i in pp.indicators if i.indicator == "B2")
    # No detector gap (a real detector exists, Step 21F) -- an empty session
    # is LIMITED (detector ran, found nothing), never the missing-detector
    # INSUFFICIENT/PARTIAL.
    assert b2.gaps == [] and b2.evidence_quality == AVAILABILITY_LIMITED


def test_6b_b2_maps_cue_response_events():
    unified = _unified(candidate_events=[
        CandidateEvent(
            event="cue_response", turn_index=1, evidence_text="I can see that's worrying you.",
            related_patient_turns=[0],
        ),
        CandidateEvent(
            event="cue_response_uncertain", turn_index=3, evidence_text="Let's move on.",
            related_patient_turns=[2], target_concern="cost",
        ),
    ])
    result = map_criterion_evidence(_ei(unified))
    pp = next(b for b in result.clinical if b.criterion == CRITERION_PATIENT_PERSPECTIVE)
    b2 = next(i for i in pp.indicators if i.indicator == "B2")
    texts = {r.evidence_text for r in b2.evidence_refs}
    assert texts == {"I can see that's worrying you.", "Let's move on."}
    assert b2.gaps == []


def test_6c_a2_maps_acknowledgement_reflective_and_dismissive():
    unified = _unified(candidate_events=[
        CandidateEvent(event="attentive_acknowledgement", turn_index=0, evidence_text="I see."),
        CandidateEvent(
            event="reflective_response", turn_index=2, evidence_text="You're worried about the pain.",
            related_patient_turns=[1],
        ),
        CandidateEvent(event="dismissive_response", turn_index=3, evidence_text="don't worry"),
    ])
    result = map_criterion_evidence(_ei(unified))
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a2 = next(i for i in rb.indicators if i.indicator == "A2")
    texts = {r.evidence_text for r in a2.evidence_refs}
    assert {"I see.", "You're worried about the pain.", "don't worry"} <= texts
    assert a2.gaps == []  # SESSION_CONTEXT carries interrupted_count=2, no gap


def test_6d_a2_no_detector_gap_when_nothing_said():
    from app.services.examiner_input import AVAILABILITY_STRONG
    result = map_criterion_evidence(_ei())
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a2 = next(i for i in rb.indicators if i.indicator == "A2")
    # No detector gap (real detectors exist, Step 21H). SESSION_CONTEXT still
    # carries interrupted_count=2, so the session-metrics ref alone is
    # present even with zero acknowledgement/reflective/dismissive events --
    # never a missing-detector gap.
    assert a2.gaps == [] and a2.evidence_quality == AVAILABILITY_STRONG
    assert len(a2.evidence_refs) == 1 and a2.evidence_refs[0].source == "session_metrics"


def test_6e_a2_interrupted_count_surfaced_as_session_metric_ref():
    result = map_criterion_evidence(_ei())
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a2 = next(i for i in rb.indicators if i.indicator == "A2")
    metric_refs = [r for r in a2.evidence_refs if r.source == "session_metrics"]
    assert len(metric_refs) == 1
    assert metric_refs[0].metadata == {"interrupted_count": 2}


def test_6f_a2_missing_interrupted_count_produces_gap():
    from app.services.criterion_evidence import REASON_NO_INTERRUPTION_METRIC
    from app.services.examiner_input import AVAILABILITY_INSUFFICIENT, AVAILABILITY_PARTIAL
    session_no_count = {"pipeline": "legacy", "session_usage_id": 1, "duration_seconds": 100.0}
    result = map_criterion_evidence(_ei(session=session_no_count))
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a2 = next(i for i in rb.indicators if i.indicator == "A2")
    assert a2.gaps and a2.gaps[0].reason_code == REASON_NO_INTERRUPTION_METRIC
    # No candidate events either in this scenario -> INSUFFICIENT (gap +
    # zero refs), not PARTIAL (gap + some refs) -- see _quality.
    assert a2.evidence_quality == AVAILABILITY_INSUFFICIENT

    unified = _unified(candidate_events=[
        CandidateEvent(event="attentive_acknowledgement", turn_index=0, evidence_text="I see."),
    ])
    result2 = map_criterion_evidence(_ei(unified, session=session_no_count))
    rb2 = next(b for b in result2.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a2_with_refs = next(i for i in rb2.indicators if i.indicator == "A2")
    assert a2_with_refs.gaps and a2_with_refs.gaps[0].reason_code == REASON_NO_INTERRUPTION_METRIC
    assert a2_with_refs.evidence_quality == AVAILABILITY_PARTIAL


def test_6g_a2_understanding_checked_no_longer_maps_here():
    """understanding_checked is E4-only now (Step 21H design decision) -- a
    stale placeholder proxy, not genuine A2 signal."""
    unified = _unified(candidate_events=[
        CandidateEvent(event="understanding_checked", turn_index=0, evidence_text="does that make sense"),
    ])
    result = map_criterion_evidence(_ei(unified))
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a2 = next(i for i in rb.indicators if i.indicator == "A2")
    assert all(r.evidence_text != "does that make sense" for r in a2.evidence_refs)
    ig = next(b for b in result.clinical if b.criterion == CRITERION_INFORMATION_GIVING)
    e4 = next(i for i in ig.indicators if i.indicator == "E4")
    assert any(r.evidence_text == "does that make sense" for r in e4.evidence_refs)


def test_7_b3_maps_concern_addressing():
    unified = _unified(candidate_events=[
        CandidateEvent(event="concern_addressing", turn_index=1, evidence_text="let me explain", source=SOURCE_SEMANTIC),
    ])
    result = map_criterion_evidence(_ei(unified))
    pp = next(b for b in result.clinical if b.criterion == CRITERION_PATIENT_PERSPECTIVE)
    b3 = next(i for i in pp.indicators if i.indicator == "B3")
    assert any(r.evidence_text == "let me explain" for r in b3.evidence_refs)


def test_7b_d2_maps_open_and_closed_questions():
    from app.services.examiner_input import CRITERION_INFORMATION_GATHERING
    unified = _unified(candidate_events=[
        CandidateEvent(event="open_question", turn_index=0, evidence_text="What brings you in today?"),
        CandidateEvent(event="closed_question", turn_index=1, evidence_text="Do you have any allergies?"),
    ])
    result = map_criterion_evidence(_ei(unified))
    ig = next(b for b in result.clinical if b.criterion == CRITERION_INFORMATION_GATHERING)
    d2 = next(i for i in ig.indicators if i.indicator == "D2")
    texts = {r.evidence_text for r in d2.evidence_refs}
    assert texts == {"What brings you in today?", "Do you have any allergies?"}
    assert d2.gaps == []


def test_7c_d3_maps_compound_and_leading_questions():
    from app.services.examiner_input import CRITERION_INFORMATION_GATHERING
    unified = _unified(candidate_events=[
        CandidateEvent(event="compound_question", turn_index=0, evidence_text="Do you smoke? Do you drink?"),
        CandidateEvent(event="leading_question", turn_index=1, evidence_text="You don't smoke, do you?"),
    ])
    result = map_criterion_evidence(_ei(unified))
    ig = next(b for b in result.clinical if b.criterion == CRITERION_INFORMATION_GATHERING)
    d3 = next(i for i in ig.indicators if i.indicator == "D3")
    texts = {r.evidence_text for r in d3.evidence_refs}
    assert texts == {"Do you smoke? Do you drink?", "You don't smoke, do you?"}
    assert d3.gaps == []


def test_7d_d2_d3_no_detector_gap_when_no_questions_asked():
    from app.services.examiner_input import AVAILABILITY_LIMITED, CRITERION_INFORMATION_GATHERING
    result = map_criterion_evidence(_ei())
    ig = next(b for b in result.clinical if b.criterion == CRITERION_INFORMATION_GATHERING)
    d2 = next(i for i in ig.indicators if i.indicator == "D2")
    d3 = next(i for i in ig.indicators if i.indicator == "D3")
    # No detector gap (a real detector exists) -- an empty session is LIMITED
    # (detector ran, found nothing), never the missing-detector INSUFFICIENT/PARTIAL.
    assert d2.gaps == [] and d2.evidence_quality == AVAILABILITY_LIMITED
    assert d3.gaps == [] and d3.evidence_quality == AVAILABILITY_LIMITED


# ── D1 active listening / interruption (Step 21J) ─────────────────────────

def _d1(unified=None, session=SESSION_CONTEXT):
    from app.services.examiner_input import CRITERION_INFORMATION_GATHERING
    result = map_criterion_evidence(_ei(unified, session=session))
    ig = next(b for b in result.clinical if b.criterion == CRITERION_INFORMATION_GATHERING)
    return next(i for i in ig.indicators if i.indicator == "D1")


def test_8a_d1_reuses_cue_response_as_support():
    from app.services.speaking_evidence import PatientEvent
    unified = _unified(
        patient_events=[PatientEvent(event="concern_raised", turn_index=0, evidence_text="pain")],
        candidate_events=[CandidateEvent(
            event="cue_response", turn_index=1, evidence_text="let's talk about that",
            related_patient_turns=[0],
        )],
    )
    d1 = _d1(unified)
    assert any(r.evidence_id == "cue_response" for r in d1.evidence_refs)


def test_8b_d1_reuses_clarification_as_support():
    unified = _unified(candidate_events=[
        CandidateEvent(event="clarification_request", turn_index=1, evidence_text="What do you mean?"),
    ])
    d1 = _d1(unified)
    assert any(r.evidence_id == "clarification_request" for r in d1.evidence_refs)


def test_8c_d1_reuses_summary_as_support():
    unified = _unified(candidate_events=[
        CandidateEvent(event="summary_statement", turn_index=2, evidence_text="So you've had pain."),
    ])
    d1 = _d1(unified)
    assert any(r.evidence_id == "summary_statement" for r in d1.evidence_refs)


def test_8d_d1_reuses_acknowledgement_as_support():
    unified = _unified(candidate_events=[
        CandidateEvent(event="attentive_acknowledgement", turn_index=1, evidence_text="I see."),
    ])
    d1 = _d1(unified)
    assert any(r.evidence_id == "attentive_acknowledgement" for r in d1.evidence_refs)


def test_8e_d1_and_d4_both_carry_the_same_clarification_no_dedup():
    from app.services.examiner_input import CRITERION_INFORMATION_GATHERING
    unified = _unified(candidate_events=[
        CandidateEvent(event="clarification_request", turn_index=1, evidence_text="What do you mean?"),
    ])
    result = map_criterion_evidence(_ei(unified))
    ig = next(b for b in result.clinical if b.criterion == CRITERION_INFORMATION_GATHERING)
    d1 = next(i for i in ig.indicators if i.indicator == "D1")
    d4 = next(i for i in ig.indicators if i.indicator == "D4")
    assert any(r.evidence_id == "clarification_request" for r in d1.evidence_refs)
    assert any(r.evidence_id == "clarification_request" for r in d4.evidence_refs)


def test_8f_unaddressed_patient_contribution_present_when_cue_unanswered():
    from app.services.speaking_evidence import PatientEvent
    unified = _unified(
        patient_events=[PatientEvent(event="concern_raised", turn_index=0, evidence_text="pain")],
        candidate_events=[],
    )
    d1 = _d1(unified)
    unaddressed = [r for r in d1.evidence_refs if r.evidence_id == "unaddressed_patient_contribution"]
    assert len(unaddressed) == 1
    assert unaddressed[0].turn_index == 0
    assert unaddressed[0].provenance == "deterministic_rule"
    assert unaddressed[0].evidence_level == LEVEL_L2_DETERMINISTIC


def test_8g_addressed_cue_not_flagged_unaddressed():
    from app.services.speaking_evidence import PatientEvent
    unified = _unified(
        patient_events=[PatientEvent(event="concern_raised", turn_index=0, evidence_text="pain")],
        candidate_events=[CandidateEvent(
            event="cue_response", turn_index=1, evidence_text="tell me more",
            related_patient_turns=[0],
        )],
    )
    d1 = _d1(unified)
    assert not any(r.evidence_id == "unaddressed_patient_contribution" for r in d1.evidence_refs)


def test_8h_interruption_metric_surfaced_with_direction():
    d1 = _d1()  # SESSION_CONTEXT default carries interrupted_count=2
    ref = next(r for r in d1.evidence_refs if r.evidence_id == "interrupted_count")
    assert ref.metadata["interrupted_count"] == 2
    assert ref.metadata["interruption_direction"] == "candidate_over_patient"
    assert ref.metadata["turn_attribution"] == "session_level_only"
    assert ref.provenance == "direct"
    assert d1.gaps == []


def test_8i_zero_interruptions_no_direction_no_positive_claim():
    session = dict(SESSION_CONTEXT, interrupted_count=0)
    d1 = _d1(session=session)
    ref = next(r for r in d1.evidence_refs if r.evidence_id == "interrupted_count")
    assert ref.metadata["interrupted_count"] == 0
    assert ref.metadata["interruption_direction"] is None
    assert d1.gaps == []  # a real, known 0 is not a missing-metric gap


def test_8j_missing_interruption_metric_preserves_gap_reason():
    from app.services.criterion_evidence import REASON_NO_INTERRUPTION_METRIC
    session = dict(SESSION_CONTEXT)
    del session["interrupted_count"]
    d1 = _d1(session=session)
    assert d1.gaps and d1.gaps[0].reason_code == REASON_NO_INTERRUPTION_METRIC
    assert not any(r.evidence_id == "interrupted_count" for r in d1.evidence_refs)


def test_8k_no_score_band_or_judgement_on_indicator():
    d1 = _d1()
    fields = type(d1).model_fields.keys()
    for banned in ("score", "band", "penalty", "good_listener", "poor_listener"):
        assert banned not in fields


def test_8l_full_speaking_evidence_pipeline_integration():
    """SpeakingEvidence -> reconcile_evidence -> ExaminerInput -> D1, exactly
    the production path -- no direct construction of UnifiedEvidence."""
    from app.services.speaking_evidence import build_speaking_evidence
    from app.services.evidence_reconciliation import reconcile_evidence
    from app.services.examiner_input import build_examiner_input

    card = {
        "patient_name": "Sam", "mood": "anxious",
        "questions_to_ask": ["Will I be able to walk again?"],
    }
    history = [
        {"role": "nurse", "content": "Hello Sam, how are you feeling today?"},
        {"role": "patient", "content": "I'm really worried about walking again."},
        {"role": "nurse", "content": "What do you mean by worried?"},
    ]
    evidence = build_speaking_evidence(card, history)
    unified = reconcile_evidence(evidence)
    ei = build_examiner_input({"interlocutor_card": card}, history, unified, SESSION_CONTEXT, None)
    result = map_criterion_evidence(ei)
    from app.services.examiner_input import CRITERION_INFORMATION_GATHERING
    ig = next(b for b in result.clinical if b.criterion == CRITERION_INFORMATION_GATHERING)
    d1 = next(i for i in ig.indicators if i.indicator == "D1")
    assert any(r.evidence_id == "clarification_request" for r in d1.evidence_refs)


def test_7e_c2_maps_signposting_and_topic_transition():
    unified = _unified(candidate_events=[
        CandidateEvent(event="signposting_detected", turn_index=0, evidence_text="Now let's talk about your medication."),
        CandidateEvent(event="topic_transition_detected", turn_index=0, evidence_text="your medication"),
    ])
    result = map_criterion_evidence(_ei(unified))
    ps = next(b for b in result.clinical if b.criterion == CRITERION_PROVIDING_STRUCTURE)
    c2 = next(i for i in ps.indicators if i.indicator == "C2")
    texts = {r.evidence_text for r in c2.evidence_refs}
    assert texts == {"Now let's talk about your medication.", "your medication"}
    assert c2.gaps == []


def test_7f_c3_maps_organization_markers_in_turn_order():
    unified = _unified(candidate_events=[
        CandidateEvent(event="organization_marker", turn_index=2, evidence_text="First, your medication."),
        CandidateEvent(event="organization_marker", turn_index=3, evidence_text="Second, your diet."),
    ])
    result = map_criterion_evidence(_ei(unified))
    ps = next(b for b in result.clinical if b.criterion == CRITERION_PROVIDING_STRUCTURE)
    c3 = next(i for i in ps.indicators if i.indicator == "C3")
    assert [r.turn_index for r in c3.evidence_refs] == [2, 3]
    assert c3.gaps == []


def test_7g_c3_partial_sequence_evidence_present_not_gapped():
    unified = _unified(candidate_events=[
        CandidateEvent(event="organization_marker_partial", turn_index=0, evidence_text="First, let's look at your chart."),
    ])
    result = map_criterion_evidence(_ei(unified))
    ps = next(b for b in result.clinical if b.criterion == CRITERION_PROVIDING_STRUCTURE)
    c3 = next(i for i in ps.indicators if i.indicator == "C3")
    assert len(c3.evidence_refs) == 1
    assert c3.gaps == []


def test_7h_c2_c3_no_detector_gap_when_nothing_said():
    from app.services.examiner_input import AVAILABILITY_LIMITED
    result = map_criterion_evidence(_ei())
    ps = next(b for b in result.clinical if b.criterion == CRITERION_PROVIDING_STRUCTURE)
    c2 = next(i for i in ps.indicators if i.indicator == "C2")
    c3 = next(i for i in ps.indicators if i.indicator == "C3")
    assert c2.gaps == [] and c2.evidence_quality == AVAILABILITY_LIMITED
    assert c3.gaps == [] and c3.evidence_quality == AVAILABILITY_LIMITED


def test_8_e4_maps_understanding_check():
    unified = _unified(candidate_events=[
        CandidateEvent(event="understanding_checked", turn_index=1, evidence_text="does that make sense"),
    ])
    result = map_criterion_evidence(_ei(unified))
    ig = next(b for b in result.clinical if b.criterion == CRITERION_INFORMATION_GIVING)
    e4 = next(i for i in ig.indicators if i.indicator == "E4")
    assert any(r.evidence_text == "does that make sense" for r in e4.evidence_refs)


def test_9_jargon_maps_to_appropriateness():
    unified = _unified(jargon_evidence=[
        JargonEvidence(term="cannula", turn_index=0, evidence_text="cannula"),
    ])
    result = map_criterion_evidence(_ei(unified))
    appropriateness = next(b for b in result.linguistic if b.criterion == CRITERION_APPROPRIATENESS_OF_LANGUAGE)
    assert any(r.evidence_id == "cannula" for r in appropriateness.evidence_refs)


def test_10_pronunciation_maps_to_intelligibility():
    result = map_criterion_evidence(_ei(audio=ELITE_AUDIO_EVIDENCE))
    intelligibility = next(b for b in result.linguistic if b.criterion == CRITERION_INTELLIGIBILITY)
    assert intelligibility.gaps == []
    assert any(r.metadata.get("overall_score") == 82.5 for r in intelligibility.evidence_refs)


def test_11_fluency_evidence_maps_to_fluency():
    result = map_criterion_evidence(_ei(audio=ELITE_AUDIO_EVIDENCE))
    fluency = next(b for b in result.linguistic if b.criterion == CRITERION_FLUENCY)
    assert fluency.gaps == []
    assert any(r.metadata.get("fluency_score") == 79.0 for r in fluency.evidence_refs)


# ── Gaps (12-14) ────────────────────────────────────────────────────────

def test_12_a3_no_detector_gap_when_nothing_said():
    from app.services.examiner_input import AVAILABILITY_LIMITED
    result = map_criterion_evidence(_ei())
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a3 = next(i for i in rb.indicators if i.indicator == "A3")
    # No detector gap anymore (Step 21I: a real detector exists) -- an empty
    # session is LIMITED (detector ran, found nothing), never the missing-
    # detector INSUFFICIENT/PARTIAL. See module docstring, MISSING vs NEGATIVE.
    assert a3.gaps == [] and a3.evidence_quality == AVAILABILITY_LIMITED


def test_12b_a3_maps_judgmental_supportive_and_uncertain_events():
    unified = _unified(candidate_events=[
        CandidateEvent(
            event="potentially_judgmental", turn_index=1, evidence_text="You should have continued it.",
            related_patient_turns=[0],
        ),
        CandidateEvent(event="supportive_nonjudgmental", turn_index=2, evidence_text="It's understandable that you struggled with this."),
        CandidateEvent(event="uncertain_judgment", turn_index=3, evidence_text="Why didn't you take it?"),
    ])
    result = map_criterion_evidence(_ei(unified))
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a3 = next(i for i in rb.indicators if i.indicator == "A3")
    texts = {r.evidence_text for r in a3.evidence_refs}
    assert texts == {
        "You should have continued it.",
        "It's understandable that you struggled with this.",
        "Why didn't you take it?",
    }
    assert a3.gaps == []
    related = {r.evidence_text: r.related_patient_turn for r in a3.evidence_refs}
    assert related["You should have continued it."] == 0
    assert related["It's understandable that you struggled with this."] is None


def test_13_missing_audio_produces_gap():
    result = map_criterion_evidence(_ei(audio=None))
    intelligibility = next(b for b in result.linguistic if b.criterion == CRITERION_INTELLIGIBILITY)
    fluency = next(b for b in result.linguistic if b.criterion == CRITERION_FLUENCY)
    assert len(intelligibility.gaps) == 1
    assert len(fluency.gaps) == 1
    assert intelligibility.audio_available is False


def test_14_missing_grammar_evidence_always_gapped():
    result = map_criterion_evidence(_ei())
    grammar = next(b for b in result.linguistic if b.criterion == CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION)
    assert len(grammar.gaps) == 1


# ── Integrity (15-18) ──────────────────────────────────────────────────

def test_15_provenance_preserved_on_refs():
    unified = _unified(jargon_evidence=[JargonEvidence(term="cannula", turn_index=0, evidence_text="cannula")])
    result = map_criterion_evidence(_ei(unified))
    appropriateness = next(b for b in result.linguistic if b.criterion == CRITERION_APPROPRIATENESS_OF_LANGUAGE)
    jargon_ref = next(r for r in appropriateness.evidence_refs if r.source == "jargon_evidence")
    assert jargon_ref.provenance == SOURCE_DETERMINISTIC
    assert jargon_ref.evidence_level == LEVEL_L2_DETERMINISTIC


def test_16_deterministic_and_semantic_disagreement_both_kept():
    unified = _unified(candidate_events=[
        CandidateEvent(event="empathy_acknowledgement", turn_index=1, evidence_text="i understand you", source=SOURCE_DETERMINISTIC),
        CandidateEvent(event="empathy_acknowledgement", turn_index=1, evidence_text="that sounds hard", source=SOURCE_SEMANTIC),
    ])
    result = map_criterion_evidence(_ei(unified))
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a4 = next(i for i in rb.indicators if i.indicator == "A4")
    texts = {r.evidence_text for r in a4.evidence_refs}
    levels = {r.evidence_level for r in a4.evidence_refs}
    assert "i understand you" in texts and "that sounds hard" in texts
    assert LEVEL_L2_DETERMINISTIC in levels and LEVEL_L3_SEMANTIC in levels


_FORBIDDEN_KEYS = {"score", "band", "penalty", "pass_fail", "weighted_average", "performance"}


def _assert_no_score_keys(obj):
    """Recursive structural check: no dict anywhere in the dump uses a
    score/judgement KEY. Deliberately not a substring search over values --
    passthrough Azure pronunciation fields like "overall_score" are raw
    ACOUSTIC EVIDENCE (Step 13), not a judgement this mapper computed."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in _FORBIDDEN_KEYS, f"forbidden key found: {k}"
            _assert_no_score_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_score_keys(item)


def test_17_missing_is_never_negative():
    result = map_criterion_evidence(_ei())
    _assert_no_score_keys(result.model_dump())


def test_18_patient_outcome_distinct_from_candidate_action():
    unified = _unified(candidate_events=[CandidateEvent(event="empathy_acknowledgement", turn_index=0, evidence_text="i understand you")])
    result = map_criterion_evidence(_ei(unified))
    pp = next(b for b in result.clinical if b.criterion == CRITERION_PATIENT_PERSPECTIVE)
    b2 = next(i for i in pp.indicators if i.indicator == "B2")
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    a4 = next(i for i in rb.indicators if i.indicator == "A4")
    candidate_refs = [r for r in a4.evidence_refs if r.source == "candidate_event"]
    patient_refs = [r for r in b2.evidence_refs if r.source == "patient_event"]
    assert all(r.evidence_level in (LEVEL_L2_DETERMINISTIC, LEVEL_L3_SEMANTIC) for r in candidate_refs)
    assert all(r.evidence_level == LEVEL_L4_PATIENT_OUTCOME for r in patient_refs)


# ── Multi-turn (19-20) ────────────────────────────────────────────────────

def test_19_concern_sequence_preserved_with_turn_indices():
    unified = _unified(concern_outcomes=[ConcernOutcome(
        concern="Will I walk again?", final_status="resolved", resolved=True,
        history=[
            {"status": "raised", "turn_index": 0, "cause_event": None},
            {"status": "explored", "turn_index": 1, "cause_event": "concern_exploration"},
            {"status": "addressed", "turn_index": 2, "cause_event": "empathy_acknowledgement"},
        ],
    )])
    result = map_criterion_evidence(_ei(unified))
    pp = next(b for b in result.clinical if b.criterion == CRITERION_PATIENT_PERSPECTIVE)
    b1 = next(i for i in pp.indicators if i.indicator == "B1")
    b3 = next(i for i in pp.indicators if i.indicator == "B3")
    assert {r.turn_index for r in b1.evidence_refs} == {0, 1}
    assert {r.turn_index for r in b3.evidence_refs} == {2}


def test_20_reopened_concern_flagged_in_metadata():
    unified = _unified(concern_outcomes=[ConcernOutcome(
        concern="Will I walk again?", final_status="addressed", resolved=False,
        history=[
            {"status": "addressed", "turn_index": 1, "cause_event": None},
            {"status": "raised", "turn_index": 3, "cause_event": None},
        ],
        reopened_events=[{"turn_index": 3, "from_status": "addressed", "to_status": "raised", "reason": "still worried"}],
    )])
    result = map_criterion_evidence(_ei(unified))
    pp = next(b for b in result.clinical if b.criterion == CRITERION_PATIENT_PERSPECTIVE)
    b1 = next(i for i in pp.indicators if i.indicator == "B1")  # reopen entry's status ("raised") falls under B1's filter, not B3's
    assert any(r.metadata.get("reopened") for r in b1.evidence_refs)


# ── Determinism / serialization (21-22) ───────────────────────────────────

def test_21_same_input_same_mapping():
    unified = _unified(candidate_events=[CandidateEvent(event="empathy_acknowledgement", turn_index=0, evidence_text="i understand you")])
    ei = _ei(unified, audio=ELITE_AUDIO_EVIDENCE)
    r1 = map_criterion_evidence(ei)
    r2 = map_criterion_evidence(ei)
    assert r1 == r2
    assert r1.model_dump() == r2.model_dump()


def test_22_roundtrip_serialization():
    from app.services.criterion_evidence import CriterionEvidenceMap
    result = map_criterion_evidence(_ei(audio=ELITE_AUDIO_EVIDENCE))
    rebuilt = CriterionEvidenceMap.model_validate(result.model_dump())
    assert rebuilt == result


# ── Edge cases (23-25) ─────────────────────────────────────────────────

def test_23_empty_evidence_builds_without_error():
    result = map_criterion_evidence(_ei(transcript=[], audio=None, session=None))
    assert len(result.clinical) == 5
    assert len(result.linguistic) == 4
    for b in result.clinical:
        for i in b.indicators:
            assert i.evidence_quality in (AVAILABILITY_INSUFFICIENT, "LIMITED")


def test_24_minimal_scenario():
    result = map_criterion_evidence(_ei(scenario={}, transcript=[]))
    assert len(result.clinical) == 5


def test_25_multiple_concerns_mapped_independently():
    unified = _unified(concern_outcomes=[
        ConcernOutcome(concern="Will I walk again?", final_status="raised", resolved=False,
                        history=[{"status": "raised", "turn_index": 0, "cause_event": None}]),
        ConcernOutcome(concern="Will there be a scar?", final_status="explored", resolved=False,
                        history=[{"status": "raised", "turn_index": 1, "cause_event": None},
                                 {"status": "explored", "turn_index": 2, "cause_event": None}]),
    ])
    result = map_criterion_evidence(_ei(unified))
    pp = next(b for b in result.clinical if b.criterion == CRITERION_PATIENT_PERSPECTIVE)
    b1 = next(i for i in pp.indicators if i.indicator == "B1")
    concerns = {r.metadata.get("concern") for r in b1.evidence_refs}
    assert "Will I walk again?" in concerns and "Will there be a scar?" in concerns


# ── Criterion-level quality aggregation (26) ──────────────────────────────

def test_26_criterion_quality_is_worst_of_its_indicators():
    from app.services.examiner_input import AVAILABILITY_LIMITED
    result = map_criterion_evidence(_ei())
    rb = next(b for b in result.clinical if b.criterion == CRITERION_RELATIONSHIP_BUILDING)
    # No detector gaps left in Relationship Building after Step 21I (A1-A4 all
    # have real detectors now) -- with no candidate events, A1/A3/A4 are
    # LIMITED (detector ran, found nothing) and A2 is STRONG (session
    # interrupted_count ref present), so LIMITED is the worst of the four.
    assert rb.criterion_evidence_quality == AVAILABILITY_LIMITED


# ── Golden fixtures (Step 28): 12 offline builds, no scores ──────────────

def _fixture_1_a4_empathy():
    unified = _unified(candidate_events=[CandidateEvent(event="empathy_acknowledgement", turn_index=0, evidence_text="i understand you")])
    return map_criterion_evidence(_ei(unified))


def _fixture_2_b1_exploration():
    unified = _unified(candidate_events=[CandidateEvent(event="concern_exploration", turn_index=0, evidence_text="what worries you")])
    return map_criterion_evidence(_ei(unified))


def _fixture_3_b3_addressing():
    unified = _unified(candidate_events=[CandidateEvent(event="concern_addressing", turn_index=1, evidence_text="let me explain", source=SOURCE_SEMANTIC)])
    return map_criterion_evidence(_ei(unified))


def _fixture_4_e4_understanding_check():
    unified = _unified(candidate_events=[CandidateEvent(event="understanding_checked", turn_index=1, evidence_text="does that make sense")])
    return map_criterion_evidence(_ei(unified))


def _fixture_5_mixed_provenance():
    unified = _unified(candidate_events=[
        CandidateEvent(event="jargon_used", turn_index=0, evidence_text="cannula", source=SOURCE_DETERMINISTIC),
        CandidateEvent(event="jargon_used", turn_index=0, evidence_text="cannula", source=SOURCE_SEMANTIC),
    ])
    return map_criterion_evidence(_ei(unified))


def _fixture_6_all_evidence_missing():
    return map_criterion_evidence(_ei(transcript=[], audio=None, session=None))


def _fixture_7_elite_pronunciation():
    return map_criterion_evidence(_ei(audio=ELITE_AUDIO_EVIDENCE))


def _fixture_8_no_audio():
    return map_criterion_evidence(_ei(audio=None))


def _fixture_9_multiple_concerns():
    unified = _unified(concern_outcomes=[
        ConcernOutcome(concern="Will I walk again?", final_status="raised", resolved=False, history=[]),
        ConcernOutcome(concern="Will there be a scar?", final_status="not_raised", resolved=False, history=[]),
    ])
    return map_criterion_evidence(_ei(unified))


def _fixture_10_reopened_concern():
    unified = _unified(concern_outcomes=[ConcernOutcome(
        concern="Will I walk again?", final_status="addressed", resolved=False,
        history=[{"status": "addressed", "turn_index": 1, "cause_event": None}, {"status": "raised", "turn_index": 3, "cause_event": None}],
        reopened_events=[{"turn_index": 3, "from_status": "addressed", "to_status": "raised", "reason": "still worried"}],
    )])
    return map_criterion_evidence(_ei(unified))


def _fixture_11_evidence_conflict():
    unified = _unified(candidate_events=[
        CandidateEvent(event="empathy_acknowledgement", turn_index=1, evidence_text="i understand you", source=SOURCE_DETERMINISTIC),
        CandidateEvent(event="empathy_acknowledgement", turn_index=1, evidence_text="that sounds hard", source=SOURCE_SEMANTIC),
    ])
    return map_criterion_evidence(_ei(unified))


def _fixture_12_missing_not_negative():
    return map_criterion_evidence(_ei())


GOLDEN_FIXTURES = [
    _fixture_1_a4_empathy, _fixture_2_b1_exploration, _fixture_3_b3_addressing, _fixture_4_e4_understanding_check,
    _fixture_5_mixed_provenance, _fixture_6_all_evidence_missing, _fixture_7_elite_pronunciation, _fixture_8_no_audio,
    _fixture_9_multiple_concerns, _fixture_10_reopened_concern, _fixture_11_evidence_conflict, _fixture_12_missing_not_negative,
]


@pytest.mark.parametrize("build_fixture", GOLDEN_FIXTURES)
def test_27_golden_fixtures_build_without_error_and_carry_no_score(build_fixture):
    result = build_fixture()
    assert len(result.clinical) == 5
    assert len(result.linguistic) == 4
    _assert_no_score_keys(result.model_dump())


# ── Invalid input (28) ─────────────────────────────────────────────────

def test_28_invalid_examiner_input_type_rejected():
    with pytest.raises(ValueError):
        map_criterion_evidence({"not": "an examiner input"})
