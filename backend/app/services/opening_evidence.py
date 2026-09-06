"""Relationship Building opening-interaction (A1) detector (Step 21G).

First dedicated detector for A1 -- previously a placeholder that took
whatever transcript turn happened to be first (patient or nurse) and always
carried a REASON_NO_OPENING_DETECTOR gap (see criterion_evidence.py's
former _map_a1). Same shape, same limitation as this codebase's other
deterministic clinical detectors (structure_evidence.py, sequencing_evidence.py,
question_behaviour.py): this classifies SURFACE FORM (explicit opening
phrases), not whether the opening was actually effective. A rare phrasing
outside the patterns below is missed, not mis-scored -- there is no score
here, only evidence (criterion_evidence.py's MISSING vs NEGATIVE rule).

    A1: "initiating the interaction appropriately (greeting, introductions,
        nature of interview)" -> emits "opening_greeting" /
        "opening_introduction" / "opening_role_identification" /
        "opening_purpose_setting"

OPENING WINDOW: A1 is about the BEGINNING of the interaction, not anything
said later. Only the first OPENING_WINDOW_NURSE_TURNS nurse turns (by
transcript order) are scanned -- a patient turn preceding the nurse's first
turn does not push the window back or block detection (a patient greeting
first, e.g. "Oh, hello, are you my nurse?", is common and does not change
what counts as the nurse's own opening). This is deliberately conservative:
a nurse opening that spans more turns than the window (e.g. small talk
before finally introducing themselves) is simply not detected, never
guessed at (Step 1 of this task's spec).

One nurse turn -> zero or more independent {"event", "turn_index",
"evidence"} entries, same per-sentence, independent-checks shape as
structure_evidence.detect_structure_events -- a single opening sentence
("Hello, my name is Sarah, I'll be your nurse today.") legitimately carries
greeting + introduction + role_identification at once.
"""
from __future__ import annotations

import re
from typing import Dict, List, TypedDict

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# Conservative window (Step 1): the nurse's opening realistically spans one
# turn, occasionally two if the patient interjects between greeting and
# purpose-setting. Not a large arbitrary number of turns.
OPENING_WINDOW_NURSE_TURNS = 2


class _Event(TypedDict):
    event: str
    turn_index: int
    evidence: str


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


_GREETING_RE = re.compile(
    r"^(?:hello|hi|hey|good morning|good afternoon|good evening)\b", re.IGNORECASE,
)

# Requires a capitalized word after the naming phrase (Step 9): "I'm going
# to..."/"I'm here to..." never match since "going"/"here" aren't proper
# nouns. The one real gap this creates -- an all-lowercase transcript, or a
# name that happens to also be a common capitalized word -- is a documented
# limitation of surface-form detection, not fixed here.
_INTRODUCTION_RE = re.compile(
    r"\b(?:[Mm]y name is|I'?m|I am)\s+(?:nurse\s+)?[A-Z][a-zA-Z'-]*\b",
)

_ROLE_RE = re.compile(
    r"\b(?:i'?ll be (?:your |one of )?(?:the )?nurse|i'?m (?:your |one of )?(?:the )?nurse"
    r"|looking after you|caring for you|assigned to (?:your care|look after you))\b",
    re.IGNORECASE,
)


# "check" is deliberately excluded from the verb list -- "I'm going to check
# your blood pressure" is a specific clinical action, not a statement of the
# CONVERSATION's purpose (Step 1: surface-form only, no guessing intent).
_PURPOSE_RE = re.compile(
    r"\b(?:i'?d like to|i would like to|i'?m going to|i am going to|i'?ll|i will"
    r"|i just want to|i want to|i need to)\s+"
    r"(?:ask you|talk to you|discuss|go through|explain|find out)\b",
    re.IGNORECASE,
)


def detect_opening_events(history: List[Dict[str, str]]) -> List[_Event]:
    """Scans only the first OPENING_WINDOW_NURSE_TURNS nurse turns (by
    transcript order, regardless of what role spoke first). Called once by
    speaking_evidence.py on the full history, same call-site shape as
    sequencing_evidence.detect_sequence_events."""
    nurse_turns = [
        (idx, t.get("content", "")) for idx, t in enumerate(history or []) if t.get("role") == "nurse"
    ][:OPENING_WINDOW_NURSE_TURNS]

    events: List[_Event] = []
    for idx, content in nurse_turns:
        for sentence in _sentences(content):
            if _GREETING_RE.match(sentence):
                events.append({"event": "opening_greeting", "turn_index": idx, "evidence": sentence})
            if _INTRODUCTION_RE.search(sentence):
                events.append({"event": "opening_introduction", "turn_index": idx, "evidence": sentence})
            if _ROLE_RE.search(sentence):
                events.append({"event": "opening_role_identification", "turn_index": idx, "evidence": sentence})
            if _PURPOSE_RE.search(sentence):
                events.append({"event": "opening_purpose_setting", "turn_index": idx, "evidence": sentence})
    return events


if __name__ == "__main__":
    assert detect_opening_events([{"role": "nurse", "content": "Hello there."}]) == [
        {"event": "opening_greeting", "turn_index": 0, "evidence": "Hello there."},
    ]
    assert detect_opening_events([{"role": "nurse", "content": "I'm going to check your blood pressure."}]) == []
    assert detect_opening_events([]) == []
    combined = detect_opening_events([{
        "role": "nurse",
        "content": "Hello there. My name is Sarah. I'll be your nurse today. I'd like to ask you some questions.",
    }])
    assert {e["event"] for e in combined} == {
        "opening_greeting", "opening_introduction", "opening_role_identification", "opening_purpose_setting",
    }
    print("opening_evidence self-check OK")
