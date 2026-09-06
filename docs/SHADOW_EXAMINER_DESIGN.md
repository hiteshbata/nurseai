# Shadow OET Examiner — Design (Step 21K)

**Date:** 2026-08-29
**Scope:** Design only. No code, prompt, schema, model call, migration, or scoring change made while producing this document. `score_speaking()`, `/speaking/score`, Learning Brain, and the database are untouched.
**Predecessor:** `docs/SPEAKING_EVIDENCE_SPECIFICATION.md` (2026-08-28) — that document is the controlling source for the OET framework tables and evidence-gap tables referenced below by section number; nothing there is re-copied verbatim here.

---

## 0. What Step 0 inspection actually found

Contrary to the task's framing that these are future modules, `examiner_input.py` (Step 19) and `criterion_evidence.py` (Step 20) already exist, are already wired to `evidence_reconciliation.py`, and already implement most of the "future" contract the earlier spec proposed:

- `ExaminerInput` (pydantic, pure, no I/O) — scenario context, transcript, linguistic evidence (pronunciation/jargon), `ClinicalEvidence.unified_evidence`, session context, `AudioAvailability`, `evidence_gaps`.
- `CriterionEvidenceMap` (pydantic, pure, deterministic) — 9 criteria bundles (`ClinicalCriterionBundle` × 5, `LinguisticCriterionBundle` × 4), each carrying `EvidenceRef[]` (source/turn/provenance/L1–L4 level), `evidence_quality` (STRONG/PARTIAL/LIMITED/INSUFFICIENT — coverage, never performance), and `gaps`.
- Current live scorer (`ai_scoring.score_speaking`) is a single transcript-only LLM call via `_call_ai()` → `ai_registry.get_model_config(purpose)` (purpose-keyed model config with one fallback candidate + per-provider circuit breaker + `ai_usage_events` cost logging), JSON-mode with a fence-strip retry (`_try_parse_json`), Python-side aggregation `overall_band = clinical_average*0.6 + linguistic_average*0.4`. It has **zero dependency** on the evidence layer above.
- `admin_speaking_evidence.py` is the existing read-only QA surface that reconstructs real sessions (both pipelines) through `build_speaking_evidence_with_semantics` + `reconcile_evidence` — the exact machinery a Shadow Examiner would consume, already proven against production data.

This changes the shape of this design: there is no "input adapter" left to build. The gap is squarely **ExaminerInput + CriterionEvidenceMap → judgement**, which is what this document designs.

---

## 1. Official OET framework used

Reused as-is from `SPEAKING_EVIDENCE_SPECIFICATION.md` §2–§5: 9 criteria (4 linguistic, 0–6; 5 clinical, 0–3), 19 indicators A1–E5 as evidence *for* the 5 clinical criteria, not separate scores. No new interpretation of the source PDF is introduced here. The clinical scale's per-indicator descriptor gap (spec §5, §17) is inherited unchanged — the Shadow Examiner cannot resolve it either; see §21 below.

---

## 2. Current SpeakOET evidence architecture

```text
Conversation (legacy submissions.answer text | realtime session_transcripts)
    -> speaking_evidence.build_speaking_evidence[_with_semantics]()
         (opening/attentiveness/nonjudgmental/structure/sequencing/
          cue_response/information_gathering/information_giving detectors
          + semantic_evidence.py's 3 conservative LLM classifiers)
    -> evidence_reconciliation.reconcile_evidence() -> UnifiedEvidence
         (provenance-tagged: deterministic_rule | semantic_model | hybrid)
    -> examiner_input.build_examiner_input() -> ExaminerInput
         (pure, no model calls, no DB)
    -> criterion_evidence.map_criterion_evidence() -> CriterionEvidenceMap
         (pure, deterministic, 9 criteria, 20 indicator evidence bundles)
    -> [THIS STEP] ShadowExaminer -> ShadowResult   (not built)

score_speaking() [LIVE, untouched]:
Conversation transcript -> single LLM call (ai_registry purpose config
+ fallback + circuit breaker) -> 9 raw scores -> overall_band (0.6/0.4
Python weighting) -> shown to student today
```

The two paths share no code. That is the boundary this step preserves.

---

## 3. Shadow Examiner boundary

