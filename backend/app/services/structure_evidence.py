"""Providing Structure (C2/C3) detector (Step 21B).

Second dedicated clinical detector after question_behaviour.py's D2/D3 (Step
21A) -- same shape, same limitation: this classifies SURFACE FORM (explicit
signposting/organizing phrases), not whether the interview was actually well
structured. A rare phrasing outside the patterns below is missed, not
mis-scored -- there is no score here, only evidence (criterion_evidence.py's
MISSING vs NEGATIVE rule).

    C2: "signposting changes in topic" -> emits "signposting_detected" /
        "signposting_uncertain" / "topic_transition_detected"
    C3: "using organising techniques in explanations" -> emits
        "organization_marker" / "organization_marker_partial"

C2 is per-turn (detect_structure_events), same contract as
question_behaviour.detect_question_events -- one nurse turn in, zero or more
independent events out. C3 needs the full transcript (an organizing sequence
like "First... Second... Finally..." spans several nurse turns), so
detect_organization_sequences/detect_organization_marker_events take the
whole `history`, called once by speaking_evidence.py rather than per turn.

Sequence grouping (Step 6/7): consecutive NURSE turns (patient turns don't
break a sequence, they're simply not scanned) that each carry an
organizing marker belong to one sequence. A nurse turn with no marker closes
the sequence. A sequence with only one marker ("First..." with nothing
after) is "partial_structure" (Step 7) -- never "poor structure", just less
observable evidence. To keep the existing CandidateEvent(event, turn_index,
evidence_text) shape unmodified (Step 18/25: smallest additive change, don't
touch reconciliation architecture), a sequence's partial/complete status is
carried entirely in the event NAME (organization_marker vs
organization_marker_partial) rather than a new metadata field -- the
sequence itself is still fully reconstructable downstream because every
marker keeps its own turn_index and ordering is preserved.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, TypedDict

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class _Event(TypedDict):
    event: str
    evidence: str


class _Marker(TypedDict):
    turn_index: int
    type: str
    text: str


class _Sequence(TypedDict):
    turn_indexes: List[int]
    markers: List[_Marker]
    partial: bool


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


def _core(sentence: str) -> str:
    return sentence.rstrip(".!?").strip()


# ── C2 signposting ─────────────────────────────────────────────────────────
# Strong evidence requires a transition PHRASE, not a bare transition word
# (Step 3): "then"/"next"/"now" alone never qualify, only the verb phrases
# below ("let's talk about", "moving on to", ...).
_STRONG_SIGNPOST_RE = re.compile(
    r"\b(?:let'?s (?:talk about|discuss|look at|move on to|turn to)"
    r"|(?:i'?d like to|i would like to|i'?m going to|i will) (?:talk about|discuss|move on to|move to)"
    r"|moving on to|before we move on|next,? (?:let'?s|i'?d like to|i'?m going to|i will))\b",
    re.IGNORECASE,
)
# Captures the topic object named right after the verb phrase (Step 4) --
# no semantic topic modelling, just what the sentence itself names.
_TOPIC_CAPTURE_RE = re.compile(
    r"\b(?:talk about|discuss|look at|move on to|move to|turn to)\s+(.+)", re.IGNORECASE,
)
# Borderline phrasing (Step 14): plausibly a signpost but no explicit verb
# phrase or named topic -- kept distinct from signposting_detected rather
# than either promoted to strong evidence or silently dropped.
_WEAK_SIGNPOST_RE = re.compile(r"^(?:now|so|okay|ok|right),?\s+about\b", re.IGNORECASE)
_WEAK_MOVE_ON_RE = re.compile(r"^let'?s move on(?!\s+to)\b", re.IGNORECASE)


def detect_structure_events(nurse_message: str) -> List[_Event]:
    """One nurse turn -> zero or more {"event", "evidence"} entries (C2
    only). Mirrors question_behaviour.detect_question_events' shape so
    speaking_evidence.py can fold this into the same per-turn loop."""
    events: List[_Event] = []
    for sentence in _sentences(nurse_message):
        if _STRONG_SIGNPOST_RE.search(sentence):
            events.append({"event": "signposting_detected", "evidence": sentence})
            topic_match = _TOPIC_CAPTURE_RE.search(sentence)
            if topic_match:
                topic_text = topic_match.group(1).strip().rstrip(".!?").strip()
                if topic_text:
                    events.append({"event": "topic_transition_detected", "evidence": topic_text})
        elif _WEAK_SIGNPOST_RE.match(sentence) or _WEAK_MOVE_ON_RE.match(sentence):
            events.append({"event": "signposting_uncertain", "evidence": sentence})
    return events


# ── C3 explanation organization ─────────────────────────────────────────────
# Sentence-initial only, comma/colon/end-anchored for ordinals (Step 21): "First,"
# is a marker, "First thing in the morning..." is not.
_ORDINAL_RE = re.compile(r"^(?:first|second|third|fourth|next|finally|lastly)(?:,|:|$)", re.IGNORECASE)
_OPENER_RE = re.compile(r"^(?:there (?:are|is) \w+ (?:things?|points?)|(?:a few|several) (?:things|points))\b", re.IGNORECASE)
_POINT_RE = re.compile(r"^(?:one thing to remember|the main point is|the other point is)\b", re.IGNORECASE)
_SUMMARY_RE = re.compile(r"^(?:in summary|to summarize|to summarise|to recap|to sum up)\b", re.IGNORECASE)


def _match_marker_type(sentence: str) -> Optional[str]:
    core = _core(sentence)
    if _ORDINAL_RE.match(core):
        return "ordinal"
    if _OPENER_RE.match(core):
        return "opener"
    if _POINT_RE.match(core):
        return "point"
    if _SUMMARY_RE.match(core):
        return "summary"
    return None


def _close_sequence(markers: List[_Marker]) -> _Sequence:
    turn_indexes = sorted({m["turn_index"] for m in markers})
    return {"turn_indexes": turn_indexes, "markers": markers, "partial": len(markers) < 2}


def detect_organization_sequences(history: List[Dict[str, str]]) -> List[_Sequence]:
    """Whole-transcript (C3 needs multi-turn context, unlike C2). Returns one
    entry per contiguous run of marker-bearing nurse turns, markers kept in
    transcript order, turn_index preserved on each (Step 6)."""
    nurse_turns = [(idx, t.get("content", "")) for idx, t in enumerate(history or []) if t.get("role") == "nurse"]

    turn_markers: Dict[int, List[_Marker]] = {}
    for idx, content in nurse_turns:
        found = [
            {"turn_index": idx, "type": marker_type, "text": sentence}
            for sentence in _sentences(content)
            for marker_type in [_match_marker_type(sentence)]
            if marker_type
        ]
        if found:
            turn_markers[idx] = found

    sequences: List[_Sequence] = []
    current: List[_Marker] = []
    for idx, _content in nurse_turns:
        if idx in turn_markers:
            current.extend(turn_markers[idx])
        elif current:
            sequences.append(_close_sequence(current))
            current = []
    if current:
        sequences.append(_close_sequence(current))
    return sequences


def detect_organization_marker_events(history: List[Dict[str, str]]) -> List[_Event]:
    """Flattens detect_organization_sequences() into per-marker
    {"event", "turn_index", "evidence"} entries, called ONCE on the full
    history (not per turn) so speaking_evidence.py can fold the result into
    candidate_events the same way as any other detector output."""
    events: List[Dict] = []
    for seq in detect_organization_sequences(history):
        event_name = "organization_marker_partial" if seq["partial"] else "organization_marker"
        for marker in seq["markers"]:
            events.append({"event": event_name, "turn_index": marker["turn_index"], "evidence": marker["text"]})
    return events


if __name__ == "__main__":
    assert detect_structure_events("Now let's talk about your medication.") == [
        {"event": "signposting_detected", "evidence": "Now let's talk about your medication."},
        {"event": "topic_transition_detected", "evidence": "your medication"},
    ]
    assert detect_structure_events("Then I felt better.") == []
    assert detect_structure_events("First thing in the morning I take my medication.") == []

    seq = detect_organization_sequences([
        {"role": "nurse", "content": "There are three things I'd like to explain."},
        {"role": "patient", "content": "Okay."},
        {"role": "nurse", "content": "First, your medication."},
        {"role": "nurse", "content": "Second, your diet."},
        {"role": "nurse", "content": "Finally, your follow-up."},
    ])
    assert len(seq) == 1 and seq[0]["partial"] is False and seq[0]["turn_indexes"] == [0, 2, 3, 4]

    partial = detect_organization_sequences([{"role": "nurse", "content": "First, let's start with your chart."}])
    assert len(partial) == 1 and partial[0]["partial"] is True
    print("structure_evidence self-check OK")
