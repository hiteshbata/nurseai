"""Criterion Evidence Mapper (Step 20).

Organizes ExaminerInput's already-computed evidence against all 9 official
OET Speaking criteria and all 20 clinical indicators (A1-A4, B1-B3, C1-C3,
D1-D5, E1-E5). Pure, deterministic, offline: no model calls, no DB, no
mutation of ExaminerInput/UnifiedEvidence/SpeakingEvidence/PatientState.

    ExaminerInput -> map_criterion_evidence() -> CriterionEvidenceMap
                                                    -> [FUTURE] Shadow Examiner

HARD RULE (Step 18/19/33): this module answers "what evidence exists for
this criterion/indicator, and what's missing" -- never "was the candidate
good". There is no score/band/pass-fail field anywhere below, and event
counts (already on UnifiedEvidence.interaction_metrics, not duplicated
here) are never used as a quality threshold -- evidence_quality reflects
COVERAGE (does a detector exist, did it produce anything) not performance.

MISSING vs NEGATIVE (Step 15): an indicator with no dedicated detector gets
a `gaps` entry and evidence_quality INSUFFICIENT/PARTIAL -- never a lower
score, because there is no score field to lower. An indicator whose
detector genuinely found nothing this session (LIMITED) is structurally
distinct from one with no detector at all (INSUFFICIENT/PARTIAL) -- see
`_quality`.

MAPPING RULES ARE STATIC (Step 25): every indicator has one explicit
`_map_*` function below reading named ExaminerInput/UnifiedEvidence fields
-- no opaque heuristic, no LLM, so "why was this evidence attached to this
criterion" is always answerable by reading the one function.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.services.evidence_reconciliation import (
    UnifiedCandidateEvent,
    UnifiedConcernOutcome,
    UnifiedPatientEvent,
    UnifiedStateTransition,
)
from app.services.examiner_input import (
    AVAILABILITY_INSUFFICIENT,
    AVAILABILITY_LIMITED,
    AVAILABILITY_PARTIAL,
    AVAILABILITY_STRONG,
    CRITERION_APPROPRIATENESS_OF_LANGUAGE,
    CRITERION_FLUENCY,
    CRITERION_INFORMATION_GATHERING,
    CRITERION_INFORMATION_GIVING,
    CRITERION_INTELLIGIBILITY,
    CRITERION_PATIENT_PERSPECTIVE,
    CRITERION_PROVIDING_STRUCTURE,
    CRITERION_RELATIONSHIP_BUILDING,
    CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION,
    REASON_JARGON_DETECTOR_PARTIAL_COVERAGE,
    REASON_NO_GRAMMAR_DETECTOR,
    EvidenceGap,
    ExaminerInput,
    TranscriptTurn,
)
from app.services import d1_listening_evidence
from app.services.speaking_evidence import SOURCE_DETERMINISTIC

# ── Evidence levels (Step 6) ──────────────────────────────────────────────
LEVEL_L1_DIRECT = "L1_direct"
LEVEL_L2_DETERMINISTIC = "L2_deterministic"
LEVEL_L3_SEMANTIC = "L3_semantic"
LEVEL_L4_PATIENT_OUTCOME = "L4_patient_outcome"

# ── Provenance (Step 5) ────────────────────────────────────────────────────
# Reuses SOURCE_DETERMINISTIC/SOURCE_SEMANTIC/"hybrid" (via each UnifiedEvidence
# item's own .provenance/.source field) for anything derived from detectors.
# PROVENANCE_DIRECT is new here: for raw transcript/session-metric evidence
# with no detector involved at all (no equivalent constant exists upstream).
PROVENANCE_DIRECT = "direct"

# ── Gap reason codes owned by this module (Step 24) ───────────────────────
# One per indicator/criterion with no dedicated detector today. Where an
# identical-meaning code already exists on examiner_input.py (appropriateness/
# grammar), that constant is reused above instead of re-spelled here (Step 2).
REASON_NO_INTERRUPTION_METRIC = "NO_INTERRUPTION_METRIC"
REASON_NO_AUDIO_INTELLIGIBILITY = "NO_AUDIO_INTELLIGIBILITY"
REASON_NO_AUDIO_FLUENCY = "NO_AUDIO_FLUENCY"


# ── Models (Step 1/4/22/23) ────────────────────────────────────────────────

class EvidenceRef(BaseModel):
    source: str  # "transcript" | "candidate_event" | "patient_event" | "state_transition" | "concern_timeline" | "session_metrics" | "pronunciation" | "jargon_evidence"
    evidence_id: str
    turn_index: Optional[int] = None
    evidence_text: str
    provenance: str  # deterministic_rule | semantic_model | direct
    evidence_level: str  # LEVEL_L1_DIRECT | LEVEL_L2_DETERMINISTIC | LEVEL_L3_SEMANTIC | LEVEL_L4_PATIENT_OUTCOME
    related_patient_turn: Optional[int] = None
    metadata: Dict[str, Any] = {}


class IndicatorEvidence(BaseModel):
    indicator: str
    evidence_refs: List[EvidenceRef] = []
    evidence_quality: str
    gaps: List[EvidenceGap] = []


class ClinicalCriterionBundle(BaseModel):
    criterion: str
    family: str = "clinical"
    indicators: List[IndicatorEvidence]
    criterion_evidence_quality: str


class LinguisticCriterionBundle(BaseModel):
    criterion: str
    family: str = "linguistic"
    evidence_refs: List[EvidenceRef] = []
    evidence_levels: List[str] = []
    audio_required: bool
    audio_available: bool
    evidence_quality: str
    gaps: List[EvidenceGap] = []


class CriterionEvidenceMap(BaseModel):
    clinical: List[ClinicalCriterionBundle]
    linguistic: List[LinguisticCriterionBundle]


# ── Evidence-quality (Step 14/15) ─────────────────────────────────────────
# Coverage only, never performance -- see module docstring.
_QUALITY_RANK = {
    AVAILABILITY_INSUFFICIENT: 0, AVAILABILITY_LIMITED: 1,
    AVAILABILITY_PARTIAL: 2, AVAILABILITY_STRONG: 3,
}


def _quality(evidence_refs: List[EvidenceRef], has_detector_gap: bool) -> str:
    if has_detector_gap:
        return AVAILABILITY_PARTIAL if evidence_refs else AVAILABILITY_INSUFFICIENT
    return AVAILABILITY_STRONG if evidence_refs else AVAILABILITY_LIMITED


def _worst_quality(qualities: List[str]) -> str:
    return min(qualities, key=lambda q: _QUALITY_RANK[q])


def _build_indicator(
    criterion: str, indicator: str, refs: List[EvidenceRef],
    reason_code: Optional[str], missing_evidence_type: str,
) -> IndicatorEvidence:
    quality = _quality(refs, reason_code is not None)
    gaps = (
        [EvidenceGap(criterion=criterion, indicator=indicator, reason_code=reason_code,
                      missing_evidence_type=missing_evidence_type, availability=quality)]
        if reason_code else []
    )
    return IndicatorEvidence(indicator=indicator, evidence_refs=refs, evidence_quality=quality, gaps=gaps)


# ── Evidence-source helpers (Step 7-13) ───────────────────────────────────

def _transcript_refs(transcript: List[TranscriptTurn]) -> List[EvidenceRef]:
    return [
        EvidenceRef(
            source="transcript", evidence_id=f"turn_{t.turn_index}", turn_index=t.turn_index,
            evidence_text=t.content, provenance=PROVENANCE_DIRECT, evidence_level=LEVEL_L1_DIRECT,
        )
        for t in transcript
    ]


def _level_for_provenance(provenance: str) -> str:
    return LEVEL_L3_SEMANTIC if provenance != SOURCE_DETERMINISTIC else LEVEL_L2_DETERMINISTIC


def _candidate_event_refs(events: List[UnifiedCandidateEvent], event_names: set) -> List[EvidenceRef]:
    """One EvidenceRef PER CONTRIBUTING SOURCE inside a hybrid event, not one
    per event (Step 26): a deterministic+semantic hybrid keeps both sources
    visible and un-merged rather than picking a winner."""
    refs: List[EvidenceRef] = []
    for ev in events:
        if ev.event not in event_names:
            continue
        for entry in ev.evidence:
            refs.append(EvidenceRef(
                source="candidate_event", evidence_id=ev.event, turn_index=ev.turn_index,
                evidence_text=entry["evidence_text"], provenance=entry["source"],
                evidence_level=_level_for_provenance(entry["source"]),
                metadata={"target_concern": ev.target_concern} if ev.target_concern else {},
            ))
    return refs


def _patient_event_refs(events: List[UnifiedPatientEvent], event_names: set) -> List[EvidenceRef]:
    """Patient events are always L4 (patient outcome) regardless of the
    detector's own provenance tag -- Step 16: this is something the
    simulated PATIENT did/felt, never the candidate's own action."""
    refs: List[EvidenceRef] = []
    for ev in events:
        if ev.event not in event_names:
            continue
        meta: Dict[str, Any] = {}
        if ev.revealed is not None:
            meta["revealed"] = ev.revealed
        refs.append(EvidenceRef(
            source="patient_event", evidence_id=ev.event, turn_index=ev.turn_index,
            evidence_text=ev.evidence_text, provenance=ev.provenance,
            evidence_level=LEVEL_L4_PATIENT_OUTCOME, metadata=meta,
        ))
    return refs


