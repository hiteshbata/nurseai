"""Unified Evidence Reconciliation Layer (Step 11).

Pure, offline reconciliation over an already-built speaking_evidence.SpeakingEvidence
object -- combines its deterministic- and semantic-sourced entries (both already
present in that object, see its module docstring) into one traceable view WITHOUT
overwriting either source. No new LLM calls, no network, no database (Step 15/19):
this only regroups data speaking_evidence already computed.

CRITICAL RULE (see module docstring on SpeakingEvidence and this task's spec):
semantic evidence never overwrites deterministic evidence, and a semantic call
failure never gets treated as a real "none" result. Every unified item carries a
`provenance` of exactly "deterministic_rule", "semantic_model", or "hybrid" -- no
invented confidence scores.

This module does not touch patient_state.py's PatientState engine or
concern_outcomes/state_transitions' own official fields -- those remain exactly
what the deterministic engine computed (Step 9: semantic evidence must not
directly invent state). Unified fields here (`unified_believed_status`,
merged `timeline`) are an additional, clearly-separate read model for human
review, not a new source of truth fed back into scoring or the live patient
prompt.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel

from app.services.patient_state import CONCERN_RANK
from app.services.semantic_evidence import (
    STATUS_MALFORMED,
    STATUS_PARSE_FAILURE,
    STATUS_PROVIDER_FAILURE,
    STATUS_TOKEN_LIMIT,
)
from app.services.speaking_evidence import (
    SOURCE_DETERMINISTIC,
    SOURCE_SEMANTIC,
    CandidateEvent,
    ConcernOutcome,
    HiddenInfoCandidateTurn,
    HiddenInfoOutcome,
    InteractionMetrics,
    JargonEvidence,
    PatientEvent,
    SpeakingEvidence,
    StateTransition,
)

PROVENANCE_DETERMINISTIC = SOURCE_DETERMINISTIC
PROVENANCE_SEMANTIC = SOURCE_SEMANTIC
PROVENANCE_HYBRID = "hybrid"

_SEMANTIC_FAILURE_STATUSES = {
    STATUS_PROVIDER_FAILURE, STATUS_PARSE_FAILURE, STATUS_TOKEN_LIMIT, STATUS_MALFORMED,
}

# Maps a semantic-sourced signal's own event name onto the deterministic
# concern-status vocabulary (patient_state.CONCERN_RANK), so it can be placed
# on the same merged timeline as deterministic history entries. Kept distinct
# from "resolved" (concern_resolution_signal -> "resolved_signal") -- a
# semantic resolution signal augments the record but is never what actually
# flips ConcernOutcome.resolved (that stays the deterministic engine's call,
# Step 9).
_CONCERN_EVENT_TO_STATUS = {
    "concern_exploration": "explored",
    "concern_addressing": "addressed",
    "concern_resolution_signal": "resolved_signal",
}
# Rank used only for computing unified_believed_status below -- a resolution
# signal counts as high-confidence belief without claiming official "resolved".
_BELIEVED_RANK = dict(CONCERN_RANK, resolved_signal=CONCERN_RANK["resolved"])


class UnifiedCandidateEvent(BaseModel):
    event: str
    turn_index: int
    target_concern: Optional[str] = None
    provenance: str
    evidence: List[Dict[str, str]]  # [{"source": ..., "evidence_text": ...}, ...] -- one entry per contributing source
    # Step 21D (D4/D5): union of every contributing source's related_patient_turns,
    # sorted/deduped -- empty for every other event.
    related_patient_turns: List[int] = []
    # Step 21E (E2/E3): same union/dedup treatment for related_information_turns.
    related_information_turns: List[int] = []


class UnifiedPatientEvent(BaseModel):
    event: str
    turn_index: int
    provenance: str
    evidence_text: str
    revealed: Optional[bool] = None
    target_concern: Optional[str] = None


class UnifiedConcernTimelineEntry(BaseModel):
    turn_index: int
    status: str
    provenance: str
    source_event: Optional[str] = None
    evidence_text: Optional[str] = None
    reopened: bool = False
    reopened_from: Optional[str] = None


class UnifiedConcernOutcome(BaseModel):
    concern: str
    deterministic_final_status: str
    unified_believed_status: str
    resolved: bool
    timeline: List[UnifiedConcernTimelineEntry]
    resolved_at_turns: List[int]
    reopened_events: List[Dict]


class UnifiedHiddenInfoOutcome(BaseModel):
    item: str
    candidate_detected: bool
    verification_status: str
    final_status: str
    provenance: str
    reason: str  # Task 10: structured reason code, see REASON_* constants below -- never free-form.
    turn_index: Optional[int] = None
    evidence_text: Optional[str] = None
    # Step 12B (Rule 5): full per-candidate-turn audit trail, passed through
    # from HiddenInfoOutcome unchanged -- the reconciled view must not
    # collapse multiple candidates into the single aggregate row above.
    candidate_turns: List[HiddenInfoCandidateTurn] = []


class UnifiedStateTransition(BaseModel):
    field: str
    before: str
    after: str
    cause_event: Optional[str]
    turn_index: int
    provenance: str = PROVENANCE_DETERMINISTIC


class UnifiedEvidence(BaseModel):
    candidate_events: List[UnifiedCandidateEvent]
    patient_events: List[UnifiedPatientEvent]
    concern_outcomes: List[UnifiedConcernOutcome]
    hidden_info_outcomes: List[UnifiedHiddenInfoOutcome]
    state_transitions: List[UnifiedStateTransition]
    jargon_evidence: List[JargonEvidence]
    interaction_metrics: InteractionMetrics


def _reconcile_candidate_events(events: List[CandidateEvent]) -> List[UnifiedCandidateEvent]:
    """Groups by (event, turn_index): a deterministic and a semantic entry at
    the same turn for the same event name are the SAME observed fact seen by
    two detectors -> hybrid, both evidence texts kept. An entry present from
    only one source keeps that source's provenance untouched (Step 3)."""
    groups: Dict[tuple, List[CandidateEvent]] = {}
    order: List[tuple] = []
    for ev in events:
        key = (ev.event, ev.turn_index)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(ev)

    unified: List[UnifiedCandidateEvent] = []
    for key in order:
        group = groups[key]
        sources = {ev.source for ev in group}
        if len(sources) > 1:
            provenance = PROVENANCE_HYBRID
        else:
            provenance = next(iter(sources))
        # Prefer a semantic entry's target_concern (more often explicit) but
        # never invent one -- fall back to any non-None target in the group.
        target_concern = next(
            (ev.target_concern for ev in group if ev.source == SOURCE_SEMANTIC and ev.target_concern),
            next((ev.target_concern for ev in group if ev.target_concern), None),
        )
        related_patient_turns = sorted({t for ev in group for t in ev.related_patient_turns})
        related_information_turns = sorted({t for ev in group for t in ev.related_information_turns})
        unified.append(UnifiedCandidateEvent(
            event=key[0], turn_index=key[1], target_concern=target_concern, provenance=provenance,
            evidence=[{"source": ev.source, "evidence_text": ev.evidence_text} for ev in group],
            related_patient_turns=related_patient_turns,
            related_information_turns=related_information_turns,
        ))
    return unified


