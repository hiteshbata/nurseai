"""Providing Structure (C1) detector (Step 21C).

Third dedicated Providing Structure detector after question_behaviour.py's
D2/D3 (21A) and structure_evidence.py's C2/C3 (21B). Same shape, same
limitation: this classifies SURFACE FORM (explicit sequencing language), not
whether the consultation was actually well sequenced. A rare phrasing
outside the patterns below is missed, not mis-scored -- there is no score
here, only evidence (criterion_evidence.py's MISSING vs NEGATIVE rule).

    C1: "sequencing the interview purposefully and logically" -> emits
        "consultation_sequence_marker" / "consultation_sequence_marker_partial"
        / "consultation_sequence_uncertain"

C1 vs C3 (structure_evidence.py): C3's ordinal regex fires on a bare
"First, your medication." -- no verb required, because C3 is about
organizing an EXPLANATION. C1 requires the marker to be paired with a
first-person future-action verb ("I'll ask", "we'll discuss", "let's talk
about") naming a consultation stage -- because C1 is about sequencing the
INTERACTION itself. A turn can legitimately satisfy both (e.g. "First, I'd
like to explain what's going on."), but C1 evidence is never manufactured
just because C3 found an ordinal marker (see module test/golden cases).

C1 vs C2 (structure_evidence.py): independent detectors run on the same
turn text; a turn like "First, let's talk about your symptoms." can
legitimately produce both a C2 signposting_detected and a C1 sequence
marker -- no deduplication across criteria (Step 15/16 of the task spec).

Sequence grouping mirrors structure_evidence.detect_organization_sequences:
consecutive NURSE turns each carrying a strong marker belong to one
sequence; a nurse turn with no strong marker closes it. One marker with
nothing after it is "partial" (Step 6) -- never "poor sequencing", just
less observable evidence. Uncertain markers (ordinal/connector present but
no recognized consultation verb) are reported standalone, never grouped
into a sequence -- they are not confirmed sequencing evidence (Step 13).

LIMITATION (Step 7): a consultation can be logically sequenced
(symptoms -> history -> explanation -> plan) with no explicit marker at
all. This module cannot and does not attempt to detect that -- silence
here means "no explicit sequencing evidence detected", never "poorly
sequenced" (Step 14).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple, TypedDict

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class _Event(TypedDict):
    event: str
    turn_index: int
    evidence: str


class _Marker(TypedDict):
    turn_index: int
    text: str
    weak: bool


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


# ── Vocabulary ──────────────────────────────────────────────────────────────
# Consultation-stage action verbs (Step 2/9): what makes a marker about
# SEQUENCING THE INTERACTION rather than an ordinary temporal remark.
_VERB_STEMS = [
    r"ask(?:ed)?(?:\s+you)?(?:\s+about)?", r"talk(?:ed)?(?:\s+to\s+you)?\s+about",
    r"discuss(?:ed)?", r"explain(?:ed)?", r"examine[ds]?",
    r"go(?:ne)?\s+through", r"went\s+through", r"check(?:ed)?", r"look(?:ed)?\s+at",
    r"come\s+back\s+to", r"came\s+back\s+to", r"move(?:d)?\s+on\s+to",
    r"address(?:ed)?", r"find\s+out\s+about", r"found\s+out\s+about",
    r"walk(?:ed)?(?:\s+you)?\s+through", r"cover(?:ed)?", r"go(?:ne)?\s+over", r"went\s+over",
    r"make\s+sure", r"understand(?:s|ing)?",
]
_VERB_ALT = "(?:" + "|".join(_VERB_STEMS) + ")"
_VERB_RE = re.compile(r"\b" + _VERB_ALT + r"\b", re.IGNORECASE)

# First-person future/procedural framing (Step 9/11): distinguishes "we'll
# discuss your medication" (an upcoming step) from "we discuss your
# medication every visit" (habitual, not sequencing).
_MODAL_PHRASES = [
    "i'll", "i will", "we'll", "we will", "let's", "let us", "i'm going to",
    "i am going to", "we're going to", "we are going to", "i'd like to",
    "i would like to", "we'd like to", "we would like to",
]
_MODAL_RE = re.compile(r"\b(?:" + "|".join(re.escape(m) for m in _MODAL_PHRASES) + r")\b", re.IGNORECASE)

# Sentence-initial ordinal/connector markers (Step 2/8). "first" alone stays
# comma/colon/end-anchored, same as structure_evidence's C3 rule, so "First
# thing in the morning..." never matches (Step 19). The rest tolerate a
# following word boundary since "then"/"next"/etc. carry far less "X thing"
# ambiguity, and the downstream modal+verb gate filters ordinary temporal use
# (e.g. "Then I felt better.").
_STRICT_FIRST_RE = re.compile(r"^first(?:,|:|$)", re.IGNORECASE)
_LOOSE_MARKER_RE = re.compile(r"^(?:second|third|next|then|finally|lastly|after that|before that)\b", re.IGNORECASE)
_LET_FIRST_RE = re.compile(r"^(?:let me|let's|let us)\s+first\b", re.IGNORECASE)

# Before/after/once structural clauses (Step 8): "before we discuss...",
# "after we've talked about...", "once we've covered...". Requires the
# we/I + (optional modal) + consultation verb shape, anywhere in the
# sentence -- NOT sentence-initial only, since "...but before we discuss
# the results, let's check your vitals" is still valid mid-sentence.
_BEFORE_AFTER_RE = re.compile(
    r"\b(?:before|after|once)\s+(?:that\s+)?(?:we|i)(?:'ve|'ll|'re|'m)?\s*"
    r"(?:have\s+|will\s+|are\s+going\s+to\s+|am\s+going\s+to\s+)?" + _VERB_ALT + r"\b",
    re.IGNORECASE,
)


def _classify(sentence: str) -> Optional[Tuple[bool]]:
    """Returns `weak` (bool) if `sentence` carries C1 evidence, else None."""
    lower = sentence.strip().lower()

    if _BEFORE_AFTER_RE.search(lower):
        return (False,)

    let_first = bool(_LET_FIRST_RE.match(lower))
    marker = bool(_STRICT_FIRST_RE.match(lower) or _LOOSE_MARKER_RE.match(lower))
    if not (marker or let_first):
        return None

    has_modal = bool(_MODAL_RE.search(lower))
    has_verb = bool(_VERB_RE.search(lower))
    if has_verb and (has_modal or let_first):
        return (False,)
    if has_modal or has_verb or let_first:
        return (True,)  # marker present, but verb or modal framing missing/ambiguous
    return None


def _turn_markers(turn_index: int, content: str) -> List[_Marker]:
    markers: List[_Marker] = []
    for sentence in _sentences(content):
        result = _classify(sentence)
        if result is not None:
            markers.append({"turn_index": turn_index, "text": sentence, "weak": result[0]})
    return markers


def _flush_sequence(items: List[_Marker]) -> List[_Event]:
    event_name = "consultation_sequence_marker_partial" if len(items) < 2 else "consultation_sequence_marker"
    return [{"event": event_name, "turn_index": m["turn_index"], "evidence": m["text"]} for m in items]


def detect_sequence_events(history: List[Dict[str, str]]) -> List[_Event]:
    """Whole-transcript (a sequence spans several nurse turns, same as C3's
    detect_organization_marker_events). Called ONCE on the full history, not
    per turn, so speaking_evidence.py can fold the result straight into
    candidate_events like any other detector output."""
    nurse_turns = [(idx, t.get("content", "")) for idx, t in enumerate(history or []) if t.get("role") == "nurse"]

    events: List[_Event] = []
    current_strong: List[_Marker] = []
    for idx, content in nurse_turns:
        markers = _turn_markers(idx, content)
        strong = [m for m in markers if not m["weak"]]
        for weak in (m for m in markers if m["weak"]):
            events.append({"event": "consultation_sequence_uncertain", "turn_index": idx, "evidence": weak["text"]})

        if strong:
            current_strong.extend(strong)
        elif current_strong:
            events.extend(_flush_sequence(current_strong))
            current_strong = []
    if current_strong:
        events.extend(_flush_sequence(current_strong))
    return events


if __name__ == "__main__":
    assert detect_sequence_events([
        {"role": "nurse", "content": "First, I'll ask you about your symptoms."},
        {"role": "nurse", "content": "Then we'll discuss your medication."},
    ]) == [
        {"event": "consultation_sequence_marker", "turn_index": 0, "evidence": "First, I'll ask you about your symptoms."},
        {"event": "consultation_sequence_marker", "turn_index": 1, "evidence": "Then we'll discuss your medication."},
    ]

    partial = detect_sequence_events([{"role": "nurse", "content": "First, let's discuss your symptoms."}])
    assert len(partial) == 1 and partial[0]["event"] == "consultation_sequence_marker_partial"

    assert detect_sequence_events([{"role": "nurse", "content": "Before coming here, you felt dizzy."}]) == []
    assert detect_sequence_events([{"role": "nurse", "content": "After lunch I take my medication."}]) == []
    assert detect_sequence_events([{"role": "nurse", "content": "First thing in the morning I take my medication."}]) == []
    assert detect_sequence_events([{"role": "nurse", "content": "Then I felt better."}]) == []

    before_after = detect_sequence_events([{
        "role": "nurse",
        "content": "Before we discuss the results, let's check your vitals.",
    }])
    assert len(before_after) == 1 and before_after[0]["event"] == "consultation_sequence_marker_partial"

    print("sequencing_evidence self-check OK")
