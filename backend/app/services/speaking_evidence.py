"""Speaking Evidence Layer (Step 5).

Bridges `conversation + candidate behaviour + patient behaviour` into
structured, traceable evidence, without touching scoring, the Learning
Brain, or either speaking pipeline's transport.

Design: derive_patient_state() (app.services.patient_state) is a pure
function of (interlocutor_card, history) -- same inputs always produce the
same PatientState. Rather than hand-tracking transitions (which would
duplicate that state machine and risk drifting from it), this module
recomputes PatientState at every prefix length of the conversation and
diffs consecutive snapshots. That reconstructs exactly what the live
patient prompt would have shown at each point in time -- every transition
here is something the real engine actually produced, never invented. This
also makes evidence reconstruction after a realtime reconnect trivial:
same (card, history) in, same evidence out.

Both speaking pipelines already hold their conversation as a list of
{"role": "nurse"|"patient", "content"/"text": str} -- callers pass that
here as `history: List[{"role", "content"}]` (the realtime router already
does this exact role/text -> role/content conversion for
recompute_patient_state, see speaking_realtime.py).

LIMITATION (see patient_state.py's own docstring on concern resolution):
a concern's "resolved" status is only meaningful against a *complete*
history. Recomputed on a growing prefix, it can appear prematurely --
right after the turn that addressed it, before any later turn has had a
chance to re-raise it. That is a property of derive_patient_state itself,
not something introduced here; state_transitions can show a concern
reaching "resolved" and a later turn's snapshot showing "addressed" again
if a re-raise follows. This module surfaces what the engine actually
computed at each point, not a smoothed-over story.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.services.patient_state import (
    CONCERN_RANK,
    JARGON_EXPLANATION_WORDS,
    PatientState,
    SemanticHints,
    derive_patient_state,
    detect_nurse_events,
)
from app.services.attentiveness_evidence import detect_acknowledgement_events, detect_reflective_response_events
from app.services.cue_response_evidence import CUE_EVENT_TYPES, detect_cue_response_events
from app.services.information_gathering_evidence import detect_clarification_events, detect_summary_events
from app.services.information_giving_evidence import (
    detect_contribution_invitation_events,
    detect_further_information_events,
    detect_prior_knowledge_events,
    detect_reaction_response_events,
)
from app.services.nonjudgmental_evidence import detect_nonjudgmental_events
from app.services.opening_evidence import detect_opening_events
from app.services.question_behaviour import detect_question_events
from app.services.sequencing_evidence import detect_sequence_events
from app.services.structure_evidence import detect_organization_marker_events, detect_structure_events
from app.services import semantic_evidence

SOURCE_DETERMINISTIC = "deterministic_rule"
SOURCE_SEMANTIC = semantic_evidence.SOURCE_SEMANTIC


class CandidateEvent(BaseModel):
    event: str
    turn_index: int
    evidence_text: str
    source: str = SOURCE_DETERMINISTIC
    target_concern: Optional[str] = None
    # Step 21D (D4/D5): the patient turn(s) a clarification/summary refers
    # back to (Step 2/5/8 of that task's spec). Empty for every other event
    # -- additive, backward-compatible field, same pattern as target_concern.
    related_patient_turns: List[int] = []
    # Step 21E (E2/E3): the nurse information-giving turn(s) a reaction-
    # response/contribution-invitation event refers back to. Empty for every
    # other event -- same additive pattern as related_patient_turns above.
    related_information_turns: List[int] = []


class PatientEvent(BaseModel):
    event: str  # "concern_raised" | "information_revealed" | "emotional_trigger_fired"
    # Step 7 additions: "information_revelation_check" (revealed True/False,
    # source=semantic_model) and "concern_resolution_signal" (target_concern
    # set, source=semantic_model). Both new, optional fields -- existing
    # deterministic events never set them, so this is backward-compatible.
    turn_index: int
    evidence_text: str
    source: str = SOURCE_DETERMINISTIC
    revealed: Optional[bool] = None
    target_concern: Optional[str] = None


class StateTransition(BaseModel):
    field: str  # "trust" | "current_emotion" | "concern_status:<concern text>"
    before: str
    after: str
    cause_event: Optional[str]
    turn_index: int


class ConcernOutcome(BaseModel):
    concern: str
    final_status: str
    resolved: bool
    history: List[Dict[str, Any]]  # [{"status", "turn_index", "cause_event"}, ...]
    # Task 3: the prefix-recomputation this module already documents (see
    # module docstring LIMITATION) can show a concern reach "resolved" and
    # later fall back to "addressed" once a re-raise enters the growing
    # history. That's not the engine going backward -- it's a reopening.
    # These two fields make it a real, dated event instead of a confusing
    # regression: every turn_index the concern actually reached "resolved",
    # and every turn_index/reason it was reopened afterward. Additive --
    # `history` above is unchanged, still the raw transition sequence.
    resolved_at_turns: List[int] = []
    reopened_events: List[Dict[str, Any]] = []  # [{"turn_index", "from_status", "to_status", "reason"}, ...]


class HiddenInfoCandidateTurn(BaseModel):
    """Step 12B (Rule 5 -- full audit trail): one patient turn that was a
    lexical candidate for a hidden-info item, and what verification (if any)
    found for THAT specific turn. A hidden item can have many of these; see
    HiddenInfoOutcome.candidate_turns."""
    turn_index: int
    evidence_text: str
    verification_status: str  # semantic_evidence.STATUS_* value, or "not_called"


class HiddenInfoOutcome(BaseModel):
    """Task 2: makes candidate-detection, semantic-verification, and final
    status independently visible for each hidden-info item, instead of a
    miss upstream (item never became a candidate) looking identical to a
    correct "stayed hidden" outcome. See semantic_evidence's STATUS_*
    constants for verification_status values; "not_called" means no
    semantic check was ever attempted for this item (build_speaking_evidence
    alone -- no semantics -- always reports "not_called"; only
    build_speaking_evidence_with_semantics can report a real verification
    outcome).

    Step 12B: candidate_detected/verification_status/final_status/turn_index/
    evidence_text are now the AGGREGATE view across every candidate turn --
    final_status="revealed" only when some candidate turn was actually
    verified_revealed (Rule 4), and turn_index/evidence_text point at the
    earliest such turn (Rule 6), never just the first keyword match. The
    full per-turn breakdown behind that aggregate is candidate_turns."""
    item: str
    candidate_detected: bool
    verification_status: str
    final_status: str  # "revealed" | "hidden"
    turn_index: Optional[int] = None
    evidence_text: Optional[str] = None
    candidate_turns: List[HiddenInfoCandidateTurn] = []


class JargonEvidence(BaseModel):
    term: str
    turn_index: int
    evidence_text: str
    patient_reaction: Optional[str] = None
    clarified_afterward: bool = False


class InteractionMetrics(BaseModel):
    turn_counts: Dict[str, int]
    jargon_events: int
    empathy_events: int
    concern_exploration_events: int
    understanding_check_events: int
    dismissive_events: int


class SpeakingEvidence(BaseModel):
    candidate_events: List[CandidateEvent]
    patient_events: List[PatientEvent]
    concern_outcomes: List[ConcernOutcome]
    state_transitions: List[StateTransition]
    jargon_evidence: List[JargonEvidence]
    interaction_metrics: InteractionMetrics
    hidden_info_outcomes: List[HiddenInfoOutcome] = []


def _hidden_info_candidate_turns(item: str, history: List[Dict[str, str]]) -> List[HiddenInfoCandidateTurn]:
    """Shared by both builders below (Step 10, extended by Step 12B): every
    transcript turn that made `item` a keyword-candidate, not just the
    first. Without semantics (build_speaking_evidence), every entry is
    "not_called" -- no verification has run yet, just candidate detection."""
    return [
        HiddenInfoCandidateTurn(turn_index=idx, evidence_text=text, verification_status="not_called")
        for idx, text in semantic_evidence._candidate_turns(item, history)
    ]


def _compute_snapshots(card: Dict[str, Any], history: List[Dict[str, str]]) -> List[PatientState]:
    """Hoisted out of build_speaking_evidence so build_speaking_evidence_with_semantics
    (Step 7) can reuse the same prefix-snapshot sequence instead of recomputing it."""
    return [derive_patient_state(card, history[:i]) for i in range(len(history) + 1)]


def build_speaking_evidence(
    interlocutor_card: Optional[Dict[str, Any]], history: List[Dict[str, str]],
) -> SpeakingEvidence:
    """Pure function: same card + same history always yields the same
    SpeakingEvidence, matching derive_patient_state's own contract."""
    card = interlocutor_card or {}

    # PatientState at every prefix length, including the empty one --
    # snapshots[i] is the state after exactly i turns. Reuses the real
    # engine unmodified (see module docstring).
    snapshots: List[PatientState] = _compute_snapshots(card, history)

    candidate_events: List[CandidateEvent] = []
    patient_events: List[PatientEvent] = []
    state_transitions: List[StateTransition] = []

    for idx, turn in enumerate(history):
        role = turn.get("role")
        content = turn.get("content", "")
        before, after = snapshots[idx], snapshots[idx + 1]

        turn_events = detect_nurse_events(content) if role == "nurse" else []
        question_events = detect_question_events(content) if role == "nurse" else []
        structure_events = detect_structure_events(content) if role == "nurse" else []
        cause_event = ",".join(e["event"] for e in turn_events) or None

        turn_target_concern: Optional[str] = None
        if before.trust != after.trust:
            state_transitions.append(StateTransition(
                field="trust", before=before.trust, after=after.trust,
                cause_event=cause_event, turn_index=idx,
            ))
        if before.current_emotion != after.current_emotion:
            state_transitions.append(StateTransition(
                field="current_emotion", before=before.current_emotion, after=after.current_emotion,
                cause_event=cause_event, turn_index=idx,
            ))
        for concern, after_status in after.concern_status.items():
            before_status = before.concern_status.get(concern, "not_raised")
            if before_status == after_status:
                continue
            state_transitions.append(StateTransition(
                field=f"concern_status:{concern}", before=before_status, after=after_status,
                cause_event=cause_event, turn_index=idx,
            ))
            if after_status == "raised":
                patient_events.append(PatientEvent(event="concern_raised", turn_index=idx, evidence_text=concern))
            else:
                # Any nurse-turn-driven advance (acknowledged/explored/addressed/resolved)
                # is the target this turn's candidate events were judged against --
                # matches the single-FIFO-target design in _derive_behavioural_state.
                turn_target_concern = concern

        for item in set(after.revealed_information) - set(before.revealed_information):
            patient_events.append(PatientEvent(event="information_revealed", turn_index=idx, evidence_text=item))
        for trigger in set(after.fired_emotional_triggers) - set(before.fired_emotional_triggers):
            patient_events.append(PatientEvent(event="emotional_trigger_fired", turn_index=idx, evidence_text=trigger))

        for ev in turn_events:
            candidate_events.append(CandidateEvent(
                event=ev["event"], turn_index=idx, evidence_text=ev["evidence"],
                target_concern=None if ev["event"] == "jargon_used" else turn_target_concern,
            ))
        # Question-type events (D2/D3, Step 21A) are a separate, independent
        # signal from the concern-advancing events above -- never given a
        # target_concern, and never folded into cause_event (a question's
        # own open/closed/compound/leading shape doesn't cause a concern's
        # status to move).
        for ev in question_events:
            candidate_events.append(CandidateEvent(
                event=ev["event"], turn_index=idx, evidence_text=ev["evidence"],
            ))
        # C2 signposting (Step 21B) -- per-turn, same independent-signal
        # treatment as question_events above.
        for ev in structure_events:
            candidate_events.append(CandidateEvent(
                event=ev["event"], turn_index=idx, evidence_text=ev["evidence"],
            ))

    # C3 organizing markers (Step 21B) -- needs the FULL history (a sequence
    # spans several nurse turns), so this runs once here rather than inside
    # the per-turn loop above.
    for ev in detect_organization_marker_events(history):
        candidate_events.append(CandidateEvent(
            event=ev["event"], turn_index=ev["turn_index"], evidence_text=ev["evidence"],
        ))

    # C1 consultation sequencing (Step 21C) -- same whole-history shape as C3
    # above, for the same reason (a sequence spans several nurse turns).
    for ev in detect_sequence_events(history):
        candidate_events.append(CandidateEvent(
            event=ev["event"], turn_index=ev["turn_index"], evidence_text=ev["evidence"],
        ))

    # A1 opening interaction (Step 21G) -- same whole-history shape as C1/C3
    # above: the opening window spans the first nurse turn(s) regardless of
    # what role spoke first, so this can't run per-turn in the loop above.
    for ev in detect_opening_events(history):
        candidate_events.append(CandidateEvent(
            event=ev["event"], turn_index=ev["turn_index"], evidence_text=ev["evidence"],
        ))

    # D4/D5 clarification & summarisation (Step 21D) -- same whole-history
    # shape as C1/C3 above: a clarification/summary references a prior (and
    # sometimes following) patient turn, so this can't run per-turn either.
    for ev in detect_clarification_events(history):
        candidate_events.append(CandidateEvent(
            event=ev.event_type, turn_index=ev.turn_index, evidence_text=ev.evidence_text,
            related_patient_turns=ev.related_patient_turns,
        ))
    for ev in detect_summary_events(history):
        candidate_events.append(CandidateEvent(
            event=ev.event_type, turn_index=ev.turn_index, evidence_text=ev.evidence_text,
            related_patient_turns=ev.related_patient_turns,
        ))

    # E1/E2/E3/E5 information giving (Step 21E) -- same whole-history shape
    # as D4/D5 above: E2/E3 reference nearby nurse/patient turns, so these
    # can't run per-turn either (E1/E5 don't strictly need it, but are kept
    # here for one consistent call site per this detector family).
    for ev in detect_prior_knowledge_events(history):
        candidate_events.append(CandidateEvent(
            event=ev.event_type, turn_index=ev.turn_index, evidence_text=ev.evidence_text,
        ))
    for ev in detect_reaction_response_events(history):
        candidate_events.append(CandidateEvent(
            event=ev.event_type, turn_index=ev.turn_index, evidence_text=ev.evidence_text,
            related_patient_turns=ev.related_patient_turns,
            related_information_turns=ev.related_information_turns,
        ))
    for ev in detect_contribution_invitation_events(history):
        candidate_events.append(CandidateEvent(
            event=ev.event_type, turn_index=ev.turn_index, evidence_text=ev.evidence_text,
            related_information_turns=ev.related_information_turns,
        ))
    for ev in detect_further_information_events(history):
        candidate_events.append(CandidateEvent(
            event=ev.event_type, turn_index=ev.turn_index, evidence_text=ev.evidence_text,
        ))

    # A2 attentive acknowledgement / reflective response (Step 21H) -- same
    # whole-history shape as D4/D5 above: acknowledgement is whole-turn/
    # sentence scanned, reflective response needs the immediately preceding
    # patient turn, so neither runs inside the per-turn loop above.
    for ev in detect_acknowledgement_events(history):
        candidate_events.append(CandidateEvent(
            event=ev.event_type, turn_index=ev.turn_index, evidence_text=ev.evidence_text,
        ))
    for ev in detect_reflective_response_events(history):
        candidate_events.append(CandidateEvent(
            event=ev.event_type, turn_index=ev.turn_index, evidence_text=ev.evidence_text,
            related_patient_turns=ev.related_patient_turns,
        ))

    # A3 non-judgmental approach (Step 21I) -- same whole-history shape as A2
    # above: context linkage needs the immediately preceding patient turn.
    # Independent of A2/A4 -- never derived from either (Step 21I spec).
    for ev in detect_nonjudgmental_events(history):
        candidate_events.append(CandidateEvent(
            event=ev.event_type, turn_index=ev.turn_index, evidence_text=ev.evidence_text,
            related_patient_turns=ev.related_patient_turns,
        ))

    # B2 cue -> response pairing (Step 21F) -- needs the already-detected
    # patient cue events (concern_raised/emotional_trigger_fired), so this
    # runs once here rather than inside the per-turn loop above.
    patient_cue_events = [
        {"event": pe.event, "turn_index": pe.turn_index, "evidence_text": pe.evidence_text}
        for pe in patient_events if pe.event in CUE_EVENT_TYPES
    ]
    for ev in detect_cue_response_events(history, patient_cue_events):
        candidate_events.append(CandidateEvent(
            event=ev.event_type, turn_index=ev.turn_index, evidence_text=ev.evidence_text,
            target_concern=ev.target_concern, related_patient_turns=ev.related_patient_turns,
        ))

    # Concern outcomes: every concern the card defines, not just ones that
    # got raised, so a scenario's untouched concerns show up as "not_raised"
    # rather than silently disappearing from the evidence.
    final_concern_status = snapshots[-1].concern_status
    concern_outcomes = []
    for concern in snapshots[0].concern_status.keys():
        concern_history = [
            {"status": t.after, "turn_index": t.turn_index, "cause_event": t.cause_event}
            for t in state_transitions
            if t.field == f"concern_status:{concern}"
        ]
        # Task 3: walk the raw transition sequence looking for a rank drop
        # (e.g. resolved -> addressed) -- see ConcernOutcome's docstring on
        # why that happens and why it's a reopening, not a bug.
        resolved_at_turns: List[int] = []
        reopened_events: List[Dict[str, Any]] = []
        prev_status = "not_raised"
        for entry in concern_history:
            status = entry["status"]
            if CONCERN_RANK[status] < CONCERN_RANK[prev_status]:
                reason_turn = history[entry["turn_index"]] if entry["turn_index"] < len(history) else {}
                reopened_events.append({
                    "turn_index": entry["turn_index"],
                    "from_status": prev_status,
                    "to_status": status,
                    "reason": reason_turn.get("content", "") or "concern raised again",
                })
            if status == "resolved":
                resolved_at_turns.append(entry["turn_index"])
            prev_status = status

        concern_outcomes.append(ConcernOutcome(
            concern=concern,
            final_status=final_concern_status.get(concern, "not_raised"),
            resolved=final_concern_status.get(concern) == "resolved",
            history=concern_history,
            resolved_at_turns=resolved_at_turns,
            reopened_events=reopened_events,
        ))

    jargon_evidence: List[JargonEvidence] = []
    for ev in candidate_events:
        if ev.event != "jargon_used":
            continue
        term = ev.evidence_text
        patient_reaction = None
        if ev.turn_index + 1 < len(history) and history[ev.turn_index + 1].get("role") == "patient":
            patient_reaction = history[ev.turn_index + 1].get("content", "")
        clarified_afterward = any(
            term in later.get("content", "").lower() and any(w in later.get("content", "").lower() for w in JARGON_EXPLANATION_WORDS)
            for later in history[ev.turn_index + 1:]
            if later.get("role") == "nurse"
        )
        jargon_evidence.append(JargonEvidence(
            term=term, turn_index=ev.turn_index, evidence_text=term,
            patient_reaction=patient_reaction, clarified_afterward=clarified_afterward,
        ))

    def _count(event_name: str) -> int:
        return sum(1 for e in candidate_events if e.event == event_name)

    interaction_metrics = InteractionMetrics(
        turn_counts={
            "nurse": sum(1 for t in history if t.get("role") == "nurse"),
            "patient": sum(1 for t in history if t.get("role") == "patient"),
            "total": len(history),
        },
        jargon_events=_count("jargon_used"),
        empathy_events=_count("empathy_acknowledgement"),
        concern_exploration_events=_count("concern_exploration"),
        understanding_check_events=_count("understanding_checked"),
        dismissive_events=_count("dismissive_response"),
    )

    # Hidden-info outcomes (Task 2, Step 12B Rule 4): every item the card
    # defines. No semantic check has run in this deterministic-only builder,
    # so final_status is always "hidden" here -- candidate_detected reports
    # lexical candidacy on its own (never promoted to revealed without
    # verification). build_speaking_evidence_with_semantics below replaces
    # this list once real verification has run.
    hidden_info_outcomes = []
    for item in (card.get("information_to_withhold") or []):
        candidate_turns = _hidden_info_candidate_turns(item, history)
        first = candidate_turns[0] if candidate_turns else None
        hidden_info_outcomes.append(HiddenInfoOutcome(
            item=item,
            candidate_detected=bool(candidate_turns),
            verification_status="not_called",
            final_status="hidden",
            turn_index=first.turn_index if first else None,
            evidence_text=first.evidence_text if first else None,
            candidate_turns=candidate_turns,
        ))

    return SpeakingEvidence(
        candidate_events=candidate_events,
        patient_events=patient_events,
        concern_outcomes=concern_outcomes,
        state_transitions=state_transitions,
        jargon_evidence=jargon_evidence,
        interaction_metrics=interaction_metrics,
        hidden_info_outcomes=hidden_info_outcomes,
    )