def _reconcile_patient_events(events: List[PatientEvent]) -> List[UnifiedPatientEvent]:
    """Same grouping rule as candidate events. In practice deterministic and
    semantic patient events currently use distinct event names (Step 0 finding
    -- e.g. "information_revealed" vs "information_revelation_check"), so this
    rarely merges anything today; the mechanism stays general so a future
    same-name overlap is still caught as hybrid rather than silently
    duplicated."""
    groups: Dict[tuple, List[PatientEvent]] = {}
    order: List[tuple] = []
    for ev in events:
        key = (ev.event, ev.turn_index)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(ev)

    unified: List[UnifiedPatientEvent] = []
    for key in order:
        group = groups[key]
        sources = {ev.source for ev in group}
        provenance = PROVENANCE_HYBRID if len(sources) > 1 else next(iter(sources))
        primary = group[0]
        revealed = next((ev.revealed for ev in group if ev.revealed is not None), None)
        target_concern = next((ev.target_concern for ev in group if ev.target_concern), None)
        unified.append(UnifiedPatientEvent(
            event=key[0], turn_index=key[1], provenance=provenance,
            evidence_text=primary.evidence_text, revealed=revealed, target_concern=target_concern,
        ))
    return unified


def _hidden_info_provenance(candidate_detected: bool, verification_status: str) -> str:
    """Step 4/5/6 rule, made explicit:
    - no candidate -> only the deterministic rule ever ran (deterministic_rule).
    - candidate + real semantic verdict (verified_revealed/verified_not_revealed)
      -> both layers contributed to the final answer (hybrid).
    - candidate + semantic failure/not_called -> semantic never actually
      produced a usable verdict, so the final_status is still the
      deterministic/conservative one alone (deterministic_rule); the raw
      verification_status (e.g. "provider_failure") stays visible unchanged --
      never silently promoted to a verified result (Step 5)."""
    if not candidate_detected:
        return PROVENANCE_DETERMINISTIC
    if verification_status in ("verified_revealed", "verified_not_revealed"):
        return PROVENANCE_HYBRID
    return PROVENANCE_DETERMINISTIC


