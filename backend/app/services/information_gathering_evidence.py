"""Information Gathering clarification & summarisation (D4/D5) detector (Step 21D).

Fourth dedicated Information Gathering detector after question_behaviour.py's
D2/D3 (21A). Same shape, same limitation: this classifies SURFACE FORM
(explicit clarification/summary phrasing), not whether the clarification or
summary was actually effective. A rare phrasing outside the patterns below
is missed, not mis-scored -- there is no score here, only evidence
(criterion_evidence.py's MISSING vs NEGATIVE rule).

    D4: "clarifying statements which are vague or need amplification" ->
        emits "clarification_request" (explicit "what do you mean"/"clarify"
        wording) / "clarification_uncertain" (anaphoric "tell me more about
        that/this" -- plausibly clarification, plausibly plain elaboration,
        Step 3/16: never forced to a confident classification)
    D5: "summarising information to encourage correction/invite further
        information" -> emits "summary_statement" / "summary_uncertain"
        (a bare "So, you've..." recap with no other strengthening signal)
        / "summary_check" (a correction-inviting sentence -- "Is that
        right?" -- co-occurring with a summary in the same turn, Step 6:
        tagged as its own aspect so "summary only" stays distinguishable
        from "summary + correction invitation")

D4/D5 vs C3 (structure_evidence.py): the official D5 examples in the task
spec ("Just to summarise...", "To recap...") are lexically identical to
C3's own organizing "summary" marker ("In summary, ..."). This is
deliberate overlap, not a bug -- Step 12 of the task spec: "One turn can
legitimately support both if it contains both functions." No
deduplication is performed, same as D2/C1/C2 overlaps elsewhere in this
detector family.

D4/D5 vs E4: E4's comprehension-check phrasing ("does that make sense",
"can you tell me how you'll take it") lives in patient_state.py's
_UNDERSTANDING_CHECK_PHRASES / is forward-looking about information the
NURSE just gave. D5 patterns here all reference what the PATIENT said
("you've", "what I'm hearing", "from what you've told me") -- no lexical
overlap between the two vocabularies.

Both detectors need the FULL history (a clarification/summary references a
prior -- or following -- PATIENT turn), so, like C1/C3, they run ONCE over
the whole transcript rather than per nurse turn.

LIMITATIONS (Step 24 of this module's docstring; restated in the task's
final report):
  - purely lexical: a genuine clarification/summary phrased outside the
    patterns below is missed, not flagged as evidence-absent-because-
    ineffective (see MISSING vs NEGATIVE above).
  - related_patient_turns (D5) is a keyword-overlap heuristic (reuses
    patient_state._keywords, same stopword-filtered significant-word
    approach used for concern/hidden-info matching elsewhere in this
    codebase), never an LLM/semantic call (Step 5/19 of the task spec) --
    it can miss a full paraphrase with no shared word, or over-link a
    generic word that happens to recur.
  - no ASR punctuation robustness: a "?" or "," dropped by transcription
    can shift a sentence between tiers.
  - elaboration vs clarification (Step 3) has a genuine grey zone this
    detector resolves conservatively (uncertain, never forced).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from pydantic import BaseModel

from app.services.patient_state import _keywords

EVENT_CLARIFICATION_REQUEST = "clarification_request"
EVENT_CLARIFICATION_UNCERTAIN = "clarification_uncertain"
EVENT_SUMMARY = "summary_statement"
EVENT_SUMMARY_UNCERTAIN = "summary_uncertain"
EVENT_SUMMARY_CHECK = "summary_check"

PROVENANCE_DETERMINISTIC = "deterministic_rule"
EVIDENCE_LEVEL_DETERMINISTIC = "L2_deterministic"

LIMITATIONS: List[str] = [
    "Detects surface-form clarification/summary phrasing only -- a genuine "
    "clarification or summary worded outside the known patterns is missed, "
    "not scored as absent.",
    "related_patient_turns uses deterministic keyword overlap, not semantic "
    "understanding -- a full paraphrase with no shared significant word can "
    "be missed, and a generic recurring word can over-link an unrelated turn.",
    "No ASR punctuation robustness -- a dropped '?' or ',' can shift a "
    "sentence between the confirmed/uncertain tiers.",
    "Clarification vs elaboration is a genuine grey zone; this detector "
    "resolves it conservatively (uncertain or no event), never forced.",
]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


# ── D4 clarification ────────────────────────────────────────────────────
# Explicit clarification vocabulary (Step 1) -- always confident evidence.
_STRONG_CLARIFY_RE = re.compile(
    r"\b(?:what do you mean|what does that mean|what did you mean|what exactly do you mean"
    r"|could you clarify|can you clarify|could you explain what you mean|can you explain what you mean"
    r"|could you explain that|can you explain that)\b",
    re.IGNORECASE,
)
# Anaphoric-only "tell me more" (Step 3): "about that/this" points back at
# something just said, unlike "about your pain" (Step 24 false positive),
# which names an ordinary topic and is left alone entirely.
_WEAK_CLARIFY_RE = re.compile(
    r"\b(?:tell me more about (?:that|this)|could you tell me more about (?:that|this)"
    r"|can you tell me more about (?:that|this))\b",
    re.IGNORECASE,
)


def _clarification_tier(sentence: str) -> Optional[str]:
    if _STRONG_CLARIFY_RE.search(sentence):
        return "strong"
    if _WEAK_CLARIFY_RE.search(sentence):
        return "weak"
    return None


# ── D5 summarisation ────────────────────────────────────────────────────
# Explicit summary framing (Step 4's own example list) -- always confident.
_STRONG_SUMMARY_RE = re.compile(
    r"^(?:let me make sure i(?:'ve| have) understood"
    r"|just to summarise|just to summarize"
    r"|to recap|to summarise|to summarize"
    r"|so what i'?m hearing is"
    r"|let me check i'?ve got this right"
    r"|from what you'?ve told me"
    r"|if i understand you correctly)\b",
    re.IGNORECASE,
)
# "So, you've..." (Step 4/7): second-person recap shape. Gated on "you" as
# the subject specifically so "So I'll explain the treatment now." (Step 24
# false positive) never matches -- first person, not a recap of the patient.
_WEAK_SO_YOU_RE = re.compile(r"^so,?\s+you\b", re.IGNORECASE)

_CORRECTION_INVITATION_RE = re.compile(
    r"\b(?:have i understood (?:that|you) correctly|is that right|did i get that right"
    r"|have i got that right|does that sound right|is that correct)\b",
    re.IGNORECASE,
)


def _summary_tier(sentence: str) -> Optional[str]:
    if _STRONG_SUMMARY_RE.match(sentence):
        return "strong"
    if _WEAK_SO_YOU_RE.match(sentence):
        return "weak_so_you"
    return None


def _is_correction_invitation(sentence: str) -> bool:
    return bool(_CORRECTION_INVITATION_RE.search(sentence))


def _multi_clause(sentence: str) -> bool:
    """A "so you..." sentence naming >=2 distinct facts (commas/"and"s) is
    aggregation, not a single-fact repetition (Step 7) -- promoted to a
    confirmed summary even with no correction invitation present."""
    return sentence.count(",") + len(re.findall(r"\band\b", sentence, re.IGNORECASE)) >= 2


def _related_patient_turn_for_clarification(history: List[Dict[str, str]], turn_index: int) -> Optional[int]:
    """Step 2: only the immediately preceding turn, and only if it's the
    patient -- never a guessed earlier turn (Step 2: "Do not invent
    relationships when none can be determined")."""
    if turn_index > 0 and history[turn_index - 1].get("role") == "patient":
        return turn_index - 1
    return None


def _response_patient_turn(history: List[Dict[str, str]], turn_index: int) -> Optional[int]:
    """Step 9: the patient's own clarifying reply, if the very next turn is
    theirs -- supplementary evidence only, never changes the event's tier."""
    if turn_index + 1 < len(history) and history[turn_index + 1].get("role") == "patient":
        return turn_index + 1
    return None


def _related_patient_turns_for_summary(summary_sentence: str, history: List[Dict[str, str]], before_idx: int) -> List[int]:
    """Step 5/8: every earlier PATIENT turn sharing a significant keyword
    with the summary sentence, in chronological order -- deterministic
    lexical overlap only (Step 5: "Do not use an LLM to infer semantic
    overlap"), so a full paraphrase with no shared word is missed rather
    than guessed (documented in this module's LIMITATIONS)."""
    summary_kws = _keywords(summary_sentence)
    if not summary_kws:
        return []
    related: List[int] = []
    for idx in range(before_idx):
        if history[idx].get("role") != "patient":
            continue
        if _keywords(history[idx].get("content", "")) & summary_kws:
            related.append(idx)
    return related


class ClarificationEvent(BaseModel):
    turn_index: int
    evidence_text: str
    event_type: str  # EVENT_CLARIFICATION_REQUEST | EVENT_CLARIFICATION_UNCERTAIN
    related_patient_turns: List[int] = []
    response_patient_turn: Optional[int] = None
    provenance: str = PROVENANCE_DETERMINISTIC
    evidence_level: str = EVIDENCE_LEVEL_DETERMINISTIC


class SummaryEvent(BaseModel):
    turn_index: int
    evidence_text: str
    event_type: str  # EVENT_SUMMARY | EVENT_SUMMARY_UNCERTAIN | EVENT_SUMMARY_CHECK
    related_patient_turns: List[int] = []
    has_correction_invitation: bool = False
    provenance: str = PROVENANCE_DETERMINISTIC
    evidence_level: str = EVIDENCE_LEVEL_DETERMINISTIC


class InformationGatheringEvidence(BaseModel):
    clarification_events: List[ClarificationEvent] = []
    summary_events: List[SummaryEvent] = []
    limitations: List[str] = LIMITATIONS


def detect_clarification_events(history: List[Dict[str, str]]) -> List[ClarificationEvent]:
    """Whole-transcript (a clarification links to a PRIOR patient turn and
    an optional FOLLOWING one, Step 2/9), called once, same shape as
    sequencing_evidence.detect_sequence_events. One nurse turn can carry
    more than one clarification sentence (Step 10: multiple events)."""
    events: List[ClarificationEvent] = []
    for idx, turn in enumerate(history or []):
        if turn.get("role") != "nurse":
            continue
        for sentence in _sentences(turn.get("content", "")):
            tier = _clarification_tier(sentence)
            if tier is None:
                continue
            related = _related_patient_turn_for_clarification(history, idx)
            events.append(ClarificationEvent(
                turn_index=idx, evidence_text=sentence,
                event_type=EVENT_CLARIFICATION_REQUEST if tier == "strong" else EVENT_CLARIFICATION_UNCERTAIN,
                related_patient_turns=[related] if related is not None else [],
                response_patient_turn=_response_patient_turn(history, idx),
            ))
    return events


def detect_summary_events(history: List[Dict[str, str]]) -> List[SummaryEvent]:
    """Whole-transcript, same reason as detect_clarification_events. One
    summary_check event is emitted alongside its summary (Step 6) --
    never standalone, since a bare "Is that right?" with no summary in the
    same turn isn't evidence of D5 at all."""
    events: List[SummaryEvent] = []
    for idx, turn in enumerate(history or []):
        if turn.get("role") != "nurse":
            continue
        sentences = _sentences(turn.get("content", ""))

        strong_sentence: Optional[str] = None
        weak_sentence: Optional[str] = None
        correction_sentence: Optional[str] = None
        for sentence in sentences:
            tier = _summary_tier(sentence)
            if tier == "strong" and strong_sentence is None:
                strong_sentence = sentence
            elif tier == "weak_so_you" and weak_sentence is None:
                weak_sentence = sentence
            if correction_sentence is None and _is_correction_invitation(sentence):
                correction_sentence = sentence

        summary_sentence: Optional[str] = None
        event_type: Optional[str] = None
        if strong_sentence is not None:
            summary_sentence, event_type = strong_sentence, EVENT_SUMMARY
        elif weak_sentence is not None:
            summary_sentence = weak_sentence
            promoted = _multi_clause(weak_sentence) or correction_sentence is not None
            event_type = EVENT_SUMMARY if promoted else EVENT_SUMMARY_UNCERTAIN

        if summary_sentence is None:
            continue

        related = _related_patient_turns_for_summary(summary_sentence, history, idx)
        events.append(SummaryEvent(
            turn_index=idx, evidence_text=summary_sentence, event_type=event_type,
            related_patient_turns=related, has_correction_invitation=correction_sentence is not None,
        ))
        if correction_sentence is not None:
            events.append(SummaryEvent(
                turn_index=idx, evidence_text=correction_sentence, event_type=EVENT_SUMMARY_CHECK,
                related_patient_turns=related, has_correction_invitation=True,
            ))
    return events


def detect_information_gathering_evidence(history: List[Dict[str, str]]) -> InformationGatheringEvidence:
    """Step 14 focused model -- bundles both detectors' output for direct
    testing/inspection. speaking_evidence.py calls the two detector
    functions above directly (same per-detector call shape as every other
    detector in this family); this entry point exists for callers that
    want the whole D4/D5 picture at once (golden cases, admin inspection)."""
    return InformationGatheringEvidence(
        clarification_events=detect_clarification_events(history),
        summary_events=detect_summary_events(history),
    )


if __name__ == "__main__":
    assert detect_clarification_events([
        {"role": "patient", "content": "It's been getting worse."},
        {"role": "nurse", "content": "What do you mean by worse?"},
    ]) == [ClarificationEvent(
        turn_index=1, evidence_text="What do you mean by worse?",
        event_type=EVENT_CLARIFICATION_REQUEST, related_patient_turns=[0], response_patient_turn=None,
    )]

    assert detect_clarification_events([{"role": "nurse", "content": "When did the pain start?"}]) == []
    assert detect_clarification_events([{"role": "nurse", "content": "Tell me more about your symptoms."}]) == []

    weak = detect_clarification_events([{"role": "nurse", "content": "Could you tell me more about that?"}])
    assert len(weak) == 1 and weak[0].event_type == EVENT_CLARIFICATION_UNCERTAIN

    seq = detect_clarification_events([
        {"role": "patient", "content": "It's been strange."},
        {"role": "nurse", "content": "What do you mean by strange?"},
        {"role": "patient", "content": "It feels like the room is spinning."},
    ])
    assert len(seq) == 1 and seq[0].related_patient_turns == [0] and seq[0].response_patient_turn == 2

    assert detect_summary_events([{"role": "nurse", "content": "So I'll explain the treatment now."}]) == []
    assert detect_summary_events([{"role": "nurse", "content": "You said yesterday that you felt tired."}]) == []

    multi_turn = detect_summary_events([
        {"role": "patient", "content": "I've had pain for three days."},
        {"role": "nurse", "content": "Okay, thank you."},
        {"role": "patient", "content": "It's worse when I walk."},
        {"role": "nurse", "content": "I see."},
        {"role": "patient", "content": "I'm worried about work."},
        {"role": "nurse", "content": (
            "So you've had pain for three days, it's worse when you walk, "
            "and you're concerned about work. Have I understood you correctly?"
        )},
    ])
    summary = [e for e in multi_turn if e.event_type == EVENT_SUMMARY]
    checks = [e for e in multi_turn if e.event_type == EVENT_SUMMARY_CHECK]
    assert len(summary) == 1 and summary[0].related_patient_turns == [0, 2, 4]
    assert len(checks) == 1 and checks[0].related_patient_turns == [0, 2, 4]

    print("information_gathering_evidence self-check OK")
