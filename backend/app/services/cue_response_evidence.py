"""Patient Cue -> Candidate Response (B2) detector (Step 21F).

    "B2 -- picking up the patient's cues" (examiner_input.INDICATOR_TEXT)
    concerns whether the candidate's NEXT turn engages with a patient cue,
    not just whether the cue itself was raised (that's already covered by
    the existing patient_events on B2 -- concern_raised/emotional_trigger_
    fired). This module adds the missing other half: the response side.

Cue = a patient turn where speaking_evidence.py's patient_state-derived
PatientEvent already recorded concern_raised or emotional_trigger_fired.
Passed in as plain dicts rather than re-derived here -- this module never
recomputes PatientState, same "don't duplicate the engine" rule as
speaking_evidence.py's own module docstring.

Response = the immediate next transcript turn, if and only if it is the
nurse's turn. A cue followed by another patient turn, or sitting at the
end of the transcript, has no response to pair -- nothing is emitted, never
guessed (MISSING vs NEGATIVE, criterion_evidence.py's rule: an unanswered
cue is absence of evidence, not a negative signal).

Two tiers, same structural-pairing + lexical-confirmation pattern already
used by information_giving_evidence.py's E2/E3 and information_gathering_
evidence.py's D4/D5:
  cue_response: the immediate next nurse turn independently produces
      empathy_acknowledgement / concern_exploration / understanding_checked
      (patient_state.detect_nurse_events run again on that one turn --
      reuses the existing phrase-list detector, no second lexicon).
  cue_response_uncertain: a nurse turn immediately follows, but none of the
      above fired there -- adjacency alone doesn't prove the candidate
      engaged with THIS cue, so it's kept as evidence rather than dropped.

LIMITATIONS:
  - adjacency-only: a response given two or more turns later (after an
    intervening nurse turn on something else) is not linked, even if it
    does address the cue.
  - lexical confirmation reuses patient_state's own empathy/concern-
    exploration/understanding-check phrase lists -- a genuinely engaged but
    differently-worded response is reported uncertain, never scored down.
  - one cue pairs with at most one response turn -- a cue addressed
    gradually across several following nurse turns is not reconstructed.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel

from app.services.patient_state import detect_nurse_events

EVENT_CUE_RESPONSE = "cue_response"
EVENT_CUE_RESPONSE_UNCERTAIN = "cue_response_uncertain"

PROVENANCE_DETERMINISTIC = "deterministic_rule"
EVIDENCE_LEVEL_DETERMINISTIC = "L2_deterministic"

CUE_EVENT_TYPES = {"concern_raised", "emotional_trigger_fired"}
_ENGAGEMENT_EVENTS = {"empathy_acknowledgement", "concern_exploration", "understanding_checked"}

LIMITATIONS: List[str] = [
    "Adjacency-only: pairs a cue with the immediate next turn only -- a response "
    "given two or more turns later is not linked, even if it does address the cue.",
    "Lexical confirmation reuses patient_state's existing empathy/concern-exploration/"
    "understanding-check phrase lists -- a genuinely engaged but differently-worded "
    "response is reported as cue_response_uncertain, never scored down.",
    "One cue pairs with at most one response turn -- a cue addressed gradually across "
    "several following nurse turns is not reconstructed.",
]


class CueResponseEvent(BaseModel):
    turn_index: int  # the RESPONSE turn (nurse)
    evidence_text: str
    event_type: str  # EVENT_CUE_RESPONSE | EVENT_CUE_RESPONSE_UNCERTAIN
    cue_event: str  # "concern_raised" | "emotional_trigger_fired"
    cue_text: str
    related_patient_turns: List[int] = []  # the cue's own turn_index
    target_concern: Optional[str] = None
    provenance: str = PROVENANCE_DETERMINISTIC
    evidence_level: str = EVIDENCE_LEVEL_DETERMINISTIC


def detect_cue_response_events(
    history: List[Dict[str, str]], patient_cue_events: List[Dict],
) -> List[CueResponseEvent]:
    """`patient_cue_events`: [{"event", "turn_index", "evidence_text"}, ...],
    already-detected concern_raised/emotional_trigger_fired events (speaking_
    evidence.py passes its own PatientEvent list, filtered/dict-ified)."""
    history = history or []
    events: List[CueResponseEvent] = []
    for cue in patient_cue_events or []:
        if cue.get("event") not in CUE_EVENT_TYPES:
            continue
        cue_idx = cue["turn_index"]
        response_idx = cue_idx + 1
        if response_idx >= len(history):
            continue
        response = history[response_idx]
        if response.get("role") != "nurse":
            continue
        content = response.get("content", "")
        if not content.strip():
            continue

        engaged = {e["event"] for e in detect_nurse_events(content)} & _ENGAGEMENT_EVENTS
        event_type = EVENT_CUE_RESPONSE if engaged else EVENT_CUE_RESPONSE_UNCERTAIN
        events.append(CueResponseEvent(
            turn_index=response_idx, evidence_text=content, event_type=event_type,
            cue_event=cue["event"], cue_text=cue.get("evidence_text", ""),
            related_patient_turns=[cue_idx],
            target_concern=cue.get("evidence_text") if cue["event"] == "concern_raised" else None,
        ))
    return events


if __name__ == "__main__":
    confirmed = detect_cue_response_events(
        [
            {"role": "patient", "content": "I'm really scared about the surgery."},
            {"role": "nurse", "content": "I can see that this is worrying you -- let's talk it through."},
        ],
        [{"event": "emotional_trigger_fired", "turn_index": 0, "evidence_text": "fear_of_surgery"}],
    )
    assert len(confirmed) == 1
    assert confirmed[0].event_type == EVENT_CUE_RESPONSE
    assert confirmed[0].turn_index == 1 and confirmed[0].related_patient_turns == [0]

    uncertain = detect_cue_response_events(
        [
            {"role": "patient", "content": "I'm worried about the pain medication."},
            {"role": "nurse", "content": "Let's move on to your allergies."},
        ],
        [{"event": "concern_raised", "turn_index": 0, "evidence_text": "pain medication"}],
    )
    assert len(uncertain) == 1
    assert uncertain[0].event_type == EVENT_CUE_RESPONSE_UNCERTAIN
    assert uncertain[0].target_concern == "pain medication"

    no_response_at_end = detect_cue_response_events(
        [{"role": "patient", "content": "I'm scared."}],
        [{"event": "emotional_trigger_fired", "turn_index": 0, "evidence_text": "fear"}],
    )
    assert no_response_at_end == []

    no_response_patient_next = detect_cue_response_events(
        [
            {"role": "patient", "content": "I'm scared."},
            {"role": "patient", "content": "Really scared."},
        ],
        [{"event": "emotional_trigger_fired", "turn_index": 0, "evidence_text": "fear"}],
    )
    assert no_response_patient_next == []

    print("cue_response_evidence self-check OK")
