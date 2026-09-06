"""Tests for the Phase 3 live-experiment harness (app.services.
shadow_examiner_experiment).

All model calls are mocked here -- this file makes zero real network calls
and zero real model calls. The single real clinical-family call is made only
by scripts/phase3_shadow_examiner_clinical_experiment.py, run once by hand
against QA (see the Phase 3 report), never by the test suite.
"""
from __future__ import annotations

import json
import socket

import pytest

from app.core import env_guard
from app.services import shadow_examiner as se
from app.services import shadow_examiner_experiment as harness
from app.services.criterion_evidence import (
    ClinicalCriterionBundle,
    CriterionEvidenceMap,
    EvidenceRef,
    IndicatorEvidence,
    LEVEL_L2_DETERMINISTIC,
)
from app.services.examiner_input import (
    AVAILABILITY_PARTIAL,
    CRITERION_INFORMATION_GATHERING,
    CRITERION_INFORMATION_GIVING,
    CRITERION_PATIENT_PERSPECTIVE,
    CRITERION_PROVIDING_STRUCTURE,
    CRITERION_RELATIONSHIP_BUILDING,
)
from app.services.speaking_evidence import SOURCE_DETERMINISTIC


def _ref(evidence_id, turn_index):
    return EvidenceRef(
        source="candidate_event", evidence_id=evidence_id, turn_index=turn_index,
        evidence_text="text", provenance=SOURCE_DETERMINISTIC, evidence_level=LEVEL_L2_DETERMINISTIC,
    )


def _one_indicator_bundle(criterion, evidence_id, turn_index):
    return ClinicalCriterionBundle(
        criterion=criterion, criterion_evidence_quality=AVAILABILITY_PARTIAL,
        indicators=[IndicatorEvidence(indicator="X1", evidence_quality=AVAILABILITY_PARTIAL, evidence_refs=[_ref(evidence_id, turn_index)])],
    )


def _map() -> CriterionEvidenceMap:
    return CriterionEvidenceMap(linguistic=[], clinical=[
        _one_indicator_bundle(CRITERION_RELATIONSHIP_BUILDING, "A1_event", 2),
        _one_indicator_bundle(CRITERION_PATIENT_PERSPECTIVE, "B1_event", 3),
        _one_indicator_bundle(CRITERION_PROVIDING_STRUCTURE, "C1_event", 1),
        _one_indicator_bundle(CRITERION_INFORMATION_GATHERING, "D1_event", 4),
        _one_indicator_bundle(CRITERION_INFORMATION_GIVING, "E1_event", 3),
    ])


def _item(criterion, evidence_id=None, turn_index=None):
    return {
        "criterion": criterion, "family": se.FAMILY_CLINICAL, "status": se.STATUS_ASSESSED,
        "level": 2, "level_label": "Competent use", "justification": "cites evidence",
        "evidence_refs": [{
            "evidence_id": evidence_id, "turn_index": turn_index,
            "evidence_level": LEVEL_L2_DETERMINISTIC, "source": "candidate_event", "provenance": SOURCE_DETERMINISTIC,
        }] if evidence_id else [],
        "evidence_quality": AVAILABILITY_PARTIAL, "limitations": [],
    }


def _valid_clinical_response_json() -> str:
    return json.dumps([
        _item(CRITERION_RELATIONSHIP_BUILDING, "A1_event", 2),
        _item(CRITERION_PATIENT_PERSPECTIVE, "B1_event", 3),
        _item(CRITERION_PROVIDING_STRUCTURE, "C1_event", 1),
        _item(CRITERION_INFORMATION_GATHERING, "D1_event", 4),
        _item(CRITERION_INFORMATION_GIVING, "E1_event", 3),
    ])


# ── QA-only guard ────────────────────────────────────────────────────────

def test_verify_qa_environment_accepts_qa_with_non_prod_url():
    harness.verify_qa_environment("qa", "https://qaref1234567890123.supabase.co", "prodref123456789")


def test_verify_qa_environment_rejects_production():
    with pytest.raises(harness.EnvironmentSafetyError):
        harness.verify_qa_environment("production", "https://prodref123456789.supabase.co", "prodref123456789")


def test_verify_qa_environment_rejects_development():
    with pytest.raises(harness.EnvironmentSafetyError):
        harness.verify_qa_environment("development", "https://devref123456789012.supabase.co", "prodref123456789")


def test_verify_qa_environment_rejects_qa_pointed_at_production_supabase():
    with pytest.raises(harness.EnvironmentSafetyError):
        harness.verify_qa_environment("qa", "https://prodref123456789.supabase.co", "prodref123456789")


def test_verify_qa_environment_rejects_non_supabase_url():
    with pytest.raises(harness.EnvironmentSafetyError):
        harness.verify_qa_environment("qa", "not-a-url", "prodref123456789")


# ── build_clinical_prompt: Phase 1 pass-through ─────────────────────────

from app.services.evidence_reconciliation import UnifiedEvidence  # noqa: E402
from app.services.speaking_evidence import InteractionMetrics  # noqa: E402
from app.services.examiner_input import (  # noqa: E402
    AudioAvailability, ClinicalEvidence, ExaminerInput, LinguisticEvidence, ScenarioContext, SessionContext,
)


def _minimal_examiner_input() -> ExaminerInput:
    unified = UnifiedEvidence(
        candidate_events=[], patient_events=[], concern_outcomes=[], hidden_info_outcomes=[],
        state_transitions=[], jargon_evidence=[],
        interaction_metrics=InteractionMetrics(
            turn_counts={"total": 0, "nurse": 0, "patient": 0}, jargon_events=0, empathy_events=0,
            concern_exploration_events=0, understanding_check_events=0, dismissive_events=0,
        ),
    )
    return ExaminerInput(
        scenario_context=ScenarioContext(), transcript=[], linguistic_evidence=LinguisticEvidence(),
        clinical_evidence=ClinicalEvidence(unified_evidence=unified), session_context=SessionContext(),
        audio_availability=AudioAvailability(audio_available=False, pronunciation_evidence_available=False, fluency_evidence_available=False),
        evidence_gaps=[],
    )


