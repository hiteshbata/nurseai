"""Tests for the Shadow Examiner schema/prompt (Step 21K, Phase 1).

Pure schema/prompt tests only -- no model call, no ai_registry, no DB, no
network. See shadow_examiner.py's module docstring for scope.
"""
from __future__ import annotations

import ast
import inspect
import socket

import pytest
from pydantic import ValidationError

from app.services import shadow_examiner as se
from app.services.criterion_evidence import (
    ClinicalCriterionBundle,
    CriterionEvidenceMap,
    EvidenceRef,
    IndicatorEvidence,
    LinguisticCriterionBundle,
    LEVEL_L1_DIRECT,
    LEVEL_L2_DETERMINISTIC,
    LEVEL_L3_SEMANTIC,
    LEVEL_L4_PATIENT_OUTCOME,
    PROVENANCE_DIRECT,
)
from app.services.examiner_input import (
    ALL_CRITERIA,
    AudioAvailability,
    AVAILABILITY_INSUFFICIENT,
    AVAILABILITY_LIMITED,
    AVAILABILITY_PARTIAL,
    AVAILABILITY_STRONG,
    ClinicalEvidence,
    CLINICAL_CRITERIA,
    CRITERION_APPROPRIATENESS_OF_LANGUAGE,
    CRITERION_FLUENCY,
    CRITERION_INFORMATION_GATHERING,
    CRITERION_INFORMATION_GIVING,
    CRITERION_INTELLIGIBILITY,
    CRITERION_PATIENT_PERSPECTIVE,
    CRITERION_PROVIDING_STRUCTURE,
    CRITERION_RELATIONSHIP_BUILDING,
    CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION,
    EvidenceGap,
    ExaminerInput,
    INDICATORS_BY_CRITERION,
    LinguisticEvidence,
    LINGUISTIC_CRITERIA,
    ScenarioContext,
    SessionContext,
    TranscriptTurn,
)
from app.services.evidence_reconciliation import UnifiedEvidence
from app.services.speaking_evidence import InteractionMetrics, SOURCE_DETERMINISTIC, SOURCE_SEMANTIC


# ── Golden fixture: hand-written ExaminerInput + CriterionEvidenceMap ──────
# Schema fixture only -- no real OET scores assigned anywhere below.

def build_golden_examiner_input() -> ExaminerInput:
    transcript = [
        TranscriptTurn(role="nurse", content="Good morning, I'm Alex, one of the nurses here.", turn_index=0),
        TranscriptTurn(role="patient", content="Morning. I'm a bit worried about the surgery.", turn_index=1),
        TranscriptTurn(role="nurse", content="I understand this feels worrying -- what's on your mind?", turn_index=2),
        TranscriptTurn(role="patient", content="Will it hurt afterwards?", turn_index=3),
        TranscriptTurn(role="nurse", content="Let's talk through what to expect, then I'll check what you already know.", turn_index=4),
    ]
    return ExaminerInput(
        scenario_context=ScenarioContext(
            scenario_id=101, title="Pre-op anxiety", setting="Surgical ward",
            difficulty="medium", specialty="surgical", nurse_tasks=["reassure", "explain recovery"],
            patient_name="Jordan", patient_age=54, patient_condition="pre-operative",
            patient_mood="anxious", patient_background="first surgery", patient_concerns=["pain after surgery"],
            hidden_information_items=["family history of complications"], emotional_triggers=["mention of pain"],
        ),
        transcript=transcript,
        linguistic_evidence=LinguisticEvidence(pronunciation=None, accent_pattern_hints=[], jargon_evidence=[]),
        clinical_evidence=ClinicalEvidence(unified_evidence=UnifiedEvidence(
            candidate_events=[], patient_events=[], state_transitions=[], concern_outcomes=[],
            hidden_info_outcomes=[], jargon_evidence=[],
            interaction_metrics=InteractionMetrics(
                turn_counts={"total": 5, "nurse": 3, "patient": 2},
                jargon_events=0, empathy_events=0, concern_exploration_events=0,
                understanding_check_events=0, dismissive_events=0,
            ),
        )),
        session_context=SessionContext(
            pipeline="realtime", session_usage_id=555, duration_seconds=180.0,
            turn_count=5, nurse_turn_count=3, patient_turn_count=2, interrupted_count=0,
        ),
        audio_availability=AudioAvailability(
            audio_available=False, pronunciation_evidence_available=False, fluency_evidence_available=False,
        ),
        evidence_gaps=[
            EvidenceGap(criterion=CRITERION_INTELLIGIBILITY, reason_code="no_audio_evidence",
                        missing_evidence_type="acoustic_pronunciation_data", availability=AVAILABILITY_INSUFFICIENT),
        ],
    )


