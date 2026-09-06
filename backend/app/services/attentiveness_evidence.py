"""Relationship Building attentive/respectful interaction (A2) detector (Step 21H).

    A2: "demonstrating an attentive and respectful attitude" -> emits
        "attentive_acknowledgement" / "attentive_acknowledgement_uncertain"
        (explicit interpersonal receipt of what the patient said) and
        "reflective_response" / "reflective_response_uncertain" (candidate
        paraphrases the patient's immediately preceding statement).

Same shape, same limitation as this codebase's other deterministic clinical
detectors (opening_evidence.py, information_gathering_evidence.py): this
classifies SURFACE FORM, not whether the candidate was actually attentive or
respectful. There is no score here, only evidence (criterion_evidence.py's
MISSING vs NEGATIVE rule).

ACKNOWLEDGEMENT (Step 2/8): matched as a FULL SENTENCE against a fixed
phrase set -- deliberately stricter than patient_state.py's A4 substring
matching, specifically so "I understand the medication schedule." (extra
words after the phrase) never matches. A4's own phrases ("i can understand",
"that sounds") are NOT reused here (Step 4: A2 must not be created merely
because A4 exists) -- this lexicon is disjoint from A4's.

REFLECTIVE RESPONSE (Step 3): a "you're.../it sounds like you..." framing
sentence immediately following a PATIENT turn, sharing >=1 significant
keyword (patient_state._keywords, same tool D4/D5 use) with that turn.
Framing alone with no shared keyword is kept as uncertain evidence, never
dropped (Step 15) -- and never linked to anything but the immediately
preceding turn (Step 2: no invented relationships).

DISMISSIVE (Step 7) and INTERRUPTION (Step 6) evidence are NOT re-detected
here:
  - dismissive_response already flows into speaking_evidence.py's
    candidate_events via patient_state.detect_nurse_events on every nurse
    turn -- criterion_evidence._map_a2 reads it directly from there.
    detect_attentiveness_evidence() below re-derives it too, but only for
    this module's own offline/golden-case/test view (same "run the real
    engine again for a self-contained bundle" convention as
    information_gathering_evidence.detect_information_gathering_evidence),
    never as a second production code path.
  - interrupted_count is a session/connection-level metric (realtime
    Interrupted event = candidate spoke over the patient's reply), not
    something present in `history` at all -- it cannot come out of a pure
    detect_*(history) function like every detector in this family. It is
    wired directly into criterion_evidence._map_a2, identical in shape to
    that module's existing _map_d1 handling of the same field. Deliberate
    deviation from a literal interruption_events[] list on this module's
    own model -- see this module's LIMITATIONS.

LIMITATIONS:
  - purely lexical: a genuine acknowledgement or reflection phrased outside
    the patterns below is missed, not scored as absent.
  - acknowledgement is full-sentence-anchored: a genuine acknowledgement
    embedded mid-sentence with trailing content beyond the recognized
    contrastive-conjunction case is missed rather than guessed.
  - reflective response requires the immediately preceding turn to be the
    patient's; a reflection of something said two or more turns earlier is
    not linked, even if it does reflect that turn.
  - reflective response is lexical-overlap only, not semantic paraphrase
    detection (Step 3: not required for this step) -- a genuine reflection
    using entirely different words from the patient's turn is missed.
  - interruption evidence is not represented on this module's own model --
    it is session-metric data wired in separately at the criterion_evidence
    integration layer (see module docstring above).
"""
from __future__ import annotations

import re
from typing import Dict, List

from pydantic import BaseModel

from app.services.patient_state import _keywords, detect_nurse_events

EVENT_ACKNOWLEDGEMENT = "attentive_acknowledgement"
EVENT_ACKNOWLEDGEMENT_UNCERTAIN = "attentive_acknowledgement_uncertain"
EVENT_REFLECTIVE_RESPONSE = "reflective_response"
EVENT_REFLECTIVE_RESPONSE_UNCERTAIN = "reflective_response_uncertain"

