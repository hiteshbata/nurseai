"""Tests for the ExaminerInput assembler (Step 19).

Pure unit tests: every input is hand-built directly (UnifiedEvidence via its
pydantic models, scenario/session/audio via plain dicts) -- build_examiner_input
is a pure function over already-computed evidence, so these exercise exactly
the packaging/gap logic, not the upstream detectors already covered by
test_speaking_evidence.py / test_evidence_reconciliation.py / test_semantic_evidence.py.
"""
import pytest

from app.services.evidence_reconciliation import UnifiedEvidence
from app.services.examiner_input import (
    ALL_CRITERIA,
    AVAILABILITY_INSUFFICIENT,
    AVAILABILITY_PARTIAL,
    CLINICAL_CRITERIA,
    CRITERION_APPROPRIATENESS_OF_LANGUAGE,
    CRITERION_FLUENCY,
    CRITERION_INTELLIGIBILITY,
    CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION,
    INDICATORS_BY_CRITERION,
    LINGUISTIC_CRITERIA,
    build_examiner_input,
)
from app.services.speaking_evidence import (
    CandidateEvent,
    ConcernOutcome,
    HiddenInfoOutcome,
    InteractionMetrics,
    JargonEvidence,
    PatientEvent,
    SOURCE_DETERMINISTIC,
    SOURCE_SEMANTIC,
    SpeakingEvidence,
    StateTransition,
)
from app.services.evidence_reconciliation import reconcile_evidence

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
    "difficulty": "medium", "specialty": "surgical",
    "nurse_card": {"tasks": ["Explain dressing change", "Address pain concerns"]},
    "interlocutor_card": {
        "patient_name": "Sam", "age": 58, "condition": "post-operative",
        "mood": "anxious", "background": "First surgery, lives alone.",
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
        "completeness_score": 95.0,
        "words": [{"word": "hello", "accuracy_score": 90.0, "error_type": "None"}],
        "problem_words": [], "transcript": "Hello Sam how are you feeling today",
    },
    "pattern_analysis": [{"pattern": "V/W confusion", "word_said": "wery", "word_correct": "very", "tip": "practice"}],
    "has_azure": True,
}

NO_AUDIO_EVIDENCE = {
    "method": "pattern_analysis", "azure": None,
    "pattern_analysis": [], "has_azure": False,
}

SESSION_CONTEXT = {
    "pipeline": "realtime", "session_usage_id": 123,
    "duration_seconds": 245.5, "interrupted_count": 2,
}


# ── Schema: 9 criteria / 19 indicators (1, 2) ────────────────────────────

def test_1_all_9_criteria_represented():
    assert len(ALL_CRITERIA) == 9
    assert len(set(ALL_CRITERIA)) == 9
    assert set(LINGUISTIC_CRITERIA) | set(CLINICAL_CRITERIA) == set(ALL_CRITERIA)


def test_2_all_20_indicators_supported():
    # PDF has 20 (A1-4=4, B1-3=3, C1-3=3, D1-5=5, E1-5=5); the task spec's
    # "19/19" is a miscount against its own listed A1..E5 codes -- the PDF
    # is the controlling spec, so this follows the PDF's real count.
    all_indicators = [i for indicators in INDICATORS_BY_CRITERION.values() for i in indicators]
    assert len(all_indicators) == 20
    assert set(all_indicators) == {
        "A1", "A2", "A3", "A4", "B1", "B2", "B3", "C1", "C2", "C3",
        "D1", "D2", "D3", "D4", "D5", "E1", "E2", "E3", "E4", "E5",
    }


def test_3_linguistic_criteria_have_no_indicators():
    for criterion in LINGUISTIC_CRITERIA:
        assert INDICATORS_BY_CRITERION[criterion] == []


def test_4_clinical_criteria_have_no_scores_only_evidence():
    # ExaminerInput has no score field anywhere -- structural check.
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), SESSION_CONTEXT, None)
    assert "score" not in result.model_dump()
    assert not hasattr(result.clinical_evidence, "score")


# ── Evidence retention (5, 6, 7, 8) ───────────────────────────────────────

def test_5_unified_evidence_retained_intact():
    unified = _unified(candidate_events=[
        CandidateEvent(event="empathy_acknowledgement", turn_index=0, evidence_text="i understand you"),
    ])
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, None)
    assert result.clinical_evidence.unified_evidence == unified


def test_6_provenance_retained():
    unified = _unified(candidate_events=[
        CandidateEvent(event="jargon_used", turn_index=0, evidence_text="cannula", source=SOURCE_SEMANTIC),
    ])
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, None)
    assert result.clinical_evidence.unified_evidence.candidate_events[0].provenance == SOURCE_SEMANTIC


def test_7_evidence_gaps_represented():
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), SESSION_CONTEXT, None)
    assert len(result.evidence_gaps) > 0
    assert all(g.criterion in ALL_CRITERIA for g in result.evidence_gaps)


