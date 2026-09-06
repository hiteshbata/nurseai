"""Phase 5 -- Human Calibration Package schema + admin comparison utility.

Scope / hard boundary: OFFLINE ONLY. This module makes zero model calls,
zero `ai_registry` lookups, zero DB access, zero network access. It does not
touch `score_speaking()`, `/speaking/score`, Learning Brain, or the
database. Importing it and calling every function in it is a pure operation.

Reuses `shadow_examiner`'s own vocabulary (statuses, level ranges, clinical
level labels, family constants) rather than inventing a parallel one --
`HumanCriterionReview` is deliberately schema-compatible with
`shadow_examiner.CriterionJudgement` (same criterion/family/status/level
contract) but drops fields a human reviewer should never be asked to
produce (`evidence_quality`, which is a fact about the pipeline's own
evidence coverage, not a human judgement) and loosens `evidence_refs` to a
bare `turn_index` citation -- Phase 5 task Step 9 explicitly bans forcing a
human reviewer to use this codebase's detector-label vocabulary.

STATUS/LEVEL DISCIPLINE (unchanged from shadow_examiner.py): a criterion a
reviewer genuinely cannot assess is `status="limited_evidence"`,
`level=None` -- never a forced zero (task Step 6).
"""
from __future__ import annotations

from typing import List, Optional, Set

from pydantic import BaseModel, field_validator, model_validator

from app.services.examiner_input import ALL_CRITERIA, CLINICAL_CRITERIA, INDICATORS_BY_CRITERION, LINGUISTIC_CRITERIA
from app.services.shadow_examiner import (
    CLINICAL_LEVEL_MAX,
    CLINICAL_LEVEL_MIN,
    FAMILY_CLINICAL,
    FAMILY_LINGUISTIC,
    LINGUISTIC_LEVEL_MAX,
    LINGUISTIC_LEVEL_MIN,
    STATUS_ASSESSED,
    VALID_FAMILIES,
    VALID_STATUSES,
    CriterionJudgement,
)

REVIEW_STATUS_IN_PROGRESS = "in_progress"
REVIEW_STATUS_COMPLETE = "complete"
VALID_REVIEW_STATUSES = {REVIEW_STATUS_IN_PROGRESS, REVIEW_STATUS_COMPLETE}

# ── Agreement buckets (Step 12 -- data prep only, no threshold/verdict) ────
AGREEMENT_EXACT = "exact"
AGREEMENT_ADJACENT = "adjacent"
AGREEMENT_LARGE = "large_disagreement"
AGREEMENT_BOTH_LIMITED = "both_limited_evidence"
AGREEMENT_STATUS_MISMATCH = "status_mismatch"


class HumanEvidenceRef(BaseModel):
    """Reviewer citation -- turn_index only (task Step 9): no evidence_id,
    evidence_level, or provenance vocabulary is required. `evidence_id` is
    optional and only usable if the reviewer chooses to cross-reference the
    case's own CriterionEvidenceMap; never required."""

    turn_index: int
    note: Optional[str] = None
    evidence_id: Optional[str] = None

    @field_validator("turn_index")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("turn_index must be >= 0")
        return v


class HumanCriterionReview(BaseModel):
    criterion: str
    family: str
    status: str
    level: Optional[int] = None
    justification: str
    evidence_refs: List[HumanEvidenceRef] = []
    limitations: List[str] = []
    # Clinical only, optional (task Step 8): which indicators informed the
    # judgement. Never an independent per-indicator score.
    indicator_notes: List[str] = []

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

    @model_validator(mode="after")
    def _check_consistency(self) -> "HumanCriterionReview":
        expected_family = FAMILY_LINGUISTIC if self.criterion in LINGUISTIC_CRITERIA else FAMILY_CLINICAL
        if self.family != expected_family:
            raise ValueError(
                f"family {self.family!r} inconsistent with criterion {self.criterion!r} "
                f"(expected {expected_family!r})"
            )

        if self.indicator_notes:
            if self.family != FAMILY_CLINICAL:
                raise ValueError("indicator_notes is clinical-only")
            valid_ids = set(INDICATORS_BY_CRITERION[self.criterion])
            bad = [i for i in self.indicator_notes if i not in valid_ids]
            if bad:
                raise ValueError(f"indicator_notes {bad} do not belong to criterion {self.criterion!r}")

        if self.status != STATUS_ASSESSED:
            if self.level is not None:
                raise ValueError(
                    f"level must be null when status is {self.status!r} -- never force a zero (task Step 6)"
                )
            return self

        if self.level is None:
            raise ValueError("status=assessed requires a non-null level")
        if self.family == FAMILY_LINGUISTIC:
            if not (LINGUISTIC_LEVEL_MIN <= self.level <= LINGUISTIC_LEVEL_MAX):
                raise ValueError(f"linguistic level must be {LINGUISTIC_LEVEL_MIN}-{LINGUISTIC_LEVEL_MAX}, got {self.level}")
        else:
            if not (CLINICAL_LEVEL_MIN <= self.level <= CLINICAL_LEVEL_MAX):
                raise ValueError(f"clinical level must be {CLINICAL_LEVEL_MIN}-{CLINICAL_LEVEL_MAX}, got {self.level}")
        return self