def _ref(source, evidence_id, level, provenance=PROVENANCE_DIRECT, turn_index=None, evidence_text="evidence"):
    return EvidenceRef(
        source=source, evidence_id=evidence_id, turn_index=turn_index,
        evidence_text=evidence_text, provenance=provenance, evidence_level=level,
    )


def build_golden_criterion_evidence_map() -> CriterionEvidenceMap:
    """All 9 criteria, all 20 indicators represented, mixed provenance, some
    evidence gaps, audio unavailable, multiple concerns, at least one
    semantic event, at least one patient-outcome event."""
    clinical_bundles = []
    for criterion in CLINICAL_CRITERIA:
        indicators = []
        for idx, indicator_id in enumerate(INDICATORS_BY_CRITERION[criterion]):
            if idx == 0:
                refs = [_ref("candidate_event", f"{indicator_id}_event", LEVEL_L2_DETERMINISTIC,
                             provenance=SOURCE_DETERMINISTIC, turn_index=2)]
                quality = AVAILABILITY_STRONG
            elif idx == 1:
                refs = [_ref("candidate_event", f"{indicator_id}_semantic_event", LEVEL_L3_SEMANTIC,
                             provenance=SOURCE_SEMANTIC, turn_index=3)]
                quality = AVAILABILITY_PARTIAL
            else:
                refs = []
                quality = AVAILABILITY_LIMITED
            indicators.append(IndicatorEvidence(indicator=indicator_id, evidence_refs=refs, evidence_quality=quality, gaps=[]))
        # one patient-outcome event on the criterion's first indicator's evidence
        indicators[0].evidence_refs.append(
            _ref("patient_event", "concern_resolution_signal", LEVEL_L4_PATIENT_OUTCOME,
                 provenance="direct", turn_index=3)
        )
        clinical_bundles.append(ClinicalCriterionBundle(
            criterion=criterion, indicators=indicators,
            criterion_evidence_quality=AVAILABILITY_PARTIAL,
        ))

    linguistic_bundles = [
        LinguisticCriterionBundle(
            criterion=CRITERION_INTELLIGIBILITY, evidence_refs=[], evidence_levels=[LEVEL_L1_DIRECT],
            audio_required=True, audio_available=False, evidence_quality=AVAILABILITY_INSUFFICIENT,
            gaps=[EvidenceGap(criterion=CRITERION_INTELLIGIBILITY, reason_code="no_audio_evidence",
                               missing_evidence_type="audio_intelligibility_evidence", availability=AVAILABILITY_INSUFFICIENT)],
        ),
        LinguisticCriterionBundle(
            criterion=CRITERION_FLUENCY, evidence_refs=[], evidence_levels=[LEVEL_L1_DIRECT],
            audio_required=True, audio_available=False, evidence_quality=AVAILABILITY_INSUFFICIENT,
            gaps=[EvidenceGap(criterion=CRITERION_FLUENCY, reason_code="no_audio_evidence",
                               missing_evidence_type="audio_fluency_evidence", availability=AVAILABILITY_INSUFFICIENT)],
        ),
        LinguisticCriterionBundle(
            criterion=CRITERION_APPROPRIATENESS_OF_LANGUAGE,
            evidence_refs=[_ref("transcript", "turn_0", LEVEL_L1_DIRECT, turn_index=0)],
            evidence_levels=[LEVEL_L1_DIRECT], audio_required=False, audio_available=False,
            evidence_quality=AVAILABILITY_PARTIAL,
            gaps=[EvidenceGap(criterion=CRITERION_APPROPRIATENESS_OF_LANGUAGE, reason_code="jargon_detector_partial_coverage",
                               missing_evidence_type="full_register_and_lexis_analysis", availability=AVAILABILITY_PARTIAL)],
        ),
        LinguisticCriterionBundle(
            criterion=CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION,
            evidence_refs=[_ref("transcript", "turn_2", LEVEL_L1_DIRECT, turn_index=2)],
            evidence_levels=[LEVEL_L1_DIRECT], audio_required=False, audio_available=False,
            evidence_quality=AVAILABILITY_PARTIAL,
            gaps=[EvidenceGap(criterion=CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, reason_code="no_grammar_detector",
                               missing_evidence_type="structured_grammar_analysis", availability=AVAILABILITY_PARTIAL)],
        ),
    ]

    return CriterionEvidenceMap(clinical=clinical_bundles, linguistic=linguistic_bundles)


