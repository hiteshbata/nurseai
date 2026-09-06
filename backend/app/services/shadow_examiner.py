"""Shadow OET Examiner -- schema and prompt structure only (Step 21K, Phase 1).

Design doc: docs/SHADOW_EXAMINER_DESIGN.md (approved 2026-08-29).

Scope of this module: `CriterionJudgement` + `ShadowResult` pydantic models,
the `EvidenceRefPointer` lightweight evidence pointer, and standalone
SYSTEM/USER prompt templates for the future Shadow Examiner. NOTHING here
calls a model, calls `ai_registry`, reads/writes the database, or is wired
into `score_speaking()` / `/speaking/score`. This module is pure: importing
it and calling every function in it makes 0 network calls and 0 AI calls.

    ExaminerInput + CriterionEvidenceMap (Step 19/20, already built)
        -> build_shadow_examiner_prompt() -> SYSTEM/USER prompt text
        -> [FUTURE, NOT WIRED HERE] model call -> raw JSON
        -> CriterionJudgement / validate_family_judgements() -> ShadowResult

CLINICAL INDICATOR COUNT CORRECTION: earlier docs (SPEAKING_EVIDENCE_
SPECIFICATION.md, SHADOW_EXAMINER_DESIGN.md, examiner_input.py's own
docstring) say "19 indicators". The correct count is 20: A1-A4 (4) + B1-B3
(3) + C1-C3 (3) + D1-D5 (5) + E1-E5 (5) = 20. `examiner_input.
INDICATORS_BY_CRITERION` already lists all 20 correctly -- only the prose
comments elsewhere undercounted. This module uses 20 consistently and
asserts it at import time (see `ALL_INDICATOR_IDS` below) rather than
silently repeating the old miscount.

STATUS/LEVEL ARE ORTHOGONAL (design doc Step 19/Step 15): `status` never
implies a level. A missing detector or missing audio evidence is
`limited_evidence` + `level=None` -- never `level=0`. `level=0` is a real,
earned "Ineffective use" judgement, not a stand-in for "we don't know".

No overall score, no numeric confidence, and no 0.6/0.4-style cross-
criterion weighting exist anywhere in this module -- the official OET
source gives no such rule, so none is invented here (unlike `ai_scoring.
score_speaking`'s own `overall_band` weighting, which belongs to that
separate, untouched, live scoring path).
"""
from __future__ import annotations

import json
from typing import List, Optional

from pydantic import BaseModel, field_validator, model_validator

from app.services.criterion_evidence import (
    LEVEL_L1_DIRECT,
    LEVEL_L2_DETERMINISTIC,
    LEVEL_L3_SEMANTIC,
    LEVEL_L4_PATIENT_OUTCOME,
    ClinicalCriterionBundle,
    CriterionEvidenceMap,
    LinguisticCriterionBundle,
)
from app.services.examiner_input import (
    ALL_CRITERIA,
    AVAILABILITY_INSUFFICIENT,
    AVAILABILITY_LIMITED,
    AVAILABILITY_PARTIAL,
    AVAILABILITY_STRONG,
    CLINICAL_CRITERIA,
    INDICATOR_TEXT,
    INDICATORS_BY_CRITERION,
    LINGUISTIC_CRITERIA,
    ExaminerInput,
)

# ── Indicator inventory (20, corrected -- see module docstring) ───────────
ALL_INDICATOR_IDS: List[str] = [
    indicator for ids in INDICATORS_BY_CRITERION.values() for indicator in ids
]
assert len(ALL_INDICATOR_IDS) == 20, "official OET clinical framework has 20 indicators, not 19"

# ── Family constants (reuses criterion_evidence.py's own bundle defaults) ──
FAMILY_LINGUISTIC = "linguistic"
FAMILY_CLINICAL = "clinical"
VALID_FAMILIES = {FAMILY_LINGUISTIC, FAMILY_CLINICAL}

# ── Status model (design doc §15: orthogonal to level) ─────────────────────
STATUS_ASSESSED = "assessed"
STATUS_LIMITED_EVIDENCE = "limited_evidence"
STATUS_EVIDENCE_CONFLICT_UNRESOLVED = "evidence_conflict_unresolved"
VALID_STATUSES = {STATUS_ASSESSED, STATUS_LIMITED_EVIDENCE, STATUS_EVIDENCE_CONFLICT_UNRESOLVED}

# ── Level ranges ────────────────────────────────────────────────────────────
LINGUISTIC_LEVEL_MIN, LINGUISTIC_LEVEL_MAX = 0, 6
CLINICAL_LEVEL_MIN, CLINICAL_LEVEL_MAX = 0, 3