class ReviewMetadata(BaseModel):
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    minutes_spent: Optional[float] = None


class HumanReview(BaseModel):
    """One reviewer's full assessment of one case. `reviewer_id` is optional
    and pseudonymous only (task Step 27 -- no email/phone/name/credentials)."""

    case_id: str
    reviewer_id: Optional[str] = None
    review_status: str = REVIEW_STATUS_IN_PROGRESS
    criteria: List[HumanCriterionReview]
    overall_notes: str = ""
    review_metadata: ReviewMetadata = ReviewMetadata()

    @field_validator("review_status")
    @classmethod
    def _valid_review_status(cls, v: str) -> str:
        if v not in VALID_REVIEW_STATUSES:
            raise ValueError(f"invalid review_status: {v!r}")
        return v

    @field_validator("criteria")
    @classmethod
    def _exactly_nine_unique_and_complete(cls, v: List[HumanCriterionReview]) -> List[HumanCriterionReview]:
        if len(v) != len(ALL_CRITERIA):
            raise ValueError(f"criteria must contain exactly {len(ALL_CRITERIA)} entries, got {len(v)}")
        seen: Set[str] = set()
        for review in v:
            if review.criterion in seen:
                raise ValueError(f"duplicate criterion review: {review.criterion!r}")
            seen.add(review.criterion)
        missing = set(ALL_CRITERIA) - seen
        if missing:
            raise ValueError(f"missing criterion reviews: {sorted(missing)}")
        return v


def blank_review_template(case_id: str = "") -> HumanReview:
    """One blank HumanCriterionReview per official criterion, all
    status=limited_evidence/level=None -- a safe starting scaffold a
    reviewer edits in place, never a scaffold that silently defaults to a
    real score."""
    from app.services.shadow_examiner import STATUS_LIMITED_EVIDENCE

    return HumanReview(
        case_id=case_id,
        criteria=[
            HumanCriterionReview(
                criterion=c,
                family=FAMILY_LINGUISTIC if c in LINGUISTIC_CRITERIA else FAMILY_CLINICAL,
                status=STATUS_LIMITED_EVIDENCE,
                level=None,
                justification="",
            )
            for c in ALL_CRITERIA
        ],
    )


# ── Administrator-only comparison utility (Step 13) ────────────────────────
# Kept separate from reviewer materials -- never imported by anything the
# reviewer-facing package generator writes into reviewer/.


class ComparisonRow(BaseModel):
    case_id: str
    criterion: str
    provisional_level: Optional[int]
    human_level: Optional[int]
    level_difference: Optional[int]
    human_status: str
    provisional_status: str
    agreement_bucket: str
    evidence_turn_overlap: List[int]


def _agreement_bucket(human_status: str, provisional_status: str, human_level: Optional[int], provisional_level: Optional[int]) -> str:
    human_assessed = human_status == STATUS_ASSESSED
    provisional_assessed = provisional_status == STATUS_ASSESSED
    if not human_assessed and not provisional_assessed:
        return AGREEMENT_BOTH_LIMITED if human_status == provisional_status else AGREEMENT_STATUS_MISMATCH
    if human_assessed != provisional_assessed:
        return AGREEMENT_STATUS_MISMATCH
    diff = abs(human_level - provisional_level)  # type: ignore[operator]
    if diff == 0:
        return AGREEMENT_EXACT
    if diff == 1:
        return AGREEMENT_ADJACENT
    return AGREEMENT_LARGE


def compare_case(
    case_id: str, human_criteria: List[HumanCriterionReview], provisional_criteria: List[CriterionJudgement],
) -> List[ComparisonRow]:
    """Diffs one reviewer's HumanReview.criteria against one case's
    provisional_reference (shadow_examiner_benchmark's own reference_
    judgement), criterion by criterion. Administrator tool only -- never
    shown to a blind reviewer. Pure, no I/O."""
    provisional_by_criterion = {c.criterion: c for c in provisional_criteria}
    rows: List[ComparisonRow] = []
    for human in human_criteria:
        provisional = provisional_by_criterion.get(human.criterion)
        if provisional is None:
            raise ValueError(f"no provisional judgement for criterion {human.criterion!r}")
        human_turns = {r.turn_index for r in human.evidence_refs}
        provisional_turns = {r.turn_index for r in provisional.evidence_refs if r.turn_index is not None}
        diff = None
        if human.level is not None and provisional.level is not None:
            diff = abs(human.level - provisional.level)
        rows.append(ComparisonRow(
            case_id=case_id, criterion=human.criterion,
            provisional_level=provisional.level, human_level=human.level, level_difference=diff,
            human_status=human.status, provisional_status=provisional.status,
            agreement_bucket=_agreement_bucket(human.status, provisional.status, human.level, provisional.level),
            evidence_turn_overlap=sorted(human_turns & provisional_turns),
        ))
    return rows