# ── Golden fixture sanity ──────────────────────────────────────────────────

def test_golden_fixture_covers_all_9_criteria():
    cem = build_golden_criterion_evidence_map()
    criteria = {b.criterion for b in cem.clinical} | {b.criterion for b in cem.linguistic}
    assert criteria == set(ALL_CRITERIA)
    assert len(criteria) == 9


def test_golden_fixture_covers_all_20_indicators():
    cem = build_golden_criterion_evidence_map()
    indicator_ids = {ind.indicator for bundle in cem.clinical for ind in bundle.indicators}
    assert indicator_ids == set(se.ALL_INDICATOR_IDS)
    assert len(indicator_ids) == 20


def test_golden_fixture_has_evidence_gaps_and_mixed_provenance():
    cem = build_golden_criterion_evidence_map()
    provenances = {ref.provenance for bundle in cem.clinical for ind in bundle.indicators for ref in ind.evidence_refs}
    provenances |= {ref.provenance for bundle in cem.linguistic for ref in bundle.evidence_refs}
    assert SOURCE_DETERMINISTIC in provenances
    assert SOURCE_SEMANTIC in provenances
    any_gaps = any(bundle.gaps for bundle in cem.linguistic)
    assert any_gaps


def test_golden_fixture_audio_unavailable():
    ei = build_golden_examiner_input()
    assert ei.audio_availability.audio_available is False


# ── Indicator/criterion inventory ──────────────────────────────────────────

def test_20_indicators_not_19():
    assert len(se.ALL_INDICATOR_IDS) == 20


def test_9_criteria():
    assert len(ALL_CRITERIA) == 9
    assert len(LINGUISTIC_CRITERIA) == 4
    assert len(CLINICAL_CRITERIA) == 5


# ── Level validation ────────────────────────────────────────────────────────

def _judgement(**overrides):
    base = dict(
        criterion=CRITERION_RELATIONSHIP_BUILDING, family=se.FAMILY_CLINICAL,
        status=se.STATUS_ASSESSED, level=2, level_label="Competent use",
        justification="cites A1_event", evidence_refs=[], evidence_quality=AVAILABILITY_PARTIAL, limitations=[],
    )
    base.update(overrides)
    return se.CriterionJudgement(**base)


@pytest.mark.parametrize("level", [0, 1, 2, 3])
def test_clinical_level_0_to_3_valid(level):
    j = _judgement(level=level, level_label=se.CLINICAL_LEVEL_LABELS[level])
    assert j.level == level


@pytest.mark.parametrize("level", [-1, 4, 10])
def test_clinical_level_outside_range_rejected(level):
    with pytest.raises(ValidationError):
        _judgement(level=level, level_label=se.CLINICAL_LEVEL_LABELS.get(level, "Adept use"))


@pytest.mark.parametrize("level", [0, 1, 2, 3, 4, 5, 6])
def test_linguistic_level_0_to_6_valid(level):
    j = _judgement(criterion=CRITERION_FLUENCY, family=se.FAMILY_LINGUISTIC, level=level, level_label=None)
    assert j.level == level


@pytest.mark.parametrize("level", [-1, 7, 20])
def test_linguistic_level_outside_range_rejected(level):
    with pytest.raises(ValidationError):
        _judgement(criterion=CRITERION_FLUENCY, family=se.FAMILY_LINGUISTIC, level=level, level_label=None)


def test_clinical_label_inconsistent_with_level_rejected():
    with pytest.raises(ValidationError):
        _judgement(level=3, level_label="Ineffective use")


def test_linguistic_level_label_must_be_null():
    with pytest.raises(ValidationError):
        _judgement(criterion=CRITERION_FLUENCY, family=se.FAMILY_LINGUISTIC, level=4, level_label="Adept use")


# ── Criterion/family validation ────────────────────────────────────────────

def test_invalid_criterion_rejected():
    with pytest.raises(ValidationError):
        _judgement(criterion="not_a_real_criterion")


def test_family_inconsistent_with_criterion_rejected():
    with pytest.raises(ValidationError):
        _judgement(criterion=CRITERION_RELATIONSHIP_BUILDING, family=se.FAMILY_LINGUISTIC)