def _state_transition_refs(transitions: List[UnifiedStateTransition], field_prefix: str) -> List[EvidenceRef]:
    refs: List[EvidenceRef] = []
    for t in transitions:
        if not t.field.startswith(field_prefix):
            continue
        meta = {"cause_event": t.cause_event} if t.cause_event else {}
        refs.append(EvidenceRef(
            source="state_transition", evidence_id=t.field, turn_index=t.turn_index,
            evidence_text=f"{t.before} -> {t.after}", provenance=t.provenance,
            evidence_level=LEVEL_L4_PATIENT_OUTCOME, metadata=meta,
        ))
    return refs


def _concern_timeline_refs(outcomes: List[UnifiedConcernOutcome], statuses: set) -> List[EvidenceRef]:
    """Multi-turn evidence (Step 17): one ref per matching timeline entry,
    turn_index preserved, so a sequence (raised -> explored -> addressed)
    stays reconstructable rather than collapsing to one unsupported claim."""
    refs: List[EvidenceRef] = []
    for outcome in outcomes:
        for entry in outcome.timeline:
            if entry.status not in statuses:
                continue
            refs.append(EvidenceRef(
                source="concern_timeline", evidence_id=f"{outcome.concern}::{entry.status}",
                turn_index=entry.turn_index, evidence_text=entry.evidence_text or outcome.concern,
                provenance=entry.provenance, evidence_level=LEVEL_L4_PATIENT_OUTCOME,
                metadata={"concern": outcome.concern, "reopened": entry.reopened},
            ))
    return refs