# Task 10 -- structured "why is the final status what it is" codes. Deliberately
# not free-form/AI-generated text: a fixed, small vocabulary a reviewer (or a
# future automated check) can match on exactly.
REASON_NOT_A_CANDIDATE = "not_a_candidate"
REASON_SEMANTIC_VERIFIED_REVEALED = "semantic_verified_revealed"
REASON_SEMANTIC_VERIFIED_NOT_REVEALED = "semantic_verified_not_revealed"
REASON_SEMANTIC_UNAVAILABLE_CONSERVATIVE_DEFAULT = "semantic_unavailable_conservative_default"


def _hidden_info_reason(candidate_detected: bool, verification_status: str) -> str:
    """Mirrors _hidden_info_provenance's own branching (Task 10 pairs with
    Task 3): candidate_detected=False means the lexical layer never even
    proposed this item, a real semantic verdict names which way it went, and
    anything else (not_called/provider_failure/parse_failure/token_limit/
    malformed_response) means semantic never produced a usable answer so the
    deterministic/conservative default is why final_status is what it is."""
    if not candidate_detected:
        return REASON_NOT_A_CANDIDATE
    if verification_status == "verified_revealed":
        return REASON_SEMANTIC_VERIFIED_REVEALED
    if verification_status == "verified_not_revealed":
        return REASON_SEMANTIC_VERIFIED_NOT_REVEALED
    return REASON_SEMANTIC_UNAVAILABLE_CONSERVATIVE_DEFAULT


def _reconcile_hidden_info(outcomes: List[HiddenInfoOutcome]) -> List[UnifiedHiddenInfoOutcome]:
    return [
        UnifiedHiddenInfoOutcome(
            item=o.item,
            candidate_detected=o.candidate_detected,
            verification_status=o.verification_status,
            final_status=o.final_status,
            provenance=_hidden_info_provenance(o.candidate_detected, o.verification_status),
            reason=_hidden_info_reason(o.candidate_detected, o.verification_status),
            turn_index=o.turn_index,
            evidence_text=o.evidence_text,
            candidate_turns=o.candidate_turns,
        )
        for o in outcomes
    ]


def _reconcile_concern(
    outcome: ConcernOutcome,
    candidate_events: List[CandidateEvent],
    patient_events: List[PatientEvent],
) -> UnifiedConcernOutcome:
    timeline: List[UnifiedConcernTimelineEntry] = []
    reopened_by_turn = {r["turn_index"]: r for r in outcome.reopened_events}

    for entry in outcome.history:
        turn_index = entry["turn_index"]
        reopen = reopened_by_turn.get(turn_index)
        timeline.append(UnifiedConcernTimelineEntry(
            turn_index=turn_index,
            status=entry["status"],
            provenance=PROVENANCE_DETERMINISTIC,
            source_event=entry.get("cause_event"),
            reopened=reopen is not None,
            reopened_from=reopen["from_status"] if reopen else None,
        ))

    for ev in candidate_events:
        if ev.source != SOURCE_SEMANTIC or ev.target_concern != outcome.concern:
            continue
        status = _CONCERN_EVENT_TO_STATUS.get(ev.event)
        if not status:
            continue
        timeline.append(UnifiedConcernTimelineEntry(
            turn_index=ev.turn_index, status=status, provenance=PROVENANCE_SEMANTIC,
            source_event=ev.event, evidence_text=ev.evidence_text,
        ))

    for ev in patient_events:
        if ev.source != SOURCE_SEMANTIC or ev.target_concern != outcome.concern:
            continue
        status = _CONCERN_EVENT_TO_STATUS.get(ev.event)
        if not status:
            continue
        timeline.append(UnifiedConcernTimelineEntry(
            turn_index=ev.turn_index, status=status, provenance=PROVENANCE_SEMANTIC,
            source_event=ev.event, evidence_text=ev.evidence_text,
        ))

    timeline.sort(key=lambda e: e.turn_index)

    believed_status = max(
        (e.status for e in timeline), key=lambda s: _BELIEVED_RANK[s], default="not_raised",
    )

    return UnifiedConcernOutcome(
        concern=outcome.concern,
        deterministic_final_status=outcome.final_status,
        unified_believed_status=believed_status,
        resolved=outcome.resolved,
        timeline=timeline,
        resolved_at_turns=outcome.resolved_at_turns,
        reopened_events=outcome.reopened_events,
    )