def test_invalid_status_rejected():
    with pytest.raises(ValidationError):
        _judgement(status="not_a_real_status")


# ── Status/level orthogonality ──────────────────────────────────────────────

def test_limited_evidence_with_level_none_valid():
    j = _judgement(status=se.STATUS_LIMITED_EVIDENCE, level=None, level_label=None)
    assert j.status == se.STATUS_LIMITED_EVIDENCE
    assert j.level is None


def test_assessed_with_valid_level_valid():
    j = _judgement(status=se.STATUS_ASSESSED, level=2, level_label="Competent use")
    assert j.status == se.STATUS_ASSESSED
    assert j.level == 2


def test_evidence_conflict_unresolved_with_level_none_valid():
    j = _judgement(status=se.STATUS_EVIDENCE_CONFLICT_UNRESOLVED, level=None, level_label=None)
    assert j.status == se.STATUS_EVIDENCE_CONFLICT_UNRESOLVED
    assert j.level is None


def test_limited_evidence_with_nonnull_level_rejected():
    with pytest.raises(ValidationError):
        _judgement(status=se.STATUS_LIMITED_EVIDENCE, level=0, level_label="Ineffective use")


def test_assessed_with_null_level_rejected():
    with pytest.raises(ValidationError):
        _judgement(status=se.STATUS_ASSESSED, level=None, level_label=None)


def test_missing_evidence_never_becomes_level_zero():
    """The task's core anti-pattern: a gap must produce limited_evidence, not
    a real level=0 (which is a legitimate 'Ineffective use' judgement)."""
    j = _judgement(status=se.STATUS_LIMITED_EVIDENCE, level=None, level_label=None,
                    limitations=["no_indicator_level_detector"])
    assert j.level is None
    assert j.status != se.STATUS_ASSESSED


# ── Evidence pointer ─────────────────────────────────────────────────────

def test_evidence_pointer_serialization():
    ptr = se.EvidenceRefPointer(evidence_id="empathy_acknowledgement", turn_index=4,
                                 evidence_level=LEVEL_L2_DETERMINISTIC, source="candidate_event",
                                 provenance=SOURCE_DETERMINISTIC)
    dumped = ptr.model_dump()
    assert dumped["evidence_id"] == "empathy_acknowledgement"
    assert dumped["evidence_level"] == LEVEL_L2_DETERMINISTIC
    restored = se.EvidenceRefPointer(**dumped)
    assert restored == ptr


def test_evidence_pointer_invalid_level_rejected():
    with pytest.raises(ValidationError):
        se.EvidenceRefPointer(evidence_id="x", evidence_level="L9_not_real", source="candidate_event")


def test_evidence_pointer_missing_evidence_id_rejected():
    with pytest.raises(ValidationError):
        se.EvidenceRefPointer(evidence_level=LEVEL_L1_DIRECT, source="transcript")


# ── ShadowResult: 9-criteria coverage ──────────────────────────────────────

def _all_nine_judgements():
    judgements = []
    for c in LINGUISTIC_CRITERIA:
        judgements.append(_judgement(criterion=c, family=se.FAMILY_LINGUISTIC, level=3, level_label=None))
    for c in CLINICAL_CRITERIA:
        judgements.append(_judgement(criterion=c, family=se.FAMILY_CLINICAL, level=2, level_label="Competent use"))
    return judgements


def _metadata(**overrides):
    base = dict(model="stub", prompt_version=se.PROMPT_VERSION, generated_at="2026-08-29T00:00:00Z",
                criteria_unavailable=[], evidence_complete=True)
    base.update(overrides)
    return se.EvaluationMetadata(**base)


def test_shadow_result_complete_9_criteria_valid():
    result = se.ShadowResult(
        session_ref=se.SessionRef(pipeline="realtime", session_usage_id=1),
        criteria=_all_nine_judgements(), evaluation_metadata=_metadata(),
    )
    assert len(result.criteria) == 9


def test_shadow_result_missing_criterion_rejected():
    judgements = _all_nine_judgements()[:-1]
    with pytest.raises(ValidationError):
        se.ShadowResult(session_ref=se.SessionRef(), criteria=judgements, evaluation_metadata=_metadata())