PROVENANCE_DETERMINISTIC = "deterministic_rule"
EVIDENCE_LEVEL_DETERMINISTIC = "L2_deterministic"

LIMITATIONS: List[str] = [
    "Detects surface-form acknowledgement/reflection phrasing only -- a genuine "
    "attentive response worded outside the known patterns is missed, not scored "
    "as absent.",
    "Acknowledgement is matched as a full sentence, not a substring -- a genuine "
    "acknowledgement with unrecognized trailing content beyond the contrastive-"
    "conjunction case is missed rather than guessed.",
    "Reflective response requires the immediately preceding turn to be the "
    "patient's, and uses deterministic keyword overlap, not semantic paraphrase "
    "detection -- a reflection two or more turns later, or using entirely "
    "different words, is missed.",
    "Interruption evidence is not part of this module's output -- it is session/"
    "connection metric data (interrupted_count), not present in the transcript, "
    "and is wired in separately at the criterion_evidence integration layer.",
]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


# ── Acknowledgement (Step 2/8) ──────────────────────────────────────────
# Full-sentence anchor (^...$, optional trailing punctuation) so "I
# understand the medication schedule." can never match -- only a bare
# recognized phrase, alone, as the entire sentence. Disjoint from A4's
# _EMPATHY_PHRASES (patient_state.py) -- "that sounds"/"i can understand"
# are deliberately not here (Step 4).
_STRONG_ACK_RE = re.compile(
    r"^(?:okay,?\s+)?(?:i see(?: what you mean)?|i understand|i hear you"
    r"|that makes sense"
    r"|thank you for (?:telling|sharing|explaining)(?:\s+me)?(?:\s+that)?"
    r"|thanks for explaining(?:\s+that)?)[.!]?$",
    re.IGNORECASE,
)
# Same phrase, but the sentence continues with a contrastive conjunction --
# a perfunctory-acknowledgement-then-pivot is genuinely ambiguous respectful-
# attention evidence (Step 15), never forced positive.
_CONTRAST_ACK_RE = re.compile(
    r"^(?:okay,?\s+)?(?:i see(?: what you mean)?|i understand|i hear you"
    r"|that makes sense"
    r"|thank you for (?:telling|sharing|explaining)(?:\s+me)?(?:\s+that)?"
    r"|thanks for explaining(?:\s+that)?)"
    r",?\s+(?:but|however|although)\b",
    re.IGNORECASE,
)


def _acknowledgement_tier(sentence: str) -> str | None:
    if _CONTRAST_ACK_RE.match(sentence):
        return "uncertain"
    if _STRONG_ACK_RE.match(sentence):
        return "strong"
    return None


# ── Reflective response (Step 3) ────────────────────────────────────────
_REFLECTION_FRAMING_RE = re.compile(
    r"^(?:so\s+)?(?:you'?re|you are|you feel|you sound|it sounds like you)\b",
    re.IGNORECASE,
)


class AcknowledgementEvent(BaseModel):
    turn_index: int
    evidence_text: str
    event_type: str  # EVENT_ACKNOWLEDGEMENT | EVENT_ACKNOWLEDGEMENT_UNCERTAIN
    provenance: str = PROVENANCE_DETERMINISTIC
    evidence_level: str = EVIDENCE_LEVEL_DETERMINISTIC


class ReflectiveResponseEvent(BaseModel):
    turn_index: int
    evidence_text: str
    event_type: str  # EVENT_REFLECTIVE_RESPONSE | EVENT_REFLECTIVE_RESPONSE_UNCERTAIN
    related_patient_turns: List[int] = []
    provenance: str = PROVENANCE_DETERMINISTIC
    evidence_level: str = EVIDENCE_LEVEL_DETERMINISTIC


class AttentivenessEvidence(BaseModel):
    acknowledgement_events: List[AcknowledgementEvent] = []
    reflective_response_events: List[ReflectiveResponseEvent] = []
    dismissive_interaction_events: List[Dict[str, object]] = []
    limitations: List[str] = LIMITATIONS