def test_8_missing_is_not_negative():
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), SESSION_CONTEXT, None)
    for gap in result.evidence_gaps:
        assert gap.availability in (AVAILABILITY_PARTIAL, AVAILABILITY_INSUFFICIENT, "STRONG", "LIMITED")
        # never a performance verdict
        assert not hasattr(gap, "score")
        assert not hasattr(gap, "performance")


# ── Audio (9, 10, 11) ──────────────────────────────────────────────────────

def test_9_elite_pronunciation_data_represented():
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), SESSION_CONTEXT, ELITE_AUDIO_EVIDENCE)
    assert result.audio_availability.audio_available is True
    assert result.audio_availability.pronunciation_evidence_available is True
    assert result.linguistic_evidence.pronunciation.overall_score == 82.5
    assert result.linguistic_evidence.accent_pattern_hints[0]["word_said"] == "wery"
    gap_criteria = {g.criterion for g in result.evidence_gaps}
    assert CRITERION_INTELLIGIBILITY not in gap_criteria
    assert CRITERION_FLUENCY not in gap_criteria


def test_10_no_audio_state_represented():
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), SESSION_CONTEXT, NO_AUDIO_EVIDENCE)
    assert result.audio_availability.audio_available is False
    assert result.linguistic_evidence.pronunciation is None
    gap_criteria = {g.criterion for g in result.evidence_gaps}
    assert CRITERION_INTELLIGIBILITY in gap_criteria
    assert CRITERION_FLUENCY in gap_criteria


def test_11_no_fabricated_audio_evidence_when_none_passed():
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), SESSION_CONTEXT, None)
    assert result.linguistic_evidence.pronunciation is None
    assert result.linguistic_evidence.accent_pattern_hints == []


# ── Session (12, 13) ───────────────────────────────────────────────────────

def test_12_valid_session_metrics():
    unified = _unified(interaction_metrics=InteractionMetrics(
        turn_counts={"nurse": 3, "patient": 3, "total": 6},
        jargon_events=0, empathy_events=0, concern_exploration_events=0,
        understanding_check_events=0, dismissive_events=0,
    ))
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, None)
    assert result.session_context.turn_count == 6
    assert result.session_context.nurse_turn_count == 3
    assert result.session_context.duration_seconds == 245.5
    assert result.session_context.interrupted_count == 2


def test_13_unavailable_timing_remains_unavailable():
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), session_context=None, audio_evidence=None)
    assert result.session_context.duration_seconds is None
    assert result.session_context.interrupted_count is None
    assert result.session_context.pipeline is None


# ── Determinism (14) ────────────────────────────────────────────────────

def test_14_identical_input_identical_output():
    unified = _unified(candidate_events=[
        CandidateEvent(event="empathy_acknowledgement", turn_index=0, evidence_text="i understand you"),
    ])
    r1 = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, ELITE_AUDIO_EVIDENCE)
    r2 = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, ELITE_AUDIO_EVIDENCE)
    assert r1 == r2
    assert r1.model_dump() == r2.model_dump()


# ── Serialization (15) ───────────────────────────────────────────────────

def test_15_roundtrip_preserves_evidence():
    from app.services.examiner_input import ExaminerInput

    unified = _unified(
        candidate_events=[CandidateEvent(event="jargon_used", turn_index=0, evidence_text="cannula")],
        hidden_info_outcomes=[HiddenInfoOutcome(item="History of falls", candidate_detected=False, verification_status="not_called", final_status="hidden")],
    )
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, ELITE_AUDIO_EVIDENCE)
    as_dict = result.model_dump()
    rebuilt = ExaminerInput.model_validate(as_dict)
    assert rebuilt == result
    assert len(rebuilt.evidence_gaps) == len(result.evidence_gaps)
    assert rebuilt.clinical_evidence.unified_evidence.hidden_info_outcomes[0].item == "History of falls"
    assert rebuilt.audio_availability.audio_available is True


# ── Edge cases (16-20) ────────────────────────────────────────────────────

def test_16_minimal_scenario():
    result = build_examiner_input({}, [], _unified(), None, None)
    assert result.scenario_context.title == ""
    assert result.scenario_context.nurse_tasks == []
    assert result.scenario_context.hidden_information_items == []


def test_17_empty_transcript():
    result = build_examiner_input(BASE_SCENARIO, [], _unified(), SESSION_CONTEXT, None)
    assert result.transcript == []
    assert result.session_context.turn_count == 0


def test_18_partial_evidence():
    unified = _unified(
        concern_outcomes=[ConcernOutcome(concern="Will I walk again?", final_status="raised", resolved=False, history=[{"status": "raised", "turn_index": 0, "cause_event": None}])],
    )
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, None)
    assert result.clinical_evidence.unified_evidence.concern_outcomes[0].deterministic_final_status == "raised"