def test_shadow_result_duplicate_criterion_rejected():
    judgements = _all_nine_judgements()[:-1]
    judgements.append(judgements[0])
    with pytest.raises(ValidationError):
        se.ShadowResult(session_ref=se.SessionRef(), criteria=judgements, evaluation_metadata=_metadata())


def test_shadow_result_serialization_round_trip():
    result = se.ShadowResult(
        session_ref=se.SessionRef(pipeline="legacy", session_usage_id=42),
        criteria=_all_nine_judgements(), evaluation_metadata=_metadata(),
    )
    dumped = result.model_dump(mode="json")
    restored = se.ShadowResult(**dumped)
    assert restored == result


def test_shadow_result_has_no_overall_score_field():
    result = se.ShadowResult(
        session_ref=se.SessionRef(), criteria=_all_nine_judgements(), evaluation_metadata=_metadata(),
    )
    dumped = result.model_dump()
    assert "overall" not in dumped
    assert "overall_band" not in dumped
    assert "score" not in dumped


# ── Family-specific validation / assembly ──────────────────────────────────

def test_validate_family_judgements_linguistic_ok():
    judgements = [_judgement(criterion=c, family=se.FAMILY_LINGUISTIC, level=3, level_label=None) for c in LINGUISTIC_CRITERIA]
    se.validate_family_judgements(se.FAMILY_LINGUISTIC, judgements)


def test_validate_family_judgements_wrong_family_rejected():
    judgements = [_judgement(criterion=c, family=se.FAMILY_LINGUISTIC, level=3, level_label=None) for c in LINGUISTIC_CRITERIA]
    with pytest.raises(ValueError):
        se.validate_family_judgements(se.FAMILY_CLINICAL, judgements)


def test_validate_family_judgements_incomplete_rejected():
    judgements = [_judgement(criterion=c, family=se.FAMILY_LINGUISTIC, level=3, level_label=None) for c in LINGUISTIC_CRITERIA[:-1]]
    with pytest.raises(ValueError):
        se.validate_family_judgements(se.FAMILY_LINGUISTIC, judgements)


def test_build_shadow_result_from_family_batches():
    linguistic = [_judgement(criterion=c, family=se.FAMILY_LINGUISTIC, level=3, level_label=None) for c in LINGUISTIC_CRITERIA]
    clinical = [_judgement(criterion=c, family=se.FAMILY_CLINICAL, level=2, level_label="Competent use") for c in CLINICAL_CRITERIA]
    result = se.build_shadow_result(se.SessionRef(session_usage_id=9), linguistic, clinical, _metadata())
    assert len(result.criteria) == 9


# ── Incomplete / audio-unavailable / conflicting fixtures ──────────────────

def test_incomplete_criterion_fixture_rejected_by_shadow_result():
    """8 valid judgements, one clinical criterion entirely absent."""
    judgements = _all_nine_judgements()
    incomplete = [j for j in judgements if j.criterion != CRITERION_INFORMATION_GIVING]
    with pytest.raises(ValidationError):
        se.ShadowResult(session_ref=se.SessionRef(), criteria=incomplete, evaluation_metadata=_metadata())


def test_audio_unavailable_fixture_yields_limited_evidence():
    j = _judgement(criterion=CRITERION_INTELLIGIBILITY, family=se.FAMILY_LINGUISTIC,
                    status=se.STATUS_LIMITED_EVIDENCE, level=None, level_label=None,
                    limitations=["no_audio_evidence"])
    assert j.level is None
    assert j.status == se.STATUS_LIMITED_EVIDENCE


def test_conflicting_evidence_fixture_yields_conflict_status():
    j = _judgement(criterion=CRITERION_PATIENT_PERSPECTIVE, family=se.FAMILY_CLINICAL,
                    status=se.STATUS_EVIDENCE_CONFLICT_UNRESOLVED, level=None, level_label=None,
                    justification="deterministic and semantic evidence on turn 3 conflict with no direct arbiter",
                    limitations=[])
    assert j.status == se.STATUS_EVIDENCE_CONFLICT_UNRESOLVED
    assert j.level is None


# ── Prompt structure ─────────────────────────────────────────────────────

def test_prompt_version_exists_and_is_a_real_string():
    assert isinstance(se.PROMPT_VERSION, str)
    assert len(se.PROMPT_VERSION) > 0
    assert se.PROMPT_VERSION != ""


def test_prompt_contains_anti_hallucination_rules():
    for family in (se.FAMILY_LINGUISTIC, se.FAMILY_CLINICAL):
        system = se.build_system_prompt(family)
        assert "never invent" in system.lower()