# ── Official clinical 0-3 scale labels (SPEAKING_EVIDENCE_SPECIFICATION.md §5,
# sourced from the OET "Speaking sub-test: Assessment criteria and level
# descriptors" PDF -- one shared 4-point scale applied per clinical criterion,
# not per indicator) ─────────────────────────────────────────────────────────
CLINICAL_LEVEL_LABELS = {
    3: "Adept use",
    2: "Competent use",
    1: "Partially effective use",
    0: "Ineffective use",
}

VALID_EVIDENCE_LEVELS = {LEVEL_L1_DIRECT, LEVEL_L2_DETERMINISTIC, LEVEL_L3_SEMANTIC, LEVEL_L4_PATIENT_OUTCOME}
VALID_EVIDENCE_QUALITIES = {AVAILABILITY_STRONG, AVAILABILITY_PARTIAL, AVAILABILITY_LIMITED, AVAILABILITY_INSUFFICIENT}

# ── Prompt version (explicit, immutable -- never a bare anonymous string) ──
PROMPT_VERSION = "shadow_examiner_v1"


# ── Schema types ─────────────────────────────────────────────────────────

class EvidenceRefPointer(BaseModel):
    """Lightweight pointer into a CriterionEvidenceMap's EvidenceRef -- never
    duplicates evidence_text. Re-join on (evidence_id, turn_index) against
    the CriterionEvidenceMap that produced the input to recover full detail;
    both that map and this pointer are pure functions of stored data, so the
    join is always reproducible (design doc §9)."""

    evidence_id: str
    turn_index: Optional[int] = None
    evidence_level: str
    source: str
    provenance: Optional[str] = None

    @field_validator("evidence_level")
    @classmethod
    def _valid_evidence_level(cls, v: str) -> str:
        if v not in VALID_EVIDENCE_LEVELS:
            raise ValueError(f"invalid evidence_level: {v!r}")
        return v


class CriterionJudgement(BaseModel):
    """One judgement per official OET criterion (9 total, never per
    indicator). No overall score, no numeric confidence -- see module
    docstring."""

    criterion: str
    family: str
    status: str
    level: Optional[int] = None
    level_label: Optional[str] = None
    justification: str
    evidence_refs: List[EvidenceRefPointer] = []
    evidence_quality: str
    limitations: List[str] = []

    @field_validator("criterion")
    @classmethod
    def _valid_criterion(cls, v: str) -> str:
        if v not in ALL_CRITERIA:
            raise ValueError(f"invalid criterion: {v!r}")
        return v

    @field_validator("family")
    @classmethod
    def _valid_family(cls, v: str) -> str:
        if v not in VALID_FAMILIES:
            raise ValueError(f"invalid family: {v!r}")
        return v

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"invalid status: {v!r}")
        return v

    @field_validator("evidence_quality")
    @classmethod
    def _valid_evidence_quality(cls, v: str) -> str:
        if v not in VALID_EVIDENCE_QUALITIES:
            raise ValueError(f"invalid evidence_quality: {v!r}")
        return v

    @model_validator(mode="after")
    def _check_consistency(self) -> "CriterionJudgement":
        expected_family = FAMILY_LINGUISTIC if self.criterion in LINGUISTIC_CRITERIA else FAMILY_CLINICAL
        if self.family != expected_family:
            raise ValueError(
                f"family {self.family!r} inconsistent with criterion {self.criterion!r} "
                f"(expected {expected_family!r})"
            )

        if self.status != STATUS_ASSESSED:
            if self.level is not None:
                raise ValueError(f"level must be null when status is {self.status!r}, not {self.level!r}")
            if self.level_label is not None:
                raise ValueError(f"level_label must be null when status is {self.status!r}")
            return self

        # status == assessed: a level is required, missing evidence is never level=0.
        if self.level is None:
            raise ValueError("status=assessed requires a non-null level")

        if self.family == FAMILY_LINGUISTIC:
            if not (LINGUISTIC_LEVEL_MIN <= self.level <= LINGUISTIC_LEVEL_MAX):
                raise ValueError(
                    f"linguistic level must be {LINGUISTIC_LEVEL_MIN}-{LINGUISTIC_LEVEL_MAX}, got {self.level}"
                )
            if self.level_label is not None:
                raise ValueError("level_label is clinical-only; linguistic criteria must leave it null")
        else:
            if not (CLINICAL_LEVEL_MIN <= self.level <= CLINICAL_LEVEL_MAX):
                raise ValueError(
                    f"clinical level must be {CLINICAL_LEVEL_MIN}-{CLINICAL_LEVEL_MAX}, got {self.level}"
                )
            expected_label = CLINICAL_LEVEL_LABELS[self.level]
            if self.level_label != expected_label:
                raise ValueError(
                    f"level_label {self.level_label!r} inconsistent with level {self.level} "
                    f"(expected {expected_label!r})"
                )
        return self