def detect_acknowledgement_events(history: List[Dict[str, str]]) -> List[AcknowledgementEvent]:
    """Whole-transcript, same per-sentence/per-turn shape as opening_evidence.
    Speaker attribution (Step 9): only nurse turns are scanned."""
    events: List[AcknowledgementEvent] = []
    for idx, turn in enumerate(history or []):
        if turn.get("role") != "nurse":
            continue
        for sentence in _sentences(turn.get("content", "")):
            tier = _acknowledgement_tier(sentence)
            if tier is None:
                continue
            events.append(AcknowledgementEvent(
                turn_index=idx, evidence_text=sentence,
                event_type=EVENT_ACKNOWLEDGEMENT if tier == "strong" else EVENT_ACKNOWLEDGEMENT_UNCERTAIN,
            ))
    return events


def detect_reflective_response_events(history: List[Dict[str, str]]) -> List[ReflectiveResponseEvent]:
    """Whole-transcript (needs the immediately preceding turn, Step 2/10).
    Speaker attribution (Step 9): only nurse turns are scanned; the
    preceding turn must be the patient's, or nothing is emitted (Step 2:
    never invent a relationship when none can be determined)."""
    events: List[ReflectiveResponseEvent] = []
    for idx, turn in enumerate(history or []):
        if turn.get("role") != "nurse":
            continue
        if idx == 0 or history[idx - 1].get("role") != "patient":
            continue
        preceding_text = history[idx - 1].get("content", "")
        preceding_kws = _keywords(preceding_text)
        for sentence in _sentences(turn.get("content", "")):
            if not _REFLECTION_FRAMING_RE.match(sentence):
                continue
            overlap = bool(preceding_kws & _keywords(sentence))
            events.append(ReflectiveResponseEvent(
                turn_index=idx, evidence_text=sentence,
                event_type=EVENT_REFLECTIVE_RESPONSE if overlap else EVENT_REFLECTIVE_RESPONSE_UNCERTAIN,
                related_patient_turns=[idx - 1],
            ))
    return events


def detect_attentiveness_evidence(history: List[Dict[str, str]]) -> AttentivenessEvidence:
    """Step 14 focused model -- bundles both new detectors' output plus a
    reused (not re-implemented) dismissive_response reading, for direct
    testing/golden-case inspection. speaking_evidence.py calls
    detect_acknowledgement_events/detect_reflective_response_events
    directly (same per-detector call shape as every other detector in this
    family) and reads dismissive_response from its own existing
    detect_nurse_events call -- this bundling function is a second,
    read-only view for callers that want the whole A2 picture at once."""
    history = history or []
    dismissive: List[Dict[str, object]] = []
    for idx, turn in enumerate(history):
        if turn.get("role") != "nurse":
            continue
        for ev in detect_nurse_events(turn.get("content", "")):
            if ev["event"] == "dismissive_response":
                dismissive.append({"turn_index": idx, "evidence_text": ev["evidence"]})
    return AttentivenessEvidence(
        acknowledgement_events=detect_acknowledgement_events(history),
        reflective_response_events=detect_reflective_response_events(history),
        dismissive_interaction_events=dismissive,
    )