async def build_speaking_evidence_with_semantics(
    interlocutor_card: Optional[Dict[str, Any]], history: List[Dict[str, str]],
    *, user_id: str = "", session_id: Optional[int] = None,
    prior: Optional[SemanticHints] = None,
) -> SpeakingEvidence:
    """Step 7: additive semantic enrichment on top of build_speaking_evidence's
    deterministic output. Computed ONCE over the final transcript, not at
    every prefix length like the deterministic snapshots above -- repeating
    a semantic call at every prefix length would multiply cost by
    conversation length for no benefit, since the same candidate/turn gets
    re-verified at every later prefix too. Used by the admin Speaking
    Evidence Inspector (a read-only, on-demand diagnostic, not a hot path),
    and available to any other post-hoc caller with the same shape of need.

    KNOWN LIMITATION (Step 10, kept deliberately separate -- see this
    module's own docstring on why state and evidence stay separate):
    semantic events below are appended to candidate_events/patient_events
    as clearly source-tagged additional signal -- they do NOT retroactively
    change concern_outcomes/state_transitions, which remain exactly what
    the deterministic PatientState state machine actually computed. Fully
    reconciling the two would mean re-deriving every prefix snapshot with
    semantic hints applied, reintroducing the same repeated-call cost
    problem above; left as a documented next step, not solved here.
    """
    card = interlocutor_card or {}
    evidence = build_speaking_evidence(card, history)
    if not history:
        return evidence

    # 1. Hidden-information revelation verification (Finding 1, extended by
    # Step 12B) -- every candidate turn in the final transcript gets
    # verified (hidden_info_hints stops early per item once one turn
    # confirms revealed=True; see its own docstring for the cost rationale).
    # Step 13: `prior` (persisted SemanticHints, if the caller has any) means
    # every turn already verified in a prior connection/session is skipped --
    # see this function's own docstring.
    hints = await semantic_evidence.hidden_info_hints(card, history, prior=prior, user_id=user_id, session_id=session_id)

    # Task 2 + Step 12B: replace the deterministic-only placeholder outcomes
    # with the real candidate/verification/final breakdown, now WITH the
    # full per-turn audit trail (candidate_turns) instead of a single
    # first-match turn reference. final_status="revealed" only when a
    # candidate turn actually verified true (Rule 4); turn_index/
    # evidence_text point at that earliest verified turn (Rule 6), or --
    # when never revealed -- at whichever turn produced the reported
    # aggregate verification_status, so "why" is always traceable to one
    # concrete transcript line.
    new_hidden_outcomes = []
    for item in (card.get("information_to_withhold") or []):
        turn_status = hints.candidate_turn_status.get(item, {})
        candidate_turns = [
            HiddenInfoCandidateTurn(turn_index=idx, evidence_text=history[idx].get("content", ""), verification_status=status)
            for idx, status in sorted(turn_status.items())
        ]
        agg_status = hints.verification_status.get(item, "not_called")
        final_status = "revealed" if item in hints.confirmed_hidden_reveals else "hidden"
        if final_status == "revealed":
            final_turn = hints.confirmed_reveal_turn.get(item)
        else:
            final_turn = next((idx for idx, status in sorted(turn_status.items()) if status == agg_status), None)
        new_hidden_outcomes.append(HiddenInfoOutcome(
            item=item,
            candidate_detected=bool(candidate_turns),
            verification_status=agg_status,
            final_status=final_status,
            turn_index=final_turn,
            evidence_text=history[final_turn].get("content", "") if final_turn is not None else None,
            candidate_turns=candidate_turns,
        ))
    evidence.hidden_info_outcomes = new_hidden_outcomes

    # Timeline signal (Step 15's per-turn admin view draws on candidate_turns
    # above; this is the generic candidate/patient-event timeline other
    # sections already reconcile) -- one entry per candidate turn that got a
    # real verdict, skipping turns that only ever produced a failure status
    # (there's nothing to "check" there, just an unanswered attempt).
    for item, turn_status in hints.candidate_turn_status.items():
        for idx, status in turn_status.items():
            if status not in ("verified_revealed", "verified_not_revealed"):
                continue
            evidence.patient_events.append(PatientEvent(
                event="information_revelation_check", turn_index=idx,
                evidence_text=history[idx].get("content", "") or item,
                revealed=status == "verified_revealed", source=SOURCE_SEMANTIC,
            ))

    # 2/3. Concern exploration/addressing (Finding 2) + patient resolution
    # signal -- only where the deterministic pass had nothing to say.
    concerns = card.get("questions_to_ask") or card.get("concerns") or []
    if concerns:
        snapshots = _compute_snapshots(card, history)
        for idx, turn in enumerate(history):
            role = turn.get("role")
            content = turn.get("content", "")
            state_before = snapshots[idx]
            if role == "nurse":
                has_exploration = any(
                    e.event == "concern_exploration" for e in evidence.candidate_events if e.turn_index == idx
                )
                if not has_exploration and state_before.current_concern:
                    context = semantic_evidence._recent_context(history, idx)
                    result = await semantic_evidence.classify_nurse_concern_event(
                        content, concerns, context, user_id=user_id, session_id=session_id,
                    )
                    if result and result["event"] != "none":
                        evidence.candidate_events.append(CandidateEvent(
                            event=result["event"], turn_index=idx, evidence_text=content[:200],
                            source=SOURCE_SEMANTIC, target_concern=result["target_concern"],
                        ))
            elif role == "patient":
                addressed = [c for c, s in state_before.concern_status.items() if s == "addressed"]
                if addressed:
                    concern = addressed[0]
                    nurse_turn = history[idx - 1]["content"] if idx > 0 and history[idx - 1].get("role") == "nurse" else ""
                    resolved = await semantic_evidence.classify_patient_resolution(
                        concern, nurse_turn, content, user_id=user_id, session_id=session_id,
                    )
                    if resolved is True:
                        evidence.patient_events.append(PatientEvent(
                            event="concern_resolution_signal", turn_index=idx, evidence_text=content[:200],
                            target_concern=concern, source=SOURCE_SEMANTIC,
                        ))

    return evidence
