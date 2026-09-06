"""Shadow OET Examiner -- Phase 3 live-experiment harness (pure orchestration).

Thin, testable orchestration around the Phase 1 (shadow_examiner) and Phase 2
(shadow_examiner_validation) pure functions, plus exactly one real model
call made through a caller-supplied `dispatch` callable. This module makes
no network call and no DB call itself -- it has no dependency on ai_registry,
httpx, or app.core.supabase, so it is importable and fully testable with a
mocked `dispatch` and zero real I/O. The QA-only live script
(scripts/phase3_shadow_examiner_clinical_experiment.py) wires a real
ai_registry.dispatch_call in as `dispatch`; tests wire in a fake.

SAFETY (verified by this module's own tests, not just by convention): this
module never imports app.services.ai_scoring.score_speaking, never imports
anything under app.services.progress/skill_graph (the Learning Brain), and
never imports app.core.supabase -- so it is structurally incapable of
scoring a student or writing to the database, independent of what any
individual function here does at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

from app.core import env_guard
from app.services import shadow_examiner as se
from app.services import shadow_examiner_validation as sev
from app.services.criterion_evidence import CriterionEvidenceMap
from app.services.examiner_input import ExaminerInput


class EnvironmentSafetyError(RuntimeError):
    """Raised when this experiment is about to run outside QA, or QA looks
    misconfigured to point at the production Supabase project."""


def verify_qa_environment(environment: str, supabase_url: str, production_project_ref: str) -> None:
    """Fail-closed guard, QA-only. Raises EnvironmentSafetyError for any
    non-'qa' ENVIRONMENT (so this harness can never accidentally run against
    a production or unlabeled deployment), then delegates to the codebase's
    existing app.core.env_guard.verify_production_isolation for the
    "QA pointed at the production Supabase project" check."""
    if (environment or "").strip().lower() != "qa":
        raise EnvironmentSafetyError(f"This experiment is QA-only; got ENVIRONMENT={environment!r}")
    if not env_guard.project_ref(supabase_url):
        raise EnvironmentSafetyError("SUPABASE_URL does not look like a *.supabase.co project URL")
    try:
        env_guard.verify_production_isolation(environment, supabase_url, production_project_ref)
    except env_guard.ProductionIsolationError as e:
        raise EnvironmentSafetyError(str(e)) from e


@dataclass
class ModelCallResult:
    raw_text: Optional[str]
    input_tokens: int
    output_tokens: int
    finish_reason: Optional[str]
    latency_ms: int
    success: bool
    error: Optional[str]
    call_count: int = 1  # always exactly 1 -- see run_one_clinical_call


# (system_prompt, user_prompt) -> {"text": str, "usage": {"input_tokens", "output_tokens"}, "finish_reason": str|None}
DispatchFn = Callable[[str, str], Awaitable[dict]]


async def run_one_clinical_call(system_prompt: str, user_prompt: str, dispatch: DispatchFn) -> ModelCallResult:
    """Calls `dispatch` EXACTLY ONCE. No loop, no retry, no fallback-model
    logic lives in this function -- unlike app.services.ai_scoring._call_ai's
    own single-hop-fallback behavior, which is a separate, already-existing
    abstraction this function deliberately does not reach for for the
    Shadow Examiner call itself (see design doc: "make exactly one call").
    A `dispatch` failure is reported, not retried."""
    import time

    start = time.monotonic()
    try:
        dispatched = await dispatch(system_prompt, user_prompt)
    except Exception as e:
        return ModelCallResult(
            raw_text=None, input_tokens=0, output_tokens=0, finish_reason=None,
            latency_ms=round((time.monotonic() - start) * 1000), success=False, error=str(e)[:300],
        )
    usage = dispatched.get("usage") or {}
    return ModelCallResult(
        raw_text=dispatched.get("text"), input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0), finish_reason=dispatched.get("finish_reason"),
        latency_ms=round((time.monotonic() - start) * 1000), success=True, error=None,
    )


@dataclass
class ClinicalEvaluationOutcome:
    judgements: List[se.CriterionJudgement]
    validation_valid: bool
    validation_errors: List[str] = field(default_factory=list)
    evidence_reference_errors: List[str] = field(default_factory=list)
    used_fallback: bool = False


def evaluate_clinical_response(
    raw_text: Optional[str], criterion_evidence_map: CriterionEvidenceMap,
) -> ClinicalEvaluationOutcome:
    """Phase 2 schema validation, THEN the Phase 3 evidence-reference
    cross-check (shadow_examiner_validation.validate_evidence_references) --
    see that function's docstring for why Phase 2 alone isn't enough. No
    partial trust either way, matching Phase 2's own rule: a schema failure
    OR any fabricated/misattributed evidence reference invalidates the
    WHOLE family batch and produces a safe fallback (status=limited_evidence,
    level=None for all 5 clinical criteria) -- never a partial patch of just
    the offending judgement, and never a score of 0."""
    validation = sev.validate_family_response(se.FAMILY_CLINICAL, raw_text)
    if not validation.valid:
        return ClinicalEvaluationOutcome(
            judgements=sev.safe_fallback_judgements(se.FAMILY_CLINICAL),
            validation_valid=False, validation_errors=validation.errors, used_fallback=True,
        )

    evidence_errors = sev.validate_evidence_references(se.FAMILY_CLINICAL, validation.judgements, criterion_evidence_map)
    if evidence_errors:
        return ClinicalEvaluationOutcome(
            judgements=sev.safe_fallback_judgements(se.FAMILY_CLINICAL),
            validation_valid=False, evidence_reference_errors=evidence_errors, used_fallback=True,
        )

    return ClinicalEvaluationOutcome(judgements=validation.judgements, validation_valid=True)


def build_clinical_prompt(examiner_input: ExaminerInput, criterion_evidence_map: CriterionEvidenceMap) -> se.ShadowExaminerPrompt:
    """Thin pass-through to the Phase 1 API -- exists so callers only ever
    import this harness module, never reach past it into shadow_examiner
    directly (keeps "which prompt builder is authoritative" unambiguous)."""
    return se.build_shadow_examiner_prompt(se.FAMILY_CLINICAL, examiner_input, criterion_evidence_map)