def reconcile_evidence(evidence: SpeakingEvidence) -> UnifiedEvidence:
    """Single entry point: same reconciliation for legacy and realtime (Step
    14) since both already funnel through the same SpeakingEvidence shape.
    With no semantic entries present (deterministic-only evidence), every
    output item is trivially provenance=deterministic_rule -- reconciling an
    all-deterministic SpeakingEvidence is a safe no-op, not a special case."""
    return UnifiedEvidence(
        candidate_events=_reconcile_candidate_events(evidence.candidate_events),
        patient_events=_reconcile_patient_events(evidence.patient_events),
        concern_outcomes=[
            _reconcile_concern(o, evidence.candidate_events, evidence.patient_events)
            for o in evidence.concern_outcomes
        ],
        hidden_info_outcomes=_reconcile_hidden_info(evidence.hidden_info_outcomes),
        state_transitions=[
            UnifiedStateTransition(
                field=t.field, before=t.before, after=t.after,
                cause_event=t.cause_event, turn_index=t.turn_index,
            )
            for t in evidence.state_transitions
        ],
        jargon_evidence=evidence.jargon_evidence,
        interaction_metrics=evidence.interaction_metrics,
    )


# ── Task 11: evidence integrity checks ───────────────────────────────────
# Catches internally IMPOSSIBLE combinations only -- never a legitimate
# "belief vs official state" difference (e.g. provider_failure + final=hidden
# is the correct conservative default, not a violation; see
# _hidden_info_provenance/_hidden_info_reason above for why that combination
# is expected and unflagged here).

VIOLATION_VERIFIED_WITHOUT_CANDIDATE = "verified_without_candidate"
VIOLATION_VERIFIED_REVEALED_BUT_FINAL_HIDDEN = "verified_revealed_but_final_hidden"
VIOLATION_VERIFIED_NOT_REVEALED_BUT_FINAL_REVEALED = "verified_not_revealed_but_final_revealed"

_REAL_VERDICTS = {"verified_revealed", "verified_not_revealed"}


class IntegrityViolation(BaseModel):
    item: str
    violation: str
    detail: str


def _check_hidden_info_integrity(outcome: UnifiedHiddenInfoOutcome) -> Optional[IntegrityViolation]:
    if not outcome.candidate_detected and outcome.verification_status in _REAL_VERDICTS:
        # hidden_info_hints only ever verifies items the deterministic layer
        # already flagged as a keyword candidate (see its own docstring) --
        # a real verdict with no candidate can never happen honestly.
        return IntegrityViolation(
            item=outcome.item, violation=VIOLATION_VERIFIED_WITHOUT_CANDIDATE,
            detail=f"verification_status={outcome.verification_status!r} but candidate_detected is False",
        )
    if outcome.verification_status == "verified_revealed" and outcome.final_status == "hidden":
        return IntegrityViolation(
            item=outcome.item, violation=VIOLATION_VERIFIED_REVEALED_BUT_FINAL_HIDDEN,
            detail="semantic verification confirmed the reveal but final_status is still hidden",
        )
    if outcome.verification_status == "verified_not_revealed" and outcome.final_status == "revealed":
        return IntegrityViolation(
            item=outcome.item, violation=VIOLATION_VERIFIED_NOT_REVEALED_BUT_FINAL_REVEALED,
            detail="semantic verification rejected the reveal but final_status is revealed",
        )
    return None


def check_integrity(evidence: UnifiedEvidence) -> List[IntegrityViolation]:
    """Read-only audit over an already-reconciled UnifiedEvidence -- never
    raises, never mutates. An empty list means no impossible combination was
    found (the overwhelmingly common, expected case); it does not mean the
    evidence is otherwise correct."""
    violations: List[IntegrityViolation] = []
    for outcome in evidence.hidden_info_outcomes:
        v = _check_hidden_info_integrity(outcome)
        if v:
            violations.append(v)
    return violations