def _d4_d5_event_refs(events: List[UnifiedCandidateEvent], event_names: set) -> List[EvidenceRef]:
    """D4/D5 evidence (Step 21D) carries related_patient_turns -- unlike
    every other candidate event, one EvidenceRef is emitted PER related
    patient turn so each stays independently traceable (mirrors
    _concern_timeline_refs' "one ref per timeline entry" rule), falling
    back to a single unlinked ref when no relationship could be defended
    (Step 2 of that task's spec: never invent one)."""
    refs: List[EvidenceRef] = []
    for ev in events:
        if ev.event not in event_names:
            continue
        for entry in ev.evidence:
            for related_turn in (ev.related_patient_turns or [None]):
                refs.append(EvidenceRef(
                    source="candidate_event", evidence_id=ev.event, turn_index=ev.turn_index,
                    evidence_text=entry["evidence_text"], provenance=entry["source"],
                    evidence_level=_level_for_provenance(entry["source"]),
                    related_patient_turn=related_turn,
                ))
    return refs


def _information_giving_event_refs(events: List[UnifiedCandidateEvent], event_names: set) -> List[EvidenceRef]:
    """E2/E3 evidence (Step 21E) carries related_patient_turns AND/OR
    related_information_turns. One EvidenceRef per related PATIENT turn
    (same rule as _d4_d5_event_refs, falling back to a single unlinked ref
    when there is none), with related_information_turns surfaced in
    `metadata` rather than a new EvidenceRef field -- avoids growing the
    EvidenceRef schema for a link that's just extra context, not a second
    axis of "which turn does this ref represent"."""
    refs: List[EvidenceRef] = []
    for ev in events:
        if ev.event not in event_names:
            continue
        metadata = {"related_information_turns": ev.related_information_turns} if ev.related_information_turns else {}
        for entry in ev.evidence:
            for related_turn in (ev.related_patient_turns or [None]):
                refs.append(EvidenceRef(
                    source="candidate_event", evidence_id=ev.event, turn_index=ev.turn_index,
                    evidence_text=entry["evidence_text"], provenance=entry["source"],
                    evidence_level=_level_for_provenance(entry["source"]),
                    related_patient_turn=related_turn, metadata=dict(metadata),
                ))
    return refs