class SessionRef(BaseModel):
    """Opaque session context only -- no PII, no raw transcript, matches
    ExaminerInput.session_context's own opaque identifiers."""

    pipeline: Optional[str] = None
    session_usage_id: Optional[int] = None


class EvaluationMetadata(BaseModel):
    model: Optional[str] = None
    prompt_version: str
    generated_at: str
    criteria_unavailable: List[str] = []
    evidence_complete: bool = True


class ShadowResult(BaseModel):
    """Top-level Shadow Examiner output. Exactly 9 CriterionJudgement
    entries, no more, no less, no duplicates -- never stored, never shown to
    students, never read by score_speaking() or Learning Brain (design doc
    §3, §24)."""

    session_ref: SessionRef
    criteria: List[CriterionJudgement]
    evaluation_metadata: EvaluationMetadata

    @field_validator("criteria")
    @classmethod
    def _exactly_nine_unique_and_complete(cls, v: List[CriterionJudgement]) -> List[CriterionJudgement]:
        if len(v) != len(ALL_CRITERIA):
            raise ValueError(f"criteria must contain exactly {len(ALL_CRITERIA)} entries, got {len(v)}")
        seen = set()
        for judgement in v:
            if judgement.criterion in seen:
                raise ValueError(f"duplicate criterion judgement: {judgement.criterion!r}")
            seen.add(judgement.criterion)
        missing = set(ALL_CRITERIA) - seen
        if missing:
            raise ValueError(f"missing criterion judgements: {sorted(missing)}")
        return v


def validate_family_judgements(family: str, judgements: List[CriterionJudgement]) -> List[CriterionJudgement]:
    """Family-specific validation (design doc §17/18/20's per-family model
    call): confirms `judgements` covers exactly that family's criteria, no
    more, no less, no duplicates, each tagged with the matching family. Used
    to validate one family's model response before merging both families
    into a ShadowResult -- raises ValueError on any violation rather than
    trusting a partial/malformed batch (§20: "invalidates the whole family
    batch, not a per-field patch")."""
    if family not in VALID_FAMILIES:
        raise ValueError(f"invalid family: {family!r}")
    expected = set(LINGUISTIC_CRITERIA if family == FAMILY_LINGUISTIC else CLINICAL_CRITERIA)

    seen = set()
    for judgement in judgements:
        if judgement.family != family:
            raise ValueError(f"judgement for {judgement.criterion!r} has family {judgement.family!r}, expected {family!r}")
        if judgement.criterion not in expected:
            raise ValueError(f"criterion {judgement.criterion!r} does not belong to family {family!r}")
        if judgement.criterion in seen:
            raise ValueError(f"duplicate criterion judgement: {judgement.criterion!r}")
        seen.add(judgement.criterion)

    missing = expected - seen
    if missing:
        raise ValueError(f"missing criterion judgements for family {family!r}: {sorted(missing)}")
    return judgements


def build_shadow_result(
    session_ref: SessionRef,
    linguistic_judgements: List[CriterionJudgement],
    clinical_judgements: List[CriterionJudgement],
    evaluation_metadata: EvaluationMetadata,
) -> ShadowResult:
    """Combines two already-validated family batches (Option D architecture,
    design doc §18) into one ShadowResult. Pure assembly + ShadowResult's own
    validator -- no model call, no fallback logic (that is live-wiring, not
    Phase 1's scope)."""
    validate_family_judgements(FAMILY_LINGUISTIC, linguistic_judgements)
    validate_family_judgements(FAMILY_CLINICAL, clinical_judgements)
    return ShadowResult(
        session_ref=session_ref,
        criteria=[*linguistic_judgements, *clinical_judgements],
        evaluation_metadata=evaluation_metadata,
    )


# ── Prompt structure (design doc §16-18, §23; Option D: one call per family) ─

_ROLE_HEADER = (
    "You are a shadow OET Speaking sub-test examiner. You never communicate with "
    "the candidate. You produce a private, offline, per-criterion judgement from "
    "the evidence given to you below, nothing else. Your output is never shown to "
    "the candidate and never changes their live score."
)

