"""Shadow OET Examiner -- Phase 3: FIRST real clinical-family live call.

Live Clinical Shadow Examiner QA Experiment. Runs exactly ONE real model call
against the clinical family (5 criteria) using the existing, unmodified
Phase 1 (app.services.shadow_examiner) and Phase 2 (app.services.
shadow_examiner_validation) pipelines, orchestrated through the pure,
independently-tested app.services.shadow_examiner_experiment harness. QA
only (ENVIRONMENT=qa, fail-closed against production -- see
app.core.env_guard / shadow_examiner_experiment.verify_qa_environment).

SAFETY: this script never calls score_speaking(), never writes to
submissions/session_usage/session_semantic_state, never touches the Learning
Brain, and never persists ShadowResult anywhere. The only DB writes are (a) a
one-time, idempotent QA-only ai_model_purposes row for
"shadow_examiner_clinical" (config, not session data -- user-approved, see
Phase 3 report) and (b) the standard ai_usage_events cost-ledger row that
every real model call already produces (same as every other purpose in this
codebase).

Usage:
    cd backend
    python scripts/phase3_shadow_examiner_clinical_experiment.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "qa")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core import env_guard  # noqa: E402
from app.core import cost_circuit_breaker  # noqa: E402
from app.core.supabase import get_supabase  # noqa: E402
from app.core import ai_pricing  # noqa: E402
from app.services import ai_registry  # noqa: E402
from app.services import cost_tracking  # noqa: E402
from app.services import session_semantic_state  # noqa: E402
from app.services import shadow_examiner as se  # noqa: E402
from app.services import shadow_examiner_experiment as harness  # noqa: E402
from app.services.examiner_input import build_examiner_input  # noqa: E402
from app.services.criterion_evidence import map_criterion_evidence  # noqa: E402
from app.services.evidence_reconciliation import reconcile_evidence  # noqa: E402
from app.services.speaking_evidence import build_speaking_evidence_with_semantics  # noqa: E402

PURPOSE = "shadow_examiner_clinical"
SESSION_USAGE_ID = 10  # only realtime QA session with a real multi-turn clinical transcript
SCENARIO_ID = 16  # "Initiating Insulin Therapy in Type 2 Diabetes" (Marcus Vance)
EXPERIMENT_USER_TAG = "00000000-0000-4000-8000-000000000003"  # fixed UUID tag: "phase 3" experiment, filterable in ai_usage_events
MAX_TOKENS = 4000


# ── 1. purpose configuration (user-approved: Gemini 3.5 Flash, id=3, QA only) ──

def ensure_purpose_configured() -> None:
    supabase = get_supabase()
    existing = supabase.table("ai_model_purposes").select("*").eq("purpose", PURPOSE).execute().data
    if existing:
        print(f"[PURPOSE] {PURPOSE!r} already configured: model_id={existing[0]['model_id']}")
        return
    supabase.table("ai_model_purposes").insert({"purpose": PURPOSE, "model_id": 3}).execute()
    ai_registry.invalidate_cache(PURPOSE)
    print(f"[PURPOSE] inserted QA-only row: {PURPOSE!r} -> model_id=3 (gemini-3.5-flash, native google)")


# ── 2. session selection (read-only) ────────────────────────────────────

def load_session_10():
    supabase = get_supabase()
    rows = supabase.table("session_transcripts").select("*").eq("session_usage_id", SESSION_USAGE_ID).order("created_at").execute().data
    history = []
    for row in rows:
        for turn in row.get("transcript") or []:
            history.append({"role": turn.get("role", ""), "content": turn.get("text", "")})

    metrics_rows = supabase.table("realtime_session_metrics").select("*").eq("session_usage_id", SESSION_USAGE_ID).execute().data
    duration_seconds = sum(m["duration_seconds"] for m in metrics_rows if m.get("duration_seconds") is not None) or None
    interrupted_count = metrics_rows[0].get("interrupted_count") if metrics_rows else None

    scenario = supabase.table("scenarios").select("*").eq("id", SCENARIO_ID).execute().data[0]
    return history, scenario, duration_seconds, interrupted_count


# ── main experiment ─────────────────────────────────────────────────────

async def main():
    print("=" * 70)
    print("PLAN")
    print("=" * 70)
    print(f"  QA session: pipeline=realtime session_usage_id={SESSION_USAGE_ID} scenario_id={SCENARIO_ID}")
    print(f"  Model purpose: {PURPOSE!r}")
    print("  Family: clinical only (5 criteria)")
    print("  Model calls planned: exactly 1 (clinical family)")
    print("  Persistence: none (no ShadowResult DB write, no score write)")
    print()

    harness.verify_qa_environment(settings.ENVIRONMENT, settings.SUPABASE_URL, settings.PRODUCTION_SUPABASE_PROJECT_REF)
    print(f"[ENV OK] ENVIRONMENT=qa  qa_project_ref={env_guard.project_ref(settings.SUPABASE_URL)}  "
          "(production_ref differs, isolation guard passed)")

    ensure_purpose_configured()

    cfg = await ai_registry.get_model_config(PURPOSE)
    print(f"[MODEL] purpose={PURPOSE!r} -> provider={cfg.provider} model={cfg.model_name}")

    history, scenario, duration_seconds, interrupted_count = load_session_10()
    print(f"[SESSION] turns={len(history)} scenario_title={scenario.get('title')!r}")

    # ── build ExaminerInput + CriterionEvidenceMap (existing Step 19/20 pure functions) ──
    # Read-only lookup (verified empty for session 10 -- no session_semantic_state row exists yet).
    prior_hints = await session_semantic_state.load_semantic_state(SESSION_USAGE_ID)
    speaking_evidence = await build_speaking_evidence_with_semantics(
        scenario.get("interlocutor_card"), history,
        user_id=EXPERIMENT_USER_TAG, session_id=None, prior=prior_hints,
    )
    unified_evidence = reconcile_evidence(speaking_evidence)

    examiner_input = build_examiner_input(
        scenario, history, unified_evidence,
        session_context={
            "pipeline": "realtime", "session_usage_id": SESSION_USAGE_ID,
            "duration_seconds": duration_seconds, "interrupted_count": interrupted_count,
        },
        audio_evidence=None,  # clinical-family-only experiment; audio is secondary per spec
    )
    criterion_evidence_map = map_criterion_evidence(examiner_input)

    # ── critical check: compact audit summary before the model call ────
    print("\n" + "=" * 70)
    print("CRITICAL CHECK -- audit summary before model call")
    print("=" * 70)
    print(f"  clinical criteria = {len(se.CLINICAL_CRITERIA)}")
    print(f"  indicators (framework total) = {len(se.ALL_INDICATOR_IDS)} : {se.ALL_INDICATOR_IDS}")
    print(f"  audio_availability.audio_available = {examiner_input.audio_availability.audio_available}")
    semantic_refs_present = False
    for bundle in criterion_evidence_map.clinical:
        n_refs = sum(len(ind.evidence_refs) for ind in bundle.indicators)
        levels = sorted({r.evidence_level for ind in bundle.indicators for r in ind.evidence_refs})
        if se.LEVEL_L3_SEMANTIC in levels:
            semantic_refs_present = True
        print(f"  {bundle.criterion}: evidence_refs={n_refs} quality={bundle.criterion_evidence_quality} evidence_levels={levels}")
    print(f"  semantic provenance present anywhere = {semantic_refs_present}")

    # ── build prompt (Phase 1 API, via the harness pass-through) ────────
    prompt = harness.build_clinical_prompt(examiner_input, criterion_evidence_map)

    # ── exactly ONE clinical-family model call, no automatic retry ─────
    print("\n" + "=" * 70)
    print("MODEL CALL (exactly 1, no automatic retry)")
    print("=" * 70)
    cost_circuit_breaker.raise_if_tripped()

    async def dispatch(system_prompt: str, user_prompt: str) -> dict:
        return await ai_registry.dispatch_call(
            cfg, [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            max_tokens=MAX_TOKENS, json_mode=True, temperature=0.0, timeout=60.0,
        )

    call_result = await harness.run_one_clinical_call(prompt.system, prompt.user, dispatch)
    assert call_result.call_count == 1, "harness must make exactly one model call"

    cost_usd = ai_pricing.estimate_llm_cost(cfg.model_name, call_result.input_tokens, call_result.output_tokens)
    await cost_tracking.log_ai_usage(
        "llm", cfg.provider, cost_usd if call_result.success else 0.0,
        user_id=EXPERIMENT_USER_TAG, model=cfg.model_name, purpose=PURPOSE,
        latency_ms=call_result.latency_ms, success=call_result.success,
        error_message=call_result.error,
        detail={"input_tokens": call_result.input_tokens, "output_tokens": call_result.output_tokens,
                "finish_reason": call_result.finish_reason} if call_result.success else None,
    )
    if call_result.success:
        print(f"[CALL OK] latency_ms={call_result.latency_ms} input_tokens={call_result.input_tokens} "
              f"output_tokens={call_result.output_tokens} finish_reason={call_result.finish_reason} cost_usd={cost_usd}")
    else:
        print(f"[CALL FAILED] {call_result.error}")

    # ── Phase 2 validation + Phase 3 evidence-reference audit (authoritative) ──
    print("\n" + "=" * 70)
    print("PHASE 2 VALIDATION + EVIDENCE-REFERENCE AUDIT")
    print("=" * 70)
    outcome = harness.evaluate_clinical_response(call_result.raw_text, criterion_evidence_map)
    print(f"  schema_valid={outcome.validation_valid} schema_errors={outcome.validation_errors}")
    print(f"  evidence_reference_errors={outcome.evidence_reference_errors}")
    if outcome.used_fallback:
        print("  -> using safe fallback (status=limited_evidence, level=null) for all 5 clinical criteria")
    else:
        print("  OK -- every cited evidence_id/turn_index exists in the supplied CriterionEvidenceMap for its own criterion")
    judgements = outcome.judgements

    # ── audit table ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("HUMAN-REVIEW AUDIT TABLE")
    print("=" * 70)
    print(f"{'Criterion':32s} {'Status':24s} {'Level':6s} {'#Refs':6s} {'Quality':12s} Review")
    for j in judgements:
        print(f"{j.criterion:32s} {j.status:24s} {str(j.level):6s} {len(j.evidence_refs):<6d} {j.evidence_quality:12s} REVIEW")

    # ── final artifact dump (logs/artifact only, never persisted to a table) ──
    out = {
        "environment": {"qa_project_ref": env_guard.project_ref(settings.SUPABASE_URL)},
        "session": {"pipeline": "realtime", "session_usage_id": SESSION_USAGE_ID, "scenario_id": SCENARIO_ID, "turns": len(history)},
        "model": {"purpose": PURPOSE, "provider": cfg.provider, "model_name": cfg.model_name},
        "call": {
            "latency_ms": call_result.latency_ms, "success": call_result.success, "error": call_result.error,
            "input_tokens": call_result.input_tokens, "output_tokens": call_result.output_tokens,
            "finish_reason": call_result.finish_reason, "cost_usd": cost_usd, "call_count": call_result.call_count,
        },
        "validation": {"schema_valid": outcome.validation_valid, "schema_errors": outcome.validation_errors,
                        "evidence_reference_errors": outcome.evidence_reference_errors, "used_fallback": outcome.used_fallback},
        "raw_model_text": call_result.raw_text,
        "judgements": [j.model_dump() for j in judgements],
        "audit_summary": {
            "clinical_criteria": len(se.CLINICAL_CRITERIA),
            "indicators_total": len(se.ALL_INDICATOR_IDS),
            "audio_available": examiner_input.audio_availability.audio_available,
            "semantic_provenance_present": semantic_refs_present,
        },
    }
    out_path = Path(__file__).resolve().parents[1] / "qa-artifacts" / "phase3_shadow_examiner_clinical_result.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nFull result written to {out_path} (artifact/log only -- no DB table, no score write)")


if __name__ == "__main__":
    asyncio.run(main())