def test_19_mixed_provenance():
    unified = _unified(candidate_events=[
        CandidateEvent(event="empathy_acknowledgement", turn_index=1, evidence_text="i understand you", source=SOURCE_DETERMINISTIC),
        CandidateEvent(event="empathy_acknowledgement", turn_index=1, evidence_text="that sounds hard", source=SOURCE_SEMANTIC),
    ])
    result = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, None)
    assert result.clinical_evidence.unified_evidence.candidate_events[0].provenance == "hybrid"


def test_20_session_isolation():
    unified_a = _unified(candidate_events=[CandidateEvent(event="jargon_used", turn_index=0, evidence_text="cannula")])
    unified_b = _unified()
    result_a = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified_a, SESSION_CONTEXT, None)
    result_b = build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified_b, SESSION_CONTEXT, None)
    assert len(result_a.clinical_evidence.unified_evidence.candidate_events) == 1
    assert len(result_b.clinical_evidence.unified_evidence.candidate_events) == 0
    # mutating one result must not affect the other
    result_a.evidence_gaps.append(result_a.evidence_gaps[0])
    assert len(result_a.evidence_gaps) != len(result_b.evidence_gaps)


# ── Validation (invalid input fails clearly) ──────────────────────────────

def test_21_invalid_unified_evidence_type_rejected():
    with pytest.raises(ValueError):
        build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, {"not": "unified_evidence"}, SESSION_CONTEXT, None)


def test_22_invalid_transcript_type_rejected():
    with pytest.raises(ValueError):
        build_examiner_input(BASE_SCENARIO, "not a list", _unified(), SESSION_CONTEXT, None)


# ── Golden fixtures (Step 22): 10 offline ExaminerInput builds, no scores ──

def _fixture_1_complete_clinical():
    unified = _unified(
        candidate_events=[CandidateEvent(event="empathy_acknowledgement", turn_index=1, evidence_text="i understand you")],
        concern_outcomes=[ConcernOutcome(
            concern="Will I be able to walk again?", final_status="resolved", resolved=True,
            history=[{"status": "raised", "turn_index": 0, "cause_event": None}, {"status": "addressed", "turn_index": 1, "cause_event": "empathy_acknowledgement"}],
            resolved_at_turns=[1],
        )],
    )
    return build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, ELITE_AUDIO_EVIDENCE)


def _fixture_2_partial_clinical():
    unified = _unified(concern_outcomes=[ConcernOutcome(concern="Will I be able to walk again?", final_status="raised", resolved=False, history=[{"status": "raised", "turn_index": 0, "cause_event": None}])])
    return build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, None)


def _fixture_3_no_semantic_evidence():
    return build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), SESSION_CONTEXT, None)


def _fixture_4_elite_audio():
    return build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), SESSION_CONTEXT, ELITE_AUDIO_EVIDENCE)


def _fixture_5_non_elite_no_audio():
    return build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), SESSION_CONTEXT, NO_AUDIO_EVIDENCE)


def _fixture_6_mixed_provenance():
    unified = _unified(candidate_events=[
        CandidateEvent(event="jargon_used", turn_index=0, evidence_text="cannula", source=SOURCE_DETERMINISTIC),
        CandidateEvent(event="jargon_used", turn_index=0, evidence_text="cannula", source=SOURCE_SEMANTIC),
    ])
    return build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, ELITE_AUDIO_EVIDENCE)


def _fixture_7_multiple_concerns():
    unified = _unified(concern_outcomes=[
        ConcernOutcome(concern="Will I walk again?", final_status="raised", resolved=False, history=[]),
        ConcernOutcome(concern="Will there be a scar?", final_status="not_raised", resolved=False, history=[]),
    ])
    return build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, None)


def _fixture_8_hidden_info_candidate_history():
    unified = _unified(hidden_info_outcomes=[
        HiddenInfoOutcome(item="History of falls at home", candidate_detected=True, verification_status="verified_not_revealed", final_status="hidden"),
    ])
    return build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, unified, SESSION_CONTEXT, None)


def _fixture_9_minimal_scenario():
    return build_examiner_input({"title": "Untitled"}, [], _unified(), None, None)


def _fixture_10_missing_evidence_across_criteria():
    return build_examiner_input(BASE_SCENARIO, BASE_TRANSCRIPT, _unified(), None, None)


GOLDEN_FIXTURES = [
    _fixture_1_complete_clinical, _fixture_2_partial_clinical, _fixture_3_no_semantic_evidence,
    _fixture_4_elite_audio, _fixture_5_non_elite_no_audio, _fixture_6_mixed_provenance,
    _fixture_7_multiple_concerns, _fixture_8_hidden_info_candidate_history,
    _fixture_9_minimal_scenario, _fixture_10_missing_evidence_across_criteria,
]


@pytest.mark.parametrize("build_fixture", GOLDEN_FIXTURES)
def test_23_golden_fixtures_build_without_error_and_carry_no_score(build_fixture):
    result = build_fixture()
    assert len(result.criteria) == 9
    assert "score" not in result.model_dump()