_FRAMEWORK_SUMMARY = (
    "The OET Speaking sub-test has 9 official criteria in two families. 4 linguistic "
    "criteria (Intelligibility, Fluency, Appropriateness of Language, Resources of "
    "Grammar and Expression), each scored 0-6. 5 clinical communication criteria "
    "(Relationship Building, Understanding & Incorporating the Patient's Perspective, "
    "Providing Structure, Information Gathering, Information Giving), each scored "
    "0-3 on one shared scale: 3 = Adept use, 2 = Competent use, 1 = Partially "
    "effective use, 0 = Ineffective use. Each clinical criterion is supported by "
    "named clinical indicators (A1-A4, B1-B3, C1-C3, D1-D5, E1-E5 -- 20 indicators "
    "total). Indicators are evidence for ONE criterion-level judgement; they are "
    "never independent scores of their own. A single strong or weak indicator must "
    "never single-handedly set the criterion level -- weigh the complete indicator "
    "set you are given."
)

_EVIDENCE_HIERARCHY_RULES = (
    "Every evidence item you receive carries an evidence_level: L1_direct (raw "
    "transcript/audio), L2_deterministic (rule-based detector), L3_semantic "
    "(model-based interpretation), or L4_patient_outcome (a simulated patient's "
    "resulting reaction or state change). L1/L2 are primary evidence of what the "
    "candidate actually did. L3 supports interpretation but must be named as an "
    "inference in your justification -- never presented as a directly observed "
    "fact. L4 corroborates a judgement but never substitutes for direct "
    "candidate-behavior evidence: a resolved patient concern is supporting context "
    "for empathy, not proof of it by itself. Each item also carries a provenance "
    "tag (direct, deterministic_rule, semantic_model, or hybrid) -- treat this as "
    "a confidence caveat, never as a separate performance signal."
)

_MISSING_EVIDENCE_RULES = (
    "Missing evidence must never be treated as poor performance. If a criterion or "
    "indicator has no supporting evidence this session, that is an evidence gap, "
    "not a failing behaviour, and must never be converted into a low or zero "
    "level. Example: no audio evidence -> you cannot confidently assess acoustic "
    "intelligibility or fluency; this is not the same as \"the candidate was "
    "unintelligible\". Example: no signposting evidence detected -> this is an "
    "evidence limitation, not an automatic Ineffective (0) judgement for Providing "
    "Structure. When evidence is missing or insufficient, set "
    "status=\"limited_evidence\" and level=null, and name the gap in `limitations`."
)

_CONFLICT_HANDLING_RULES = (
    "You may be given evidence that conflicts -- for example a deterministic "
    "detector and a semantic classifier disagreeing about the same turn, or a "
    "hybrid event carrying two source entries. Preserve and name both sides in "
    "your justification rather than silently picking one. Default precedence when "
    "evidence genuinely conflicts: L1/L2 (direct/deterministic) outweighs L3 "
    "(semantic); L4 (patient outcome) only ever corroborates, never overrides "
    "either. If the conflict is severe enough that no defensible level follows, "
    "set status=\"evidence_conflict_unresolved\" and level=null rather than "
    "guessing -- do not invent a numeric conflict weight to resolve it."
)

_ANTI_HALLUCINATION_RULES = (
    "Anti-hallucination rules: never invent a candidate statement, patient "
    "reaction, audio detail, or turn number that is not present in the evidence "
    "given to you. Never invent an indicator observation not backed by an "
    "evidence reference you were given. Never state a semantic-model inference "
    "as a directly observed fact. Never turn missing evidence into a low or zero "
    "level. Never produce an unsupported overall score. Never invent a weighting "
    "between criteria or between indicators that the official framework does not "
    "define."
)

_NO_OVERALL_WEIGHTING_RULE = (
    "There is no official rule for combining the 9 criteria into one overall "
    "score. You must not compute, estimate, or imply an overall band, a pass/fail "
    "outcome, or any weighting (such as a 0.6/0.4 split) across criteria. Your "
    "only output is one independent judgement per criterion assigned to you."
)

_OUTPUT_SCHEMA_INSTRUCTIONS = (
    "Respond with a JSON array of criterion judgement objects, one per criterion "
    "assigned to you this call, each matching exactly this shape: "
    "{criterion, family, status, level, level_label, justification, evidence_refs, "
    "evidence_quality, limitations}. status must be one of \"assessed\", "
    "\"limited_evidence\", \"evidence_conflict_unresolved\". level must be null "
    "unless status is \"assessed\". level_label must be one of \"Adept use\", "
    "\"Competent use\", \"Partially effective use\", \"Ineffective use\" for "
    "clinical criteria when status is \"assessed\", and must be null in every "
    "other case (including for all linguistic criteria). Cite evidence by "
    "evidence_id inside justification and evidence_refs; never introduce an "
    "evidence_id that was not given to you. Do not include any field not listed "
    "here, and do not include an overall score anywhere in your response."
)

