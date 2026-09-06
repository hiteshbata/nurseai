"""Active Listening / Interruption (D1) evidence (Step 21J).

    D1: "facilitating the patient's narrative with active listening
        techniques, minimising interruption" (examiner_input.INDICATOR_TEXT)

This module is the SINGLE canonical computation for D1 evidence --
criterion_evidence._map_d1 calls build_d1_listening_evidence() directly and
only converts its result into EvidenceRefs (via the existing
_d4_d5_event_refs helper every other indicator already uses). There is no
second D1 computation anywhere else (Step 13 of this task's spec).

Two kinds of evidence, both reuse-only, never a new detector:

1. active_listening_support -- the already-detected B2/D4/D5/A2 events
   (cue_response, clarification_request, summary_statement, reflective_
   response, attentive_acknowledgement, and their _uncertain variants)
   filtered down and re-tagged as D1 support. Nothing here is recomputed;
   select_d1_support_events only filters UnifiedCandidateEvent by name.
   IMPORTANT: presence of this evidence is NOT "the candidate demonstrated
   excellent active listening" -- it is surface-form evidence a future
   examiner may weigh, same MISSING vs NEGATIVE rule as every other
   indicator in criterion_evidence.py.

2. unaddressed_patient_contributions -- a patient cue (concern_raised /
   emotional_trigger_fired, already in UnifiedPatientEvent) whose turn_index
   never appears in any cue_response/cue_response_uncertain event's
   related_patient_turns. Pure set-difference over two already-computed
   series (Step 6/10) -- no keyword matching, no semantic inference, no
   invented relationship.

Interruption evidence stays session-level only (Step 7/8/I): the realtime
Interrupted event (services/realtime/events.py) carries no timestamp and no
turn index, so no interruption can ever be attributed to a specific turn.
interruption_direction is only ever "candidate_over_patient" -- the sole
direction the realtime event model represents (an adapter fires Interrupted
only when candidate audio starts while patient audio is still playing;
no adapter has any concept of the reverse) -- and is only set when
interrupted_count > 0. A count of 0 is a real, known fact ("no interruption
this session"), not evidence of good listening: direction stays None and no
positive interpretation is attached. interrupted_count is None entirely on
legacy (text-only) sessions, where no interruption telemetry exists at all;
callers must keep treating that as REASON_NO_INTERRUPTION_METRIC (unchanged
in criterion_evidence.py), never as a synonym for zero.

LIMITATIONS: see the LIMITATIONS list below -- also surfaced on
D1ListeningEvidence.limitations so any caller building this model directly
sees them without reading this docstring.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from app.services.cue_response_evidence import CUE_EVENT_TYPES
from app.services.evidence_reconciliation import UnifiedCandidateEvent, UnifiedPatientEvent

PROVENANCE_DETERMINISTIC = "deterministic_rule"
PROVENANCE_DIRECT = "direct"
EVIDENCE_LEVEL_DETERMINISTIC = "L2_deterministic"
EVIDENCE_LEVEL_DIRECT = "L1_direct"

DIRECTION_CANDIDATE_OVER_PATIENT = "candidate_over_patient"
TURN_ATTRIBUTION_SESSION_LEVEL_ONLY = "session_level_only"

# Reused event names -> the criterion each was originally detected for
# (Step 19: legitimate multi-criterion overlap, never deduplicated).
D1_SUPPORT_EVENT_SOURCE_CRITERIA = {
    "cue_response": "B2", "cue_response_uncertain": "B2",
    "clarification_request": "D4", "clarification_uncertain": "D4",
    "summary_statement": "D5", "summary_uncertain": "D5", "summary_check": "D5",
    "reflective_response": "A2", "reflective_response_uncertain": "A2",
    "attentive_acknowledgement": "A2", "attentive_acknowledgement_uncertain": "A2",
}
D1_SUPPORT_EVENT_NAMES = set(D1_SUPPORT_EVENT_SOURCE_CRITERIA)

# Only these two establish "this cue got a next-turn pairing" -- the exact
# event names cue_response_evidence.py itself emits for a paired cue.
_CUE_RESPONSE_EVENT_NAMES = {"cue_response", "cue_response_uncertain"}

LIMITATIONS: List[str] = [
    "Reused support evidence (cue_response/clarification/summary/acknowledgement/"
    "reflective_response) reflects surface-form engagement already detected for "
    "another criterion -- its presence here is supporting evidence only, never "
    "proof of effective active listening.",
    "unaddressed_patient_contribution only covers patient turns the system "
    "already treats as a cue (concern_raised/emotional_trigger_fired) and "
    "inherits cue_response_evidence's own adjacency-only pairing limitation -- "
    "it is not a general 'candidate ignored the patient' detector.",
    "Interruption evidence is session-level only -- the realtime Interrupted "
    "event carries no timestamp or turn index, so no interruption can be "
    "attributed to a specific turn. interruption_direction is only ever "
    "'candidate_over_patient' (the only direction the realtime event model "
    "represents) and only set when interrupted_count > 0; a patient-interrupts-"
    "candidate direction is never fabricated because no such event exists.",
    "Legacy (text-chat) sessions have no interruption telemetry at all -- "
    "interrupted_count is None there, so interruption_evidence is None "
    "(absent), never a fabricated zero.",
]


class InterruptionEvidence(BaseModel):
    session_interruption_metric: int
    interruption_direction: Optional[str] = None
    turn_attribution: str = TURN_ATTRIBUTION_SESSION_LEVEL_ONLY
    provenance: str = PROVENANCE_DIRECT
    evidence_level: str = EVIDENCE_LEVEL_DIRECT


class D1ListeningEvidence(BaseModel):
    active_listening_support: List[UnifiedCandidateEvent] = []
    unaddressed_patient_contributions: List[UnifiedPatientEvent] = []
    interruption_evidence: Optional[InterruptionEvidence] = None
    limitations: List[str] = LIMITATIONS


def select_d1_support_events(candidate_events: List[UnifiedCandidateEvent]) -> List[UnifiedCandidateEvent]:
    """Filters already-reconciled candidate_events down to the D1-relevant
    subset (B2/D4/D5/A2 events already detected elsewhere). Never recomputes
    a detector -- pure filter."""
    return [ev for ev in candidate_events if ev.event in D1_SUPPORT_EVENT_NAMES]


def find_unaddressed_patient_contributions(
    patient_events: List[UnifiedPatientEvent],
    candidate_events: List[UnifiedCandidateEvent],
) -> List[UnifiedPatientEvent]:
    """A cue (concern_raised/emotional_trigger_fired) whose turn_index never
    appears in any cue_response/cue_response_uncertain event's
    related_patient_turns. Pure set difference over two already-computed
    series -- never a new keyword detector, never an invented relationship."""
    responded_turns = {
        turn
        for ev in candidate_events if ev.event in _CUE_RESPONSE_EVENT_NAMES
        for turn in ev.related_patient_turns
    }
    return [
        pe for pe in patient_events
        if pe.event in CUE_EVENT_TYPES and pe.turn_index not in responded_turns
    ]


def build_interruption_evidence(interrupted_count: Optional[int]) -> Optional[InterruptionEvidence]:
    """None (no metric at all, e.g. legacy pipeline) stays None -- never a
    fabricated zero. 0 is a real known fact but attaches no direction (no
    positive listening interpretation). >0 gets the only direction the
    realtime event model can represent."""
    if interrupted_count is None:
        return None
    direction = DIRECTION_CANDIDATE_OVER_PATIENT if interrupted_count > 0 else None
    return InterruptionEvidence(
        session_interruption_metric=interrupted_count,
        interruption_direction=direction,
    )


def build_d1_listening_evidence(
    candidate_events: List[UnifiedCandidateEvent],
    patient_events: List[UnifiedPatientEvent],
    interrupted_count: Optional[int] = None,
) -> D1ListeningEvidence:
    """Canonical D1 evidence assembly. Pure/deterministic: same inputs always
    produce the same output. No I/O, no model calls, no DB."""
    return D1ListeningEvidence(
        active_listening_support=select_d1_support_events(candidate_events),
        unaddressed_patient_contributions=find_unaddressed_patient_contributions(patient_events, candidate_events),
        interruption_evidence=build_interruption_evidence(interrupted_count),
    )


if __name__ == "__main__":
    ack = UnifiedCandidateEvent(
        event="attentive_acknowledgement", turn_index=1, provenance="deterministic_rule",
        evidence=[{"source": "deterministic_rule", "evidence_text": "I see."}],
    )
    clarify = UnifiedCandidateEvent(
        event="clarification_request", turn_index=3, provenance="deterministic_rule",
        evidence=[{"source": "deterministic_rule", "evidence_text": "What do you mean by that?"}],
    )
    unrelated = UnifiedCandidateEvent(
        event="open_question", turn_index=5, provenance="deterministic_rule",
        evidence=[{"source": "deterministic_rule", "evidence_text": "How are you feeling?"}],
    )
    support = select_d1_support_events([ack, clarify, unrelated])
    assert {ev.event for ev in support} == {"attentive_acknowledgement", "clarification_request"}

    cue = UnifiedPatientEvent(event="concern_raised", turn_index=0, provenance="deterministic_rule", evidence_text="pain")
    responded = UnifiedCandidateEvent(
        event="cue_response", turn_index=1, provenance="deterministic_rule",
        evidence=[{"source": "deterministic_rule", "evidence_text": "let's talk about that"}],
        related_patient_turns=[0],
    )
    assert find_unaddressed_patient_contributions([cue], [responded]) == []
    assert find_unaddressed_patient_contributions([cue], []) == [cue]

    assert build_interruption_evidence(None) is None
    zero = build_interruption_evidence(0)
    assert zero.session_interruption_metric == 0 and zero.interruption_direction is None
    two = build_interruption_evidence(2)
    assert two.interruption_direction == DIRECTION_CANDIDATE_OVER_PATIENT
    assert two.turn_attribution == TURN_ATTRIBUTION_SESSION_LEVEL_ONLY

    bundle = build_d1_listening_evidence([ack, clarify, responded], [cue], interrupted_count=1)
    assert len(bundle.active_listening_support) == 3
    assert bundle.unaddressed_patient_contributions == []
    assert bundle.interruption_evidence.interruption_direction == DIRECTION_CANDIDATE_OVER_PATIENT

    # Determinism.
    bundle2 = build_d1_listening_evidence([ack, clarify, responded], [cue], interrupted_count=1)
    assert bundle == bundle2

    print("d1_listening_evidence self-check OK")
