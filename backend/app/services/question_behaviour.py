"""Information Gathering question-behaviour detector (Step 21A).

First dedicated detector for D2/D3 (see criterion_evidence.py's module
docstring on why most indicators are still gap-only). Deterministic,
keyword/regex-based -- same limitation as patient_state.detect_nurse_events:
this classifies SURFACE FORM (how a question is phrased), not whether it was
the right question to ask. A rare phrasing outside the patterns below is
missed, not mis-scored (there is no score here, only evidence -- see
criterion_evidence.py's MISSING vs NEGATIVE rule).

    D2: "using initially open questions, appropriately moving to closed
        questions" -> emits "open_question" / "closed_question"
    D3: "NOT using compound questions/leading questions" -> emits
        "compound_question" / "leading_question"

One nurse turn can carry more than one event (a leading, compound question
is still exactly one open/closed classification too), matching
detect_nurse_events' own "independent checks per turn" shape so
speaking_evidence.py can append this detector's output the same way.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

_WORD_RE = re.compile(r"[a-z']+")

# One "?"-terminated clause per match -- a turn with more than one of these
# is itself compound-question evidence (two separate questions in one turn).
_QUESTION_CLAUSE_RE = re.compile(r"[^?]*\?")

_DISCOURSE_PREFIX_RE = re.compile(r"^(?:so|okay|ok|well|now|alright|and|um|uh|then),?\s+")

_OPEN_STARTERS = {"what", "how", "why", "when", "where", "who", "which", "whose"}
_OPEN_PHRASES = [
    "tell me about", "tell me more", "can you describe", "can you tell me",
    "could you tell me", "could you describe", "describe", "walk me through",
    "what can you tell me",
]

_CLOSED_AUX = {
    "do", "does", "did", "is", "are", "was", "were", "have", "has", "had",
    "can", "could", "will", "would", "should", "shall", "am", "may", "might",
    "don't", "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't",
    "haven't", "hasn't", "hadn't", "can't", "couldn't", "won't", "wouldn't", "shouldn't",
}

# Generic tag-question shape: a comma, an auxiliary (+ optional "n't"), and a
# pronoun, right before the "?" -- covers "..., don't you?", "..., isn't
# it?", "..., do you?" etc. without hand-listing every tag phrase.
_TAG_QUESTION_RE = re.compile(
    r",\s*(?:isn't|is|aren't|are|don't|do|doesn't|does|didn't|did|wasn't|was|"
    r"weren't|were|haven't|have|hasn't|has|hadn't|had|won't|will|wouldn't|"
    r"would|can't|can|couldn't|could|shouldn't|should)\s+(?:it|he|she|you|we|they)\s*\??\s*$"
)

_LEADING_PRESUPPOSITION_PHRASES = [
    "wouldn't you agree", "don't you think", "you'd agree", "isn't it true that", "surely you",
]

# Two aux-led clauses joined by "and"/"or" inside ONE "?"-terminated
# sentence, e.g. "Have you had this before or is it new?" -- the other,
# more common compound shape (two separate "?" clauses in one turn) is
# caught directly by len(clauses) > 1 in detect_question_events.
_COMPOUND_JOIN_RE = re.compile(
    r"\b(?:do|does|did|is|are|was|were|have|has|had|can|could|will|would|should)\b"
    r".{0,80}\b(?:and|or)\b\s+(?:do|does|did|is|are|was|were|have|has|had|can|could|will|would|should)\b"
)


def _question_clauses(text: str) -> List[str]:
    return [c.strip() for c in _QUESTION_CLAUSE_RE.findall(text) if c.strip()]


def _is_leading(clause: str) -> bool:
    text = clause.lower()
    if _TAG_QUESTION_RE.search(text):
        return True
    return any(p in text for p in _LEADING_PRESUPPOSITION_PHRASES)


def _classify_open_closed(clause: str) -> Optional[str]:
    text = _DISCOURSE_PREFIX_RE.sub("", clause.strip().lower())
    if any(p in text for p in _OPEN_PHRASES):
        return "open_question"
    if _TAG_QUESTION_RE.search(clause.lower()):
        # A tag question ("You don't smoke, do you?") is subject-first, not
        # aux-first, but the tag itself proves it solicits a yes/no answer --
        # closed by definition regardless of the sentence's own first word.
        return "closed_question"
    match = _WORD_RE.match(text)
    word = match.group(0) if match else ""
    if word in _OPEN_STARTERS:
        return "open_question"
    if word in _CLOSED_AUX:
        return "closed_question"
    return None


def detect_question_events(nurse_message: str) -> List[Dict[str, str]]:
    """One nurse turn -> zero or more {"event", "evidence"} entries. Mirrors
    patient_state.detect_nurse_events' return shape so speaking_evidence.py
    can fold this detector's output into the same candidate_events list."""
    clauses = _question_clauses(nurse_message)
    if not clauses:
        return []

    events: List[Dict[str, str]] = []

    if len(clauses) > 1 or any(_COMPOUND_JOIN_RE.search(c) for c in clauses):
        events.append({
            "event": "compound_question",
            "evidence": " / ".join(clauses) if len(clauses) > 1 else clauses[0],
        })

    leading_clause = next((c for c in clauses if _is_leading(c)), None)
    if leading_clause:
        events.append({"event": "leading_question", "evidence": leading_clause})

    open_closed = _classify_open_closed(clauses[0])
    if open_closed:
        events.append({"event": open_closed, "evidence": clauses[0]})

    return events