_LINGUISTIC_ADDENDUM = (
    "This call covers the 4 linguistic criteria only. Two of them, Intelligibility "
    "and Fluency, depend on acoustic audio evidence (pronunciation/fluency "
    "scoring). If audio evidence is not available for this session "
    "(audio_availability.audio_available is false, or the relevant "
    "LinguisticCriterionBundle has no evidence_refs), you must not infer "
    "intelligibility or fluency from transcript text alone -- word choice and "
    "spelling are not evidence of pronunciation or spoken fluency. In that case "
    "set status=\"limited_evidence\" and level=null for that criterion. "
    "Appropriateness of Language and Resources of Grammar and Expression are "
    "transcript-legitimate and may reach status=\"assessed\" from transcript "
    "evidence alone."
)

_CLINICAL_ADDENDUM_HEADER = (
    "This call covers the 5 clinical communication criteria only. Each criterion "
    "definition, with its supporting indicators (evidence inputs, not separate "
    "scores):"
)


def _clinical_criterion_definitions() -> str:
    lines = []
    for criterion in CLINICAL_CRITERIA:
        indicator_ids = INDICATORS_BY_CRITERION[criterion]
        indicator_lines = "; ".join(f"{i}: {INDICATOR_TEXT[i]}" for i in indicator_ids)
        lines.append(f"- {criterion}: {indicator_lines}")
    return "\n".join(lines)


def build_system_prompt(family: str) -> str:
    """Pure string builder -- no model call, no I/O. Raises ValueError for
    an unknown family rather than silently defaulting."""
    if family not in VALID_FAMILIES:
        raise ValueError(f"invalid family: {family!r}")

    if family == FAMILY_LINGUISTIC:
        family_section = _LINGUISTIC_ADDENDUM
    else:
        family_section = f"{_CLINICAL_ADDENDUM_HEADER}\n{_clinical_criterion_definitions()}"

    return "\n\n".join([
        _ROLE_HEADER,
        _FRAMEWORK_SUMMARY,
        family_section,
        _EVIDENCE_HIERARCHY_RULES,
        _MISSING_EVIDENCE_RULES,
        _CONFLICT_HANDLING_RULES,
        _ANTI_HALLUCINATION_RULES,
        _NO_OVERALL_WEIGHTING_RULE,
        _OUTPUT_SCHEMA_INSTRUCTIONS,
    ])


class ShadowExaminerPrompt(BaseModel):
    family: str
    prompt_version: str
    system: str
    user: str


def build_user_prompt(
    family: str, examiner_input: ExaminerInput, criterion_evidence_map: CriterionEvidenceMap,
) -> str:
    """Pure string builder: serializes only the ExaminerInput/CriterionEvidenceMap
    fields relevant to `family` -- no DB credentials, no infra details, no
    application state beyond what those two existing pydantic models already
    carry."""
    if family not in VALID_FAMILIES:
        raise ValueError(f"invalid family: {family!r}")

    if family == FAMILY_LINGUISTIC:
        bundles: List[LinguisticCriterionBundle] = criterion_evidence_map.linguistic
        evidence_section = {"linguistic_criteria": [b.model_dump(mode="json") for b in bundles]}
    else:
        bundles_c: List[ClinicalCriterionBundle] = criterion_evidence_map.clinical
        evidence_section = {"clinical_criteria": [b.model_dump(mode="json") for b in bundles_c]}

    payload = {
        "scenario_context": examiner_input.scenario_context.model_dump(mode="json"),
        "transcript": [t.model_dump(mode="json") for t in examiner_input.transcript],
        "session_context": examiner_input.session_context.model_dump(mode="json"),
        "audio_availability": examiner_input.audio_availability.model_dump(mode="json"),
        **evidence_section,
    }

    instruction = (
        f"Evaluate ONLY the {family} criteria listed above using the ExaminerInput "
        "and CriterionEvidenceMap data below. Output the JSON array described in "
        "the system instructions now, and nothing else."
    )
    return f"{instruction}\n\n{json.dumps(payload, indent=2)}"


def build_shadow_examiner_prompt(
    family: str, examiner_input: ExaminerInput, criterion_evidence_map: CriterionEvidenceMap,
) -> ShadowExaminerPrompt:
    """Entry point: builds the full SYSTEM/USER pair for one family call
    (Option D architecture, design doc §18). Pure -- no model call, no
    ai_registry lookup, no network access."""
    return ShadowExaminerPrompt(
        family=family,
        prompt_version=PROMPT_VERSION,
        system=build_system_prompt(family),
        user=build_user_prompt(family, examiner_input, criterion_evidence_map),
    )