def test_build_clinical_prompt_covers_clinical_family_only():
    prompt = harness.build_clinical_prompt(_minimal_examiner_input(), _map())
    assert prompt.family == se.FAMILY_CLINICAL
    for criterion in se.CLINICAL_CRITERIA:
        assert criterion in prompt.system  # se.build_system_prompt's clinical addendum names each criterion
    assert "clinical" in prompt.user.lower()


# ── run_one_clinical_call: exactly one call, no retry ───────────────────
# Plain asyncio.run() style (no pytest-asyncio dependency in this project --
# same convention as test_realtime_gemini_adapter.py / test_realtime_openai_adapter.py).

import asyncio  # noqa: E402


def test_run_one_clinical_call_calls_dispatch_exactly_once_on_success():
    calls = []

    async def fake_dispatch(system, user):
        calls.append((system, user))
        return {"text": _valid_clinical_response_json(), "usage": {"input_tokens": 100, "output_tokens": 50}, "finish_reason": "stop"}

    result = asyncio.run(harness.run_one_clinical_call("SYS", "USR", fake_dispatch))
    assert len(calls) == 1
    assert result.call_count == 1
    assert result.success is True
    assert result.input_tokens == 100 and result.output_tokens == 50


def test_run_one_clinical_call_does_not_retry_on_failure():
    calls = []

    async def failing_dispatch(system, user):
        calls.append(1)
        raise RuntimeError("simulated provider failure (e.g. quota exceeded)")

    result = asyncio.run(harness.run_one_clinical_call("SYS", "USR", failing_dispatch))
    assert len(calls) == 1, "harness must not retry automatically, even on failure"
    assert result.call_count == 1
    assert result.success is False
    assert result.raw_text is None
    assert "simulated provider failure" in result.error


# ── evaluate_clinical_response: valid / invalid / evidence-ref rejection ──

def test_evaluate_clinical_response_valid_yields_5_judgements_no_fallback():
    outcome = harness.evaluate_clinical_response(_valid_clinical_response_json(), _map())
    assert outcome.validation_valid is True
    assert outcome.used_fallback is False
    assert len(outcome.judgements) == 5
    assert {j.criterion for j in outcome.judgements} == set(se.CLINICAL_CRITERIA)


def test_evaluate_clinical_response_malformed_json_yields_safe_fallback():
    outcome = harness.evaluate_clinical_response("not json at all {{{", _map())
    assert outcome.validation_valid is False
    assert outcome.used_fallback is True
    assert len(outcome.judgements) == 5
    assert all(j.status == se.STATUS_LIMITED_EVIDENCE and j.level is None for j in outcome.judgements)


def test_evaluate_clinical_response_none_text_yields_safe_fallback():
    outcome = harness.evaluate_clinical_response(None, _map())
    assert outcome.used_fallback is True
    assert len(outcome.judgements) == 5


def test_evaluate_clinical_response_fabricated_evidence_ref_rejected_to_fallback():
    items = json.loads(_valid_clinical_response_json())
    items[0]["evidence_refs"] = [{
        "evidence_id": "totally_made_up_event", "turn_index": 999,
        "evidence_level": LEVEL_L2_DETERMINISTIC, "source": "candidate_event", "provenance": SOURCE_DETERMINISTIC,
    }]
    outcome = harness.evaluate_clinical_response(json.dumps(items), _map())
    assert outcome.validation_valid is False
    assert outcome.used_fallback is True
    assert outcome.evidence_reference_errors  # non-empty: names the fabricated citation
    assert all(j.status == se.STATUS_LIMITED_EVIDENCE and j.level is None for j in outcome.judgements)


def test_evaluate_clinical_response_never_produces_a_zero_score_on_failure():
    outcome = harness.evaluate_clinical_response("garbage", _map())
    assert all(j.level is None for j in outcome.judgements), "missing/invalid evidence must never become level=0"


# ── structural safety: no score/DB/Learning Brain import anywhere in this module ──

def test_harness_module_has_no_score_speaking_or_db_import():
    import app.services.shadow_examiner_experiment as mod
    lines = open(mod.__file__, encoding="utf-8").read().splitlines()
    import_lines = [ln for ln in lines if ln.strip().startswith(("import ", "from "))]
    assert not any("ai_registry" in ln for ln in import_lines), "harness must not import a live provider client; caller supplies `dispatch`"
    assert not any("supabase" in ln.lower() for ln in import_lines)
    assert not any("ai_scoring" in ln for ln in import_lines)


def test_harness_module_has_no_learning_brain_import():
    import app.services.shadow_examiner_experiment as mod
    lines = open(mod.__file__, encoding="utf-8").read().splitlines()
    import_lines = [ln for ln in lines if ln.strip().startswith(("import ", "from "))]
    for forbidden in ("skill_graph", "progress", "learner_brain"):
        assert not any(forbidden in ln for ln in import_lines)


def test_no_network_calls_in_evaluate_and_prompt_building():
    def _blocked(*args, **kwargs):
        raise AssertionError("shadow_examiner_experiment attempted a network call")

    original = socket.socket
    socket.socket = _blocked
    try:
        harness.build_clinical_prompt(_minimal_examiner_input(), _map())
        harness.evaluate_clinical_response(_valid_clinical_response_json(), _map())
        harness.evaluate_clinical_response(None, _map())
    finally:
        socket.socket = original