def test_prompt_contains_missing_vs_negative_rule():
    for family in (se.FAMILY_LINGUISTIC, se.FAMILY_CLINICAL):
        system = se.build_system_prompt(family)
        assert "missing evidence" in system.lower()
        assert "must never" in system.lower()


def test_prompt_contains_audio_limitation_rule():
    system = se.build_system_prompt(se.FAMILY_LINGUISTIC)
    assert "audio" in system.lower()
    assert "must not infer" in system.lower()


def test_prompt_says_indicators_not_independent_scores():
    system = se.build_system_prompt(se.FAMILY_CLINICAL)
    assert "never independent scores" in system.lower() or "not independent scores" in system.lower()


def test_prompt_says_no_overall_weighting():
    for family in (se.FAMILY_LINGUISTIC, se.FAMILY_CLINICAL):
        system = se.build_system_prompt(family)
        assert "overall" in system.lower()
        assert "0.6/0.4" in system


def test_prompt_output_schema_instructions_present():
    system = se.build_system_prompt(se.FAMILY_CLINICAL)
    assert "criterion" in system and "evidence_refs" in system and "level_label" in system


def test_build_system_prompt_invalid_family_rejected():
    with pytest.raises(ValueError):
        se.build_system_prompt("not_a_family")


def test_build_user_prompt_contains_evidence_json():
    ei = build_golden_examiner_input()
    cem = build_golden_criterion_evidence_map()
    user = se.build_user_prompt(se.FAMILY_CLINICAL, ei, cem)
    assert "clinical_criteria" in user
    assert "relationship_building" in user


def test_build_shadow_examiner_prompt_end_to_end():
    ei = build_golden_examiner_input()
    cem = build_golden_criterion_evidence_map()
    prompt = se.build_shadow_examiner_prompt(se.FAMILY_LINGUISTIC, ei, cem)
    assert prompt.family == se.FAMILY_LINGUISTIC
    assert prompt.prompt_version == se.PROMPT_VERSION
    assert len(prompt.system) > 0
    assert len(prompt.user) > 0


# ── No model call / no forbidden dependency ─────────────────────────────────

def test_no_network_calls_building_prompts():
    ei = build_golden_examiner_input()
    cem = build_golden_criterion_evidence_map()

    def _blocked(*args, **kwargs):
        raise AssertionError("shadow_examiner attempted a network call")

    original = socket.socket
    socket.socket = _blocked
    try:
        se.build_shadow_examiner_prompt(se.FAMILY_LINGUISTIC, ei, cem)
        se.build_shadow_examiner_prompt(se.FAMILY_CLINICAL, ei, cem)
        se.CriterionJudgement(
            criterion=CRITERION_RELATIONSHIP_BUILDING, family=se.FAMILY_CLINICAL, status=se.STATUS_ASSESSED,
            level=2, level_label="Competent use", justification="x", evidence_refs=[],
            evidence_quality=AVAILABILITY_PARTIAL, limitations=[],
        )
    finally:
        socket.socket = original


def _imported_names() -> set:
    """Every name this module imports, via AST (ignores docstrings/comments --
    those may legitimately name the boundary this module respects)."""
    tree = ast.parse(inspect.getsource(se))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            names.update(alias.name for alias in node.names)
    return names


def test_module_has_no_ai_registry_dependency():
    assert not hasattr(se, "ai_registry")
    assert not any("ai_registry" in n for n in _imported_names())


def test_module_has_no_score_speaking_dependency():
    assert not hasattr(se, "score_speaking")
    assert not hasattr(se, "ai_scoring")
    assert not any(n in ("ai_scoring", "score_speaking") for n in _imported_names())


def test_module_makes_no_provider_sdk_calls():
    source = inspect.getsource(se)
    for forbidden in ("openai", "anthropic", "genai", "requests.post", "httpx.", "google.generativeai"):
        assert forbidden not in source.lower()


# ── Deterministic round-trip ─────────────────────────────────────────────

def test_deterministic_schema_round_trip():
    ei = build_golden_examiner_input()
    cem = build_golden_criterion_evidence_map()
    p1 = se.build_shadow_examiner_prompt(se.FAMILY_CLINICAL, ei, cem)
    p2 = se.build_shadow_examiner_prompt(se.FAMILY_CLINICAL, ei, cem)
    assert p1 == p2