# ── A. RELATIONSHIP BUILDING (Step 8) ─────────────────────────────────────

def _map_a1(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21G: opening_greeting/opening_introduction/opening_role_identification/
    opening_purpose_setting (opening_evidence.detect_opening_events) replace
    the placeholder first-transcript-turn evidence. No detector gap anymore --
    an empty result this session is AVAILABILITY_LIMITED via _quality's
    no-refs branch, not a missing-detector gap: see this module's docstring
    on MISSING vs NEGATIVE."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _candidate_event_refs(
        ue.candidate_events,
        {"opening_greeting", "opening_introduction", "opening_role_identification", "opening_purpose_setting"},
    )
    return _build_indicator(CRITERION_RELATIONSHIP_BUILDING, "A1", refs, None, "")


def _map_a2(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21H: attentive_acknowledgement/attentive_acknowledgement_uncertain
    (explicit interpersonal receipt of what the patient said) +
    reflective_response/reflective_response_uncertain (paraphrase of the
    immediately preceding patient turn, reuses _d4_d5_event_refs' generic
    per-related-turn expansion, same as D4/D5/B2) + dismissive_response
    (Step 7: reused directly, not re-detected). understanding_checked is
    deliberately no longer mapped here (E4-only now) -- it's a clinical-
    comprehension-check phrase, not genuine A2 signal, and was only ever a
    placeholder proxy before this step's dedicated detectors existed.

    interrupted_count (Step 6) is session/connection-metric data, not
    present in the transcript -- wired in directly here, identical in shape
    to _map_d1's own handling of the same field, rather than forced into
    attentiveness_evidence.py's transcript-only detector model (see that
    module's docstring). Its absence is the only remaining detector gap for
    A2 -- an empty acknowledgement/reflective/dismissive result this session
    is AVAILABILITY_LIMITED via _quality's no-refs branch, not a
    missing-detector gap: see this module's docstring on MISSING vs
    NEGATIVE."""
    ue = ei.clinical_evidence.unified_evidence
    refs = (
        _candidate_event_refs(
            ue.candidate_events,
            {"attentive_acknowledgement", "attentive_acknowledgement_uncertain", "dismissive_response"},
        )
        + _d4_d5_event_refs(ue.candidate_events, {"reflective_response", "reflective_response_uncertain"})
    )
    interrupted = ei.session_context.interrupted_count
    if interrupted is not None:
        refs.append(EvidenceRef(
            source="session_metrics", evidence_id="interrupted_count", turn_index=None,
            evidence_text=str(interrupted), provenance=PROVENANCE_DIRECT, evidence_level=LEVEL_L1_DIRECT,
            metadata={"interrupted_count": interrupted},
        ))
        return _build_indicator(CRITERION_RELATIONSHIP_BUILDING, "A2", refs, None, "")
    return _build_indicator(
        CRITERION_RELATIONSHIP_BUILDING, "A2", refs,
        REASON_NO_INTERRUPTION_METRIC, "interruption_metric",
    )


def _map_a3(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21I: potentially_judgmental/supportive_nonjudgmental/
    uncertain_judgment (nonjudgmental_evidence.detect_nonjudgmental_events)
    replace the former no-detector gap. All three event types can carry
    related_patient_turns (context linkage to the immediately preceding
    patient turn), so all three route through the same _d4_d5_event_refs
    per-related-turn expansion (mapping-consistency requirement of this
    task's spec) -- no event type gets a different helper merely because an
    earlier detector in this family happened to use one. No detector gap
    anymore -- an empty result this session is AVAILABILITY_LIMITED via
    _quality's no-refs branch, not a missing-detector gap: see this module's
    docstring on MISSING vs NEGATIVE."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _d4_d5_event_refs(
        ue.candidate_events,
        {"potentially_judgmental", "supportive_nonjudgmental", "uncertain_judgment"},
    )
    return _build_indicator(CRITERION_RELATIONSHIP_BUILDING, "A3", refs, None, "")


def _map_a4(ei: ExaminerInput) -> IndicatorEvidence:
    ue = ei.clinical_evidence.unified_evidence
    refs = (
        _candidate_event_refs(ue.candidate_events, {"empathy_acknowledgement"})
        + _state_transition_refs(ue.state_transitions, "current_emotion")
        + _patient_event_refs(ue.patient_events, {"emotional_trigger_fired"})
    )
    return _build_indicator(CRITERION_RELATIONSHIP_BUILDING, "A4", refs, None, "")


# ── B. PATIENT PERSPECTIVE (Step 9) ───────────────────────────────────────

def _map_b1(ei: ExaminerInput) -> IndicatorEvidence:
    ue = ei.clinical_evidence.unified_evidence
    refs = (
        _candidate_event_refs(ue.candidate_events, {"concern_exploration"})
        + _patient_event_refs(ue.patient_events, {"concern_raised"})
        + _concern_timeline_refs(ue.concern_outcomes, {"raised", "explored"})
    )
    return _build_indicator(CRITERION_PATIENT_PERSPECTIVE, "B1", refs, None, "")


def _map_b2(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21F: cue_response/cue_response_uncertain (the patient cue's
    immediate-next-turn response, paired via related_patient_turns back to
    the cue -- reuses _d4_d5_event_refs' generic per-related-turn expansion,
    same as D4/D5) alongside the cue itself (concern_raised/emotional_
    trigger_fired) and its concern-status transition. No detector gap
    anymore -- an empty result this session is AVAILABILITY_LIMITED via
    _quality's no-refs branch, not a missing-detector gap."""
    ue = ei.clinical_evidence.unified_evidence
    refs = (
        _patient_event_refs(ue.patient_events, {"concern_raised", "emotional_trigger_fired"})
        + _state_transition_refs(ue.state_transitions, "concern_status:")
        + _d4_d5_event_refs(ue.candidate_events, {"cue_response", "cue_response_uncertain"})
    )
    return _build_indicator(CRITERION_PATIENT_PERSPECTIVE, "B2", refs, None, "")


def _map_b3(ei: ExaminerInput) -> IndicatorEvidence:
    ue = ei.clinical_evidence.unified_evidence
    refs = (
        _candidate_event_refs(ue.candidate_events, {"concern_addressing"})
        + _concern_timeline_refs(ue.concern_outcomes, {"addressed", "resolved", "resolved_signal"})
        + _patient_event_refs(ue.patient_events, {"concern_resolution_signal"})
    )
    return _build_indicator(CRITERION_PATIENT_PERSPECTIVE, "B3", refs, None, "")


# ── C. PROVIDING STRUCTURE (Step 10) ──────────────────────────────────────

def _map_c1(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21C: consultation_sequence_marker/_partial (explicit sequencing
    with a recognized consultation verb) plus consultation_sequence_uncertain
    (marker present, verb/modal framing ambiguous -- Step 13, kept as
    evidence rather than dropped). No detector gap anymore (Step 17/18) --
    an empty result this session is AVAILABILITY_LIMITED via _quality's
    no-refs branch, not a missing-detector gap: see this module's docstring
    on MISSING vs NEGATIVE."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _candidate_event_refs(
        ue.candidate_events,
        {"consultation_sequence_marker", "consultation_sequence_marker_partial", "consultation_sequence_uncertain"},
    )
    return _build_indicator(CRITERION_PROVIDING_STRUCTURE, "C1", refs, None, "")


def _map_c2(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21B: signposting_detected/signposting_uncertain (both C2 --
    Step 14, uncertain evidence is still evidence, never dropped) plus
    topic_transition_detected (Step 4)."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _candidate_event_refs(
        ue.candidate_events, {"signposting_detected", "signposting_uncertain", "topic_transition_detected"},
    )
    return _build_indicator(CRITERION_PROVIDING_STRUCTURE, "C2", refs, None, "")


def _map_c3(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21B: organization_marker/organization_marker_partial -- refs stay
    turn_index-ordered (via _candidate_event_refs), which is how a sequence
    like "First... Second... Finally..." survives without a separate
    sequence object (see structure_evidence.py's module docstring)."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _candidate_event_refs(ue.candidate_events, {"organization_marker", "organization_marker_partial"})
    return _build_indicator(CRITERION_PROVIDING_STRUCTURE, "C3", refs, None, "")


# ── D. INFORMATION GATHERING (Step 11) ────────────────────────────────────

def _map_d1(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21J: ONE canonical computation
    (d1_listening_evidence.build_d1_listening_evidence) -- this function only
    turns that result into EvidenceRefs, never recomputes it.

    active_listening_support reuses already-detected B2/D4/D5/A2 events
    (cue_response, clarification_request, summary_statement, reflective_
    response, attentive_acknowledgement, and their _uncertain variants),
    tagged as D1 support -- never auto-interpreted as "excellent active
    listening" on its own (see d1_listening_evidence's module docstring).

    unaddressed_patient_contribution is pure set-difference over already-
    detected cue (concern_raised/emotional_trigger_fired) and cue_response
    events -- no new keyword detector, deterministic_rule/L2_deterministic.

    Interruption evidence stays session-level (interrupted_count), with
    turn_attribution always session_level_only and interruption_direction
    only ever candidate_over_patient when count > 0 -- count == 0 attaches
    no direction and is not treated as positive listening evidence.
    REASON_NO_INTERRUPTION_METRIC is unchanged: it still fires only when
    interrupted_count is None (legacy pipeline), never when it's 0."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _transcript_refs(ei.transcript)

    d1 = d1_listening_evidence.build_d1_listening_evidence(
        ue.candidate_events, ue.patient_events, ei.session_context.interrupted_count,
    )

    support_names = {ev.event for ev in d1.active_listening_support}
    refs += _d4_d5_event_refs(ue.candidate_events, support_names)

    refs += [
        EvidenceRef(
            source="patient_event", evidence_id="unaddressed_patient_contribution",
            turn_index=pe.turn_index, evidence_text=pe.evidence_text,
            provenance=SOURCE_DETERMINISTIC, evidence_level=LEVEL_L2_DETERMINISTIC,
            metadata={"cue_event": pe.event},
        )
        for pe in d1.unaddressed_patient_contributions
    ]

    if d1.interruption_evidence is not None:
        ie = d1.interruption_evidence
        refs.append(EvidenceRef(
            source="session_metrics", evidence_id="interrupted_count", turn_index=None,
            evidence_text=str(ie.session_interruption_metric), provenance=ie.provenance,
            evidence_level=ie.evidence_level,
            metadata={
                "interrupted_count": ie.session_interruption_metric,
                "interruption_direction": ie.interruption_direction,
                "turn_attribution": ie.turn_attribution,
            },
        ))
        return _build_indicator(CRITERION_INFORMATION_GATHERING, "D1", refs, None, "")
    return _build_indicator(
        CRITERION_INFORMATION_GATHERING, "D1", refs,
        REASON_NO_INTERRUPTION_METRIC, "interruption_metric",
    )


def _map_d2(ei: ExaminerInput) -> IndicatorEvidence:
    ue = ei.clinical_evidence.unified_evidence
    refs = _candidate_event_refs(ue.candidate_events, {"open_question", "closed_question"})
    return _build_indicator(CRITERION_INFORMATION_GATHERING, "D2", refs, None, "")


def _map_d3(ei: ExaminerInput) -> IndicatorEvidence:
    ue = ei.clinical_evidence.unified_evidence
    refs = _candidate_event_refs(ue.candidate_events, {"compound_question", "leading_question"})
    return _build_indicator(CRITERION_INFORMATION_GATHERING, "D3", refs, None, "")


def _map_d4(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21D: clarification_request (explicit "what do you mean"/
    "clarify" wording) + clarification_uncertain (anaphoric "tell me more
    about that/this" -- Step 3/16, kept as evidence rather than dropped).
    No detector gap anymore (Step 17/18) -- an empty result this session is
    AVAILABILITY_LIMITED via _quality's no-refs branch, not a missing-
    detector gap: see this module's docstring on MISSING vs NEGATIVE."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _d4_d5_event_refs(ue.candidate_events, {"clarification_request", "clarification_uncertain"})
    return _build_indicator(CRITERION_INFORMATION_GATHERING, "D4", refs, None, "")


def _map_d5(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21D: summary_statement/summary_uncertain (Step 4/7) +
    summary_check (Step 6 -- correction-inviting sentence co-occurring with
    a summary, tagged as its own aspect)."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _d4_d5_event_refs(ue.candidate_events, {"summary_statement", "summary_uncertain", "summary_check"})
    return _build_indicator(CRITERION_INFORMATION_GATHERING, "D5", refs, None, "")


# ── E. INFORMATION GIVING (Step 12) ───────────────────────────────────────

def _map_e1(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21E: prior_knowledge_check (explicit "what do you already know
    about"/"have you heard about" wording) + prior_knowledge_uncertain
    (closed "do you know anything about" form -- Step 3/17, kept as
    evidence rather than dropped). No detector gap anymore -- an empty
    result this session is AVAILABILITY_LIMITED via _quality's no-refs
    branch, not a missing-detector gap: see this module's docstring on
    MISSING vs NEGATIVE."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _candidate_event_refs(ue.candidate_events, {"prior_knowledge_check", "prior_knowledge_uncertain"})
    return _build_indicator(CRITERION_INFORMATION_GIVING, "E1", refs, None, "")


def _map_e2(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21E: reaction_response (confirmed info-turn -> patient-reaction
    -> nurse-adapts sequence) + reaction_response_uncertain (a patient turn
    precedes but the information-giving context is unclear -- Step 3/14,
    kept as evidence rather than dropped)."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _information_giving_event_refs(ue.candidate_events, {"reaction_response", "reaction_response_uncertain"})
    return _build_indicator(CRITERION_INFORMATION_GIVING, "E2", refs, None, "")


def _map_e3(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21E: contribution_invitation (an information-giving turn
    precedes) + contribution_invitation_uncertain (no clear preceding
    information -- the B1 grey zone, Step 11: never auto-promoted)."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _information_giving_event_refs(
        ue.candidate_events, {"contribution_invitation", "contribution_invitation_uncertain"},
    )
    return _build_indicator(CRITERION_INFORMATION_GIVING, "E3", refs, None, "")


def _map_e4(ei: ExaminerInput) -> IndicatorEvidence:
    ue = ei.clinical_evidence.unified_evidence
    refs = _candidate_event_refs(ue.candidate_events, {"understanding_checked"})
    return _build_indicator(CRITERION_INFORMATION_GIVING, "E4", refs, None, "")


def _map_e5(ei: ExaminerInput) -> IndicatorEvidence:
    """Step 21E: further_information_check (explicit "any other
    questions"/"anything else" wording) + further_information_uncertain (a
    bare, unqualified "do you have any questions?" -- genuinely ambiguous
    with E4, Step 9/17: never guessed either way)."""
    ue = ei.clinical_evidence.unified_evidence
    refs = _candidate_event_refs(
        ue.candidate_events, {"further_information_check", "further_information_uncertain"},
    )
    return _build_indicator(CRITERION_INFORMATION_GIVING, "E5", refs, None, "")


_CLINICAL_INDICATOR_MAPPERS: Dict[str, List] = {
    CRITERION_RELATIONSHIP_BUILDING: [_map_a1, _map_a2, _map_a3, _map_a4],
    CRITERION_PATIENT_PERSPECTIVE: [_map_b1, _map_b2, _map_b3],
    CRITERION_PROVIDING_STRUCTURE: [_map_c1, _map_c2, _map_c3],
    CRITERION_INFORMATION_GATHERING: [_map_d1, _map_d2, _map_d3, _map_d4, _map_d5],
    CRITERION_INFORMATION_GIVING: [_map_e1, _map_e2, _map_e3, _map_e4, _map_e5],
}


# ── Linguistic criteria (Step 13/23) ──────────────────────────────────────

def _map_intelligibility(ei: ExaminerInput) -> LinguisticCriterionBundle:
    pron = ei.linguistic_evidence.pronunciation
    refs = []
    if pron is not None:
        refs.append(EvidenceRef(
            source="pronunciation", evidence_id="overall_score", turn_index=None,
            evidence_text=pron.transcript or "", provenance=PROVENANCE_DIRECT, evidence_level=LEVEL_L1_DIRECT,
            metadata={"overall_score": pron.overall_score, "problem_words": len(pron.problem_words)},
        ))
    for hint in ei.linguistic_evidence.accent_pattern_hints:
        refs.append(EvidenceRef(
            source="pronunciation", evidence_id="accent_pattern_hint", turn_index=None,
            evidence_text=str(hint.get("word_said", "")), provenance=PROVENANCE_DIRECT,
            evidence_level=LEVEL_L1_DIRECT, metadata=dict(hint),
        ))
    reason = None if refs else REASON_NO_AUDIO_INTELLIGIBILITY
    quality = _quality(refs, reason is not None)
    gaps = (
        [EvidenceGap(criterion=CRITERION_INTELLIGIBILITY, reason_code=reason,
                      missing_evidence_type="audio_intelligibility_evidence", availability=quality)]
        if reason else []
    )
    return LinguisticCriterionBundle(
        criterion=CRITERION_INTELLIGIBILITY, evidence_refs=refs, evidence_levels=[LEVEL_L1_DIRECT],
        audio_required=True, audio_available=ei.audio_availability.audio_available,
        evidence_quality=quality, gaps=gaps,
    )


def _map_fluency(ei: ExaminerInput) -> LinguisticCriterionBundle:
    pron = ei.linguistic_evidence.pronunciation
    refs = []
    if pron is not None:
        refs.append(EvidenceRef(
            source="pronunciation", evidence_id="fluency_score", turn_index=None,
            evidence_text=pron.transcript or "", provenance=PROVENANCE_DIRECT, evidence_level=LEVEL_L1_DIRECT,
            metadata={"fluency_score": pron.fluency_score, "completeness_score": pron.completeness_score},
        ))
    reason = None if refs else REASON_NO_AUDIO_FLUENCY
    quality = _quality(refs, reason is not None)
    gaps = (
        [EvidenceGap(criterion=CRITERION_FLUENCY, reason_code=reason,
                      missing_evidence_type="audio_fluency_evidence", availability=quality)]
        if reason else []
    )
    return LinguisticCriterionBundle(
        criterion=CRITERION_FLUENCY, evidence_refs=refs, evidence_levels=[LEVEL_L1_DIRECT],
        audio_required=True, audio_available=ei.audio_availability.audio_available,
        evidence_quality=quality, gaps=gaps,
    )


def _map_appropriateness(ei: ExaminerInput) -> LinguisticCriterionBundle:
    refs = _transcript_refs(ei.transcript)
    for j in ei.linguistic_evidence.jargon_evidence:
        meta = {"clarified_afterward": j.clarified_afterward}
        if j.patient_reaction is not None:
            meta["patient_reaction"] = j.patient_reaction
        refs.append(EvidenceRef(
            source="jargon_evidence", evidence_id=j.term, turn_index=j.turn_index,
            evidence_text=j.evidence_text, provenance=SOURCE_DETERMINISTIC,
            evidence_level=LEVEL_L2_DETERMINISTIC, metadata=meta,
        ))
    quality = AVAILABILITY_PARTIAL
    gap = EvidenceGap(
        criterion=CRITERION_APPROPRIATENESS_OF_LANGUAGE, reason_code=REASON_JARGON_DETECTOR_PARTIAL_COVERAGE,
        missing_evidence_type="full_register_and_lexis_analysis", availability=quality,
    )
    return LinguisticCriterionBundle(
        criterion=CRITERION_APPROPRIATENESS_OF_LANGUAGE, evidence_refs=refs,
        evidence_levels=[LEVEL_L1_DIRECT, LEVEL_L2_DETERMINISTIC], audio_required=False,
        audio_available=ei.audio_availability.audio_available, evidence_quality=quality, gaps=[gap],
    )


def _map_grammar(ei: ExaminerInput) -> LinguisticCriterionBundle:
    refs = _transcript_refs(ei.transcript)
    quality = AVAILABILITY_PARTIAL if refs else AVAILABILITY_INSUFFICIENT
    gap = EvidenceGap(
        criterion=CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, reason_code=REASON_NO_GRAMMAR_DETECTOR,
        missing_evidence_type="structured_grammar_analysis", availability=quality,
    )
    return LinguisticCriterionBundle(
        criterion=CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, evidence_refs=refs,
        evidence_levels=[LEVEL_L1_DIRECT], audio_required=False,
        audio_available=ei.audio_availability.audio_available, evidence_quality=quality, gaps=[gap],
    )


_LINGUISTIC_MAPPERS = [_map_intelligibility, _map_fluency, _map_appropriateness, _map_grammar]


# ── Entry point (Step 27: deterministic, no I/O) ──────────────────────────

def map_criterion_evidence(examiner_input: ExaminerInput) -> CriterionEvidenceMap:
    """Pure function: same ExaminerInput always yields the same
    CriterionEvidenceMap. No randomness, no timestamps, no model calls, no
    mutation of `examiner_input`."""
    if not isinstance(examiner_input, ExaminerInput):
        raise ValueError("examiner_input must be an ExaminerInput instance")

    clinical: List[ClinicalCriterionBundle] = []
    for criterion, mappers in _CLINICAL_INDICATOR_MAPPERS.items():
        indicators = [m(examiner_input) for m in mappers]
        clinical.append(ClinicalCriterionBundle(
            criterion=criterion, indicators=indicators,
            criterion_evidence_quality=_worst_quality([i.evidence_quality for i in indicators]),
        ))

    linguistic = [m(examiner_input) for m in _LINGUISTIC_MAPPERS]

    return CriterionEvidenceMap(clinical=clinical, linguistic=linguistic)