if __name__ == "__main__":
    # Explicit interpersonal acknowledgement.
    ack = detect_acknowledgement_events([{"role": "nurse", "content": "I see."}])
    assert len(ack) == 1 and ack[0].event_type == EVENT_ACKNOWLEDGEMENT

    # Acknowledgement following a patient concern (context-aware -- sentence
    # split keeps "I see." separate from the follow-up question, both fire
    # independently: A2 here, concern_exploration/B2 elsewhere).
    ack2 = detect_acknowledgement_events([
        {"role": "patient", "content": "I've been struggling with the injections."},
        {"role": "nurse", "content": "I see. Tell me more about what's worrying you."},
    ])
    assert len(ack2) == 1 and ack2[0].evidence_text == "I see."

    # Clinical "I understand" false positive (Step 22) -- must NOT match.
    assert detect_acknowledgement_events([
        {"role": "nurse", "content": "I understand the medication schedule."},
    ]) == []

    # "Okay, take this twice daily." must NOT become acknowledgement merely
    # because it begins with "Okay" (Step 22).
    assert detect_acknowledgement_events([
        {"role": "nurse", "content": "Okay, take this twice daily."},
    ]) == []

    # Ambiguous/uncertain acknowledgement -- contrastive pivot.
    ack_unc = detect_acknowledgement_events([
        {"role": "nurse", "content": "I understand, but we still need to proceed."},
    ])
    assert len(ack_unc) == 1 and ack_unc[0].event_type == EVENT_ACKNOWLEDGEMENT_UNCERTAIN

    # Patient-speaker false positive -- patient's own "I understand." must
    # never produce candidate evidence.
    assert detect_acknowledgement_events([
        {"role": "patient", "content": "I understand."},
    ]) == []

    # Multiple acknowledgement events across a session.
    multi = detect_acknowledgement_events([
        {"role": "nurse", "content": "I see."},
        {"role": "patient", "content": "It's been hard."},
        {"role": "nurse", "content": "Thank you for sharing that."},
    ])
    assert len(multi) == 2

    # Reflective response with lexical overlap.
    refl = detect_reflective_response_events([
        {"role": "patient", "content": "I'm worried about the injections."},
        {"role": "nurse", "content": "You're worried the injections may be painful."},
    ])
    assert len(refl) == 1 and refl[0].event_type == EVENT_REFLECTIVE_RESPONSE
    assert refl[0].related_patient_turns == [0]

    # Reflective framing with no keyword overlap -- kept as uncertain.
    refl_unc = detect_reflective_response_events([
        {"role": "patient", "content": "I'm worried about the injections."},
        {"role": "nurse", "content": "You're feeling quite nervous today."},
    ])
    assert len(refl_unc) == 1 and refl_unc[0].event_type == EVENT_REFLECTIVE_RESPONSE_UNCERTAIN

    # Delayed response (2+ turns later): links only to the immediately
    # preceding patient turn ("Okay."), never invents a relationship back to
    # the original concern turn two turns earlier -- no overlap with "Okay."
    # so it's uncertain, not confirmed.
    delayed = detect_reflective_response_events([
        {"role": "patient", "content": "I'm worried about the injections."},
        {"role": "nurse", "content": "Let's talk about your medication first."},
        {"role": "patient", "content": "Okay."},
        {"role": "nurse", "content": "You're worried about the injections."},
    ])
    assert len(delayed) == 1
    assert delayed[0].event_type == EVENT_REFLECTIVE_RESPONSE_UNCERTAIN
    assert delayed[0].related_patient_turns == [2]

    # Preceding turn is the nurse's own, not the patient's -- nothing to
    # link, nothing emitted (Step 2: never invent a relationship).
    no_link = detect_reflective_response_events([
        {"role": "patient", "content": "I'm worried about the injections."},
        {"role": "nurse", "content": "You're worried about the injections."},
        {"role": "nurse", "content": "You're worried about the injections, right?"},
    ])
    assert len(no_link) == 1  # only the first nurse turn (idx 1) links; idx 2 does not

    # Speaker attribution -- patient reflection-shaped text never fires.
    assert detect_reflective_response_events([
        {"role": "patient", "content": "I'm worried."},
        {"role": "patient", "content": "You're right, it's scary."},
    ]) == []

    # Determinism.
    assert detect_acknowledgement_events([{"role": "nurse", "content": "I see."}]) == ack

    bundled = detect_attentiveness_evidence([
        {"role": "patient", "content": "I'm scared."},
        {"role": "nurse", "content": "Don't worry, you'll be fine."},
    ])
    assert len(bundled.dismissive_interaction_events) == 1
    assert bundled.dismissive_interaction_events[0]["turn_index"] == 1

    print("attentiveness_evidence self-check OK")