New module, e.g. `app/services/shadow_examiner.py` (name only, not created). Conceptually:

```text
ExaminerInput + CriterionEvidenceMap -> ShadowExaminer.evaluate() -> ShadowResult
```

`score_speaking()` keeps running exactly as today, on its own input, producing its own result, shown to the student. `ShadowResult` is never read by any student-facing code path in this design.

---

## 4. Examiner input contract

No new type needed. The Shadow Examiner takes **both** already-existing objects, because they're not redundant:

- `ExaminerInput` carries things `CriterionEvidenceMap` doesn't repeat: `scenario_context`, `session_context`, `audio_availability`, the raw `transcript`.
- `CriterionEvidenceMap` carries the organized, per-criterion/per-indicator evidence bundles `ExaminerInput` doesn't pre-group.

Nothing is added; nothing internal (DB rows, credentials, `session_usage_id` beyond what's already an opaque integer in both objects) is exposed beyond what these two models already contain.

---

## 5. Criterion judgement model

One `CriterionJudgement` per one of the 9 official criteria — never per indicator:

```text
CriterionJudgement
├── criterion: str                 # one of the 9 ALL_CRITERIA constants (examiner_input.py)
├── family: "linguistic" | "clinical"
├── status: "assessed" | "limited_evidence" | "evidence_conflict_unresolved"
├── level: Optional[int]           # 0-6 (linguistic) / 0-3 (clinical); null unless status == "assessed"
├── level_label: Optional[str]     # clinical only: Adept/Competent/Partially effective/Ineffective
├── justification: str             # cites evidence_refs by id, never invents detail
├── evidence_refs: List[EvidenceRefPointer]   # {evidence_id, turn_index, evidence_level, source} - pointers, not copies
├── evidence_quality: str          # rolled up from the bundle's own STRONG/PARTIAL/LIMITED/INSUFFICIENT
└── limitations: List[str]         # structured gap reason_codes, reused from EvidenceGap.reason_code where possible
```

`status` and `level` are deliberately orthogonal fields (Step 19) — see §15.

---

## 6. Clinical indicator handling

The examiner receives a full `ClinicalCriterionBundle` (all of that criterion's indicators, each with its own `evidence_refs`/`gaps`) and must produce **one** 0–3 judgement for the criterion, weighing the complete indicator set. Prompt-level hard rule: a single strong indicator never single-handedly sets the criterion level (the explicit anti-pattern named in the task: "D2 detected → criterion good" is banned). An indicator with no evidence this session (`gaps` non-empty, `evidence_refs` empty) is named in `limitations`, not silently averaged into a lower level.

---

## 7. Linguistic criteria handling

| Criterion | Evidence source | Rule |
|---|---|---|
| Intelligibility, Fluency | `LinguisticCriterionBundle.audio_available` + `PronunciationEvidence` | If `audio_available` is false (non-Elite today, per spec §11), status must be `limited_evidence`, `level=null`. The examiner is never allowed to infer intelligibility/fluency from transcript text alone — this is the task's own example (Step 5), and matches spec §11's finding that transcript is acoustically illegitimate for these two. |
| Appropriateness of Language, Resources of Grammar and Expression | Transcript + `jargon_evidence` | Transcript-legitimate per spec §11 — these can reach `status="assessed"` from text evidence alone. `evidence_quality` (PARTIAL for Appropriateness, LIMITED/INSUFFICIENT for Grammar, per spec §9) is surfaced in `limitations` as a confidence caveat on the justification, not a reason to null the level. |

---

## 8. Evidence hierarchy

Reuses `criterion_evidence.py`'s L1–L4 constants unchanged (`LEVEL_L1_DIRECT` … `LEVEL_L4_PATIENT_OUTCOME`). Interpretation rule for the examiner: L1/L2 (direct transcript/audio, deterministic detector) are primary evidence of candidate behavior; L3 (semantic) supports interpretation but must be named as inference in the justification when it's the only source; L4 (patient outcome — trust/emotion/concern-status changes) corroborates but never substitutes for direct candidate-behavior evidence (task Step 7 — a resolved concern is not proof empathy occurred; it's supporting context for an A4 judgement that must also cite an actual candidate utterance).

---

## 9. Provenance

`EvidenceRef` (already defined in `criterion_evidence.py`: `source`, `evidence_id`, `turn_index`, `evidence_text`, `provenance`, `evidence_level`, `related_patient_turn`, `metadata`) is the traceability unit. `CriterionJudgement.evidence_refs` stores lightweight pointers (`evidence_id` + `turn_index` + `evidence_level`) rather than copying `evidence_text` again — keeps output small, keeps the click-through-to-transcript-turn goal (task Step 31) achievable later by re-joining against the `CriterionEvidenceMap` that produced the input, which is already logged/reproducible since both are pure functions of stored data.

---

## 10. Missing-evidence handling

Directly from the bundle's own `evidence_quality`:

- `evidence_quality == INSUFFICIENT` and no `evidence_refs` → `status = "limited_evidence"`, `level = null`, `limitations` lists every `EvidenceGap.reason_code` on that bundle.
- `PARTIAL`/`LIMITED` with some refs → `status = "assessed"`, level set, but `limitations` still names the gap so a level isn't read as evidence-complete.
- Never: gap → `level = 0`. (Task Step 9/19's explicit rule — this is why `level` is `Optional`.)

---

## 11. Conflicting evidence handling

The examiner sees **all** `evidence_refs`, including a `hybrid`-provenance event's two source entries, and any L2-vs-L4 tension (e.g., a `dismissive_response` candidate event alongside a `trust` state transition that didn't drop) side by side — nothing is pre-filtered or merged into one entry before the model sees it. Prompt rule: on conflict, name both sides in `justification` and apply default precedence L1/L2 (direct) > L3 (semantic) > L4 (outcome, corroboration only). If the conflict is severe enough that no defensible level follows (e.g., deterministic and semantic evidence flatly contradict on the *same* turn with no direct evidence to arbitrate), `status = "evidence_conflict_unresolved"`, `level = null` — a narrow escape hatch, expected to be rare.

---

## 12. Audio limitations

Gated entirely by `ExaminerInput.audio_availability.audio_available` and each `LinguisticCriterionBundle.audio_required`/`audio_available`. No audio → Intelligibility/Fluency are `limited_evidence` by construction (§7). The examiner is never given license to "estimate" pronunciation from spelling/word-choice — that channel-mismatch risk is exactly what spec §20 flags as the highest-severity risk in the current live scorer, and this design must not reproduce it.

---

## 13. Semantic evidence failure handling

`evidence_reconciliation.py` already resolves this upstream: a semantic classifier failure (`STATUS_PROVIDER_FAILURE`/`PARSE_FAILURE`/`TOKEN_LIMIT`/`MALFORMED`) collapses to the deterministic/conservative value with `provenance` staying `deterministic_rule`, never silently promoted. The Shadow Examiner does not need to detect semantic failure itself — it only ever sees the already-resolved, correctly-labeled provenance. Its one added responsibility: when a criterion's evidence is *entirely* single-provenance-deterministic where semantic coverage would normally add depth (e.g., B3, which per spec §7 is semantic-only today), note that in `limitations` as reduced interpretive depth, not as a negative signal.

---

## 14. Criterion-level level/score model

- Linguistic: integer band 0–6 (spec §4).
- Clinical: integer 0–3 **plus** the official label (Adept/Competent/Partially effective/Ineffective, spec §5) in `level_label`.
- No overall combined score anywhere in `ShadowResult` (§16, §17) — the source PDF gives no cross-criterion aggregation rule (spec §5's explicit note), so none is invented, unlike the live scorer's `0.6/0.4` weighting, which is `ai_scoring.py`'s own legacy invention and is not carried forward here.

---

## 15. Uncertainty model

`status` (assessed / limited_evidence / evidence_conflict_unresolved) is orthogonal to `level` (Optional[int]). This is the direct implementation of the task's own preferred example: `status="limited_evidence", level=null` instead of `score=0`. A missing per-indicator detector (§10) never becomes a criterion failure.

---

## 16. Output schema

```json
{
  "session_ref": {"pipeline": "realtime|legacy", "session_usage_id": 123},
  "criteria": [
    {
      "criterion": "relationship_building",
      "family": "clinical",
      "status": "assessed",
      "level": 2,
      "level_label": "Competent use",
      "justification": "...",
      "evidence_refs": [{"evidence_id": "empathy_acknowledgement", "turn_index": 4, "evidence_level": "L2_deterministic"}],
      "evidence_quality": "PARTIAL",
      "limitations": ["semantic paraphrase coverage for empathy not available this session"]
    }
  ],
  "evaluation_metadata": {
    "model": "...", "prompt_version": "...", "generated_at": "...",
    "criteria_unavailable": [], "evidence_complete": false
  }
}
```

No `"overall"` block (§14/§17). No numeric confidence field — `evidence_quality` (categorical, reused vocabulary) does that job per the task's own preference (Step 8).

---

## 17. Model/prompt architecture options (Step 24)

| Option | Shape | Cost/latency | Consistency | Auditability | Failure isolation |
|---|---|---|---|---|---|
| A. One call, all 9 criteria | single big prompt+schema | cheapest (1 call) | model can reason across criteria | hard — one flat generation, large schema, higher malformed-JSON risk (the exact failure mode `ai_scoring.py`'s fence-strip retry exists to patch) | none — one failure loses everything |
| B. One call per criterion | 9 small calls | 9x cost/latency | no cross-criterion context | best — one focused prompt per criterion, easy to version independently | best — one criterion's failure doesn't affect the other 8 |
| C. Two-stage (interpret → judge) | 2x calls minimum | expensive, more moving parts | — | intermediate artifact aids audit | more failure surfaces, not fewer |
| D. Hybrid: deterministic evidence (already built) + one grouped model call per family | 2 calls (linguistic, clinical) | 2x cost, bounded | each call sees only evidence relevant to its family | small, focused schema per call (≤5 criteria) | per-family isolation |

Option C is largely redundant here: the "interpretation" stage it proposes is already done, for free, by `criterion_evidence.py` — a second LLM interpretation pass over already-structured, already-leveled evidence adds a failure surface without adding information.

---

## 18. Recommended model architecture

**Option D**, split by family (one call for the 4 linguistic criteria, one for the 5 clinical criteria):

- Reuses `ai_registry`'s existing purpose→model config + single-hop fallback + per-provider circuit breaker unchanged (new `purpose` value(s), no new infra).
- Two small, independently-schema-validated outputs (≤5 criteria each) keep JSON-parse reliability high — avoids Option A's single giant schema, which is the known failure mode the current scorer already works around.
- Cheaper than Option B (2 calls vs 9) while keeping most of its isolation benefit, since linguistic and clinical criteria already need different context shapes (`audio_availability`+`pronunciation` vs `UnifiedEvidence`) — splitting along that seam is free, splitting further buys little.
- Not Sonnet-by-default (task Step 22): `purpose` is a config lookup exactly like every other `_call_ai` caller; which model backs `speaking_shadow_examiner_linguistic`/`_clinical` is an Admin > AI Models decision, evaluable later against Sonnet/Gemini/other candidates on the same fixed `ExaminerInput`+`CriterionEvidenceMap` pair.

---

## 19. Failure/fallback architecture

Per family call: `ai_registry` config + fallback candidate, exactly as `_call_ai` today. If both fail (or `PurposeNotConfigured`), that family's criteria all get `status="limited_evidence"`, `level=null`, `evaluation_metadata.criteria_unavailable` lists them — never `level=0`. A linguistic failure does not block returning a valid clinical result, and vice versa (family-level isolation, §17/18). Top-level `ShadowResult` itself never "fails" in a way that raises to the caller — worst case is a result where every criterion is `limited_evidence`.

---

## 20. JSON validation (Step 26)

Reuse `ai_scoring.py`'s proven two-attempt shape (`_try_parse_json`: raw parse, then fence-strip retry) unchanged as the parsing step for each family's response. After that, **schema validation**: parse into the family's `CriterionJudgement[]` pydantic model; a missing criterion, a `level` outside that family's official range (0–6 / 0–3), or an invalid `status` value invalidates the **whole family batch** (not a per-field patch) → falls to §19's `limited_evidence` fallback for that family. No partial trust of a malformed object.

---

## 21. Human calibration plan

Per spec §17, the clinical 0–3 scale has no source-provided descriptor text distinguishing Adept/Competent/Partially effective/Ineffective per indicator — the single largest open question, unresolved by this design because the source PDF doesn't resolve it either. Plan: build the golden set (§22), have a human assign `CriterionJudgement`-shaped scores + which A1–E5 indicators they actually observed (with turn indices), run the Shadow Examiner on the same transcripts, and diff level-by-level, citing which `evidence_refs` the human vs. the model weighted differently. No numeric inter-rater-agreement threshold is invented (task explicitly bans this — real OET tolerance is not something this document claims to know).

---

## 22. Golden consultation plan

Merge spec §18's existing recommendation (10–20 transcripts per patient-mood archetype, at least one per linguistic band boundary 6/5…1/0, at least one Elite/audio session) with this task's Step 28 archetype list (strong/weak overall; strong-language-weak-clinical and its inverse; excellent vs. poor relationship building; poor questioning/structure/info-giving; concern resolved vs. ignored vs. reopened; multiple concerns; no audio; conflicting evidence; semantic evidence unavailable; minimal/very short/very long consultation) into one benchmark spec. Each entry needs: human per-criterion judgement, human indicator annotations with turn indices, and an explicit note of which criteria had no legitimate evidence that session (so the benchmark itself models the missing-vs-negative distinction, not just scores). Not built in this step.

---

## 23. Anti-hallucination rules (Step 32, verbatim intent)

SYSTEM-level hard rules for the future prompt: never invent candidate statements, patient reactions, or audio data not present in `ExaminerInput`; never invent evidence beyond what's in `CriterionEvidenceMap`; never convert an evidence gap into a poor score; never state a semantic-model inference as a directly-observed fact — always flag it as such in `justification`; never invent an overall/combined weighting across the 9 criteria.

---

## 24. Future Learning Brain handoff

```text
ShadowExaminer -> ShadowResult
      -> [FUTURE, not designed here] validated_observations extraction
              (only after human calibration confirms ShadowResult is trustworthy)
      -> Learning Brain
```

No interface, schema, or code for this hop exists or is proposed beyond the name — matches task Step 21's "conceptual only" instruction. It is explicitly gated behind calibration (§21), not behind this step.

---

## 25. Implementation phases (revised from the task's suggested sequence)

The task's suggested sequence assumes an input adapter still needs building; it doesn't (§0). Revised:

1. **Prompt + output schema definition** (Step 23's SYSTEM/USER structure, §16's `ShadowResult`/`CriterionJudgement` pydantic models) — pure design/code artifact, no model call wired yet. *(Recommended starting point — see Final Decision.)*
2. **Offline schema validation** — round-trip a hand-written or golden-fixture `ExaminerInput`+`CriterionEvidenceMap` pair through the schema with a stubbed model response, confirm §20's validation/fallback logic behaves.
3. **Live single-session evaluation** against the configured model (new `ai_registry` purpose(s)), admin/QA-only, using `admin_speaking_evidence.py`'s existing session-reconstruction as the fixture source — no storage yet, print/log only.
4. **Golden consultation benchmark** (§22) built and scored by humans.
5. **Human calibration** (§21) against the golden set.
6. **Shadow mode against real users** (§19/20 architecture) — admin/QA-flagged sessions only, result stored separately (new table, not created in this step), never shown to students.
7. **Criterion-level validation** — compare Shadow vs. current-scorer vs. human on the golden set, per criterion, citing disagreement causes.
8. **Controlled scoring integration** — only after 4–7 pass, and only incrementally, per spec §19's own final recommendation (extend, don't replace, `score_speaking()`).

---

## Final Decision

**Smallest safe next step: Phase 1 above — write the Shadow Examiner's SYSTEM/USER prompt structure and the `ShadowResult`/`CriterionJudgement` pydantic schema (§16, §17/§18's chosen Option D shape) as a standalone module with zero model wiring.** No `ai_registry` purpose is registered, no call is made, nothing runs against a real session yet. This is checkable in isolation (schema imports, pydantic validation against a hand-built fixture) before any cost, latency, or live-model risk is introduced. `score_speaking()` and the student-facing score stay untouched through every phase up to Phase 8, and Phase 8 does not start until Phases 4–7 (golden set, human calibration, shadow mode, criterion-level validation) have already passed.
