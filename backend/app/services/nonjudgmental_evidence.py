"""Relationship Building non-judgmental approach (A3) detector (Step 21I).

    A3: "maintaining a non-judgmental approach" -> emits
        "potentially_judgmental" (explicit blame/fault/accusation wording),
        "supportive_nonjudgmental" (explicit normalisation/blame-avoidance
        framing), and "uncertain_judgment" (a bare "why didn't you" with no
        stronger evidence either way).

Same shape, same limitation as this codebase's other deterministic clinical
detectors (attentiveness_evidence.py, opening_evidence.py): this classifies
SURFACE FORM, not whether the candidate was actually judgmental. There is no
score here, only evidence (criterion_evidence.py's MISSING vs NEGATIVE rule).
The future OET Examiner interprets the wording in context -- see HARD RULE
below.

HARD RULE (this step's spec): "no judgmental phrase detected" is never
equivalent to "non-judgmental performance", "supportive phrase detected" is
never equivalent to "excellent relationship building", and "judgmental
phrase detected" is never equivalent to "automatic A3 failure". This module
only ever exposes what was said; it never labels good/bad/respectful/
effective, and there is no score/band field anywhere on its output.

JUDGMENTAL PATTERNS (Step 1/7/10): require a full blame/fault/accusation
STRUCTURE, never a bare modal verb. "should"/"must"/"need to" alone never
match -- only "you should(n't) have <verb>", "you were supposed to",
declarative non-compliance ("you didn't follow"/"you ignored"), explicit
fault-assignment ("you've only got yourself to blame", "you were
careless"), or a counterfactual rebuke ("if you had listened"). This is
deliberately why a clinical instruction ("You need to take this medication
twice daily.", "You should call us if...", "You must seek urgent help
if...") never becomes judgmental merely because of its modal verb (Step 9/24).

Declarative non-compliance wording ("you didn't follow the advice") is
worded as a STATEMENT (subject "you" immediately before the negated verb).
A "why didn't you..." QUESTION has the opposite word order (negated aux
before "you", verb only implied) and is deliberately NOT matched by the
same pattern -- it falls through to the separate, weaker uncertain check
below (Step 8/11).

SUPPORTIVE PATTERNS (Step 3): normalisation / blame-avoidance framing only
-- "it's understandable that...", "many people find this difficult", "it
makes sense that you...", "there's no need to feel embarrassed...", "thank
you for being honest...". Deliberately DISJOINT from A4's _EMPATHY_PHRASES
(patient_state.py) -- "i understand you"/"that must be"/"i can see that"
are not repeated here (Step 4 of this task's spec: A3 must not be derived
from A4's existing lexicon). A statement can independently satisfy both
this module's supportive check and A4's empathy check -- Step 18 explicitly
requires that overlap to be preserved, not deduplicated.

UNCERTAIN (Step 8/11): a bare "why didn't you"/"why haven't you" with
neither a judgmental nor a supportive pattern in the same sentence. A bare
"why" question is not automatically judgmental -- genuine information-
gathering and blame are indistinguishable from surface form alone, so this
is represented as explicit uncertainty, never forced to either extreme.

SPEAKER ATTRIBUTION (Step 13): only nurse/candidate turns are scanned --
patient statements never produce A3 evidence.

CONTEXT LINKAGE (Step 12): `related_patient_turns` links to the
IMMEDIATELY PRECEDING turn only if that turn was the patient's -- same "no
invented relationship" rule as attentiveness_evidence.py's reflective
response and cue_response_evidence.py's cue pairing. A judgmental/
supportive/uncertain sentence with no immediately preceding patient turn
still fires with an empty related_patient_turns list -- linkage is enrichment,
never a precondition for evidence to exist.

A3 vs A2/A4/D2/D4 (Step 4/5/9/19/20): this module never reads or writes
attentiveness_evidence.py's or patient_state.py's output, and nothing in
speaking_evidence.py's wiring changes how those detectors -- or the
question/clarification detectors -- behave. The same utterance may
legitimately produce A2, A3, and A4 evidence at once, and a judgmental
question may independently remain D2 open-question evidence; none of that
is deduplicated or suppressed here.

LIMITATIONS:
  - purely lexical/surface-form: contextual judgement, sarcasm, tone of
    voice, and culturally dependent phrasing outside the patterns below are
    missed, never scored as absent (MISSING vs NEGATIVE).
  - no semantic paraphrase detection: a genuinely judgmental or supportive
    statement worded entirely differently from the patterns here is missed.
  - "why didn't you" uncertainty is a fixed two-phrase check, not a general
    ambiguous-question detector -- other ambiguous phrasings are simply not
    detected, not classified as uncertain.
  - context linkage only reaches the immediately preceding turn; a judgment
    responding to something said two or more turns earlier is not linked.
  - ASR segmentation: a realtime transcript's turn/sentence boundaries can
    split or merge what was actually one spoken utterance, which can shift
    which turn a pattern is attributed to.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from pydantic import BaseModel

EVENT_POTENTIALLY_JUDGMENTAL = "potentially_judgmental"
EVENT_SUPPORTIVE_NONJUDGMENTAL = "supportive_nonjudgmental"
EVENT_UNCERTAIN_JUDGMENT = "uncertain_judgment"

PROVENANCE_DETERMINISTIC = "deterministic_rule"
EVIDENCE_LEVEL_DETERMINISTIC = "L2_deterministic"

LIMITATIONS: List[str] = [
    "Purely lexical/surface-form: contextual judgement, sarcasm, tone of voice, "
    "and culturally dependent phrasing outside the known patterns are missed, "
    "never scored as absent.",
    "No semantic paraphrase detection -- a genuinely judgmental or supportive "
    "statement worded entirely differently from the patterns here is missed.",
    "\"why didn't you\" uncertainty is a fixed two-phrase check, not a general "
    "ambiguous-question detector -- other ambiguous phrasings are simply not "
    "detected, not classified as uncertain.",
    "Context linkage only reaches the immediately preceding turn; a judgment "
    "responding to something said two or more turns earlier is not linked.",
    "ASR segmentation: a realtime transcript's turn/sentence boundaries can "
    "split or merge what was actually one spoken utterance, which can shift "
    "which turn a pattern is attributed to.",
]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


# ── Potentially judgmental (Step 1/7/10) ────────────────────────────────
# Full blame/fault/accusation structures only -- never a bare modal verb
# (Step 3/9/24: "should"/"must"/"need to" alone must never match).
_JUDGMENTAL_RE = re.compile(
    r"\byou should(?:n'?t| not)? have\b"
    r"|\byou were supposed to\b"
    r"|\byou (?:didn'?t|did not|never|failed to) (?:follow|listen to|take|comply with|do what)\b"
    r"|\byou ignored\b"
    r"|\byou'?(?:ve been|were) careless\b"
    r"|\byou'?ve? only (?:got )?yourself to blame\b"
    r"|\byou'?re not taking (?:this|it) seriously\b"
    r"|\bif you had (?:listened|followed|taken)\b",
    re.IGNORECASE,
)

# ── Supportive / non-judgmental (Step 3) ────────────────────────────────
# Normalisation/blame-avoidance framing only -- deliberately disjoint from
# A4's _EMPATHY_PHRASES (patient_state.py), see module docstring.
_SUPPORTIVE_RE = re.compile(
    r"\bit'?s (?:completely )?understandable that\b"
    r"|\bthat'?s understandable\b"
    r"|\b(?:many|a lot of) people find (?:this|that) difficult\b"
    r"|\bit makes sense that you\b"
    r"|\bthere'?s no need to feel (?:embarrassed|ashamed|guilty)\b"
    r"|\bthank you for being honest\b",
    re.IGNORECASE,
)

# ── Uncertain (Step 8/11) ────────────────────────────────────────────────
# Bare "why didn't/haven't you" -- word order (negated aux BEFORE "you")
# deliberately distinguishes a question from _JUDGMENTAL_RE's declarative
# "you didn't <verb>" statements, which have the opposite order.
_WHY_DIDNT_RE = re.compile(r"\bwhy (?:didn'?t|did not|haven'?t|have not) you\b", re.IGNORECASE)


def _classify(sentence: str) -> Optional[str]:
    if _JUDGMENTAL_RE.search(sentence):
        return EVENT_POTENTIALLY_JUDGMENTAL
    if _SUPPORTIVE_RE.search(sentence):
        return EVENT_SUPPORTIVE_NONJUDGMENTAL
    if _WHY_DIDNT_RE.search(sentence):
        return EVENT_UNCERTAIN_JUDGMENT
    return None


class NonJudgmentalEvent(BaseModel):
    turn_index: int
    evidence_text: str
    event_type: str  # EVENT_POTENTIALLY_JUDGMENTAL | EVENT_SUPPORTIVE_NONJUDGMENTAL | EVENT_UNCERTAIN_JUDGMENT
    related_patient_turns: List[int] = []
    provenance: str = PROVENANCE_DETERMINISTIC
    evidence_level: str = EVIDENCE_LEVEL_DETERMINISTIC


class NonJudgmentalEvidence(BaseModel):
    potentially_judgmental_events: List[NonJudgmentalEvent] = []
    supportive_nonjudgmental_events: List[NonJudgmentalEvent] = []
    uncertain_events: List[NonJudgmentalEvent] = []
    limitations: List[str] = LIMITATIONS


def detect_nonjudgmental_events(history: List[Dict[str, str]]) -> List[NonJudgmentalEvent]:
    """Whole-transcript, flat list -- the shape speaking_evidence.py calls
    directly (same per-detector call shape as detect_acknowledgement_events/
    detect_reflective_response_events). Speaker attribution (Step 13): only
    nurse turns are scanned. Context linkage (Step 12): related_patient_turns
    is [idx-1] only when that turn is the patient's, else empty -- never
    invented."""
    history = history or []
    events: List[NonJudgmentalEvent] = []
    for idx, turn in enumerate(history):
        if turn.get("role") != "nurse":
            continue
        related = [idx - 1] if idx > 0 and history[idx - 1].get("role") == "patient" else []
        for sentence in _sentences(turn.get("content", "")):
            event_type = _classify(sentence)
            if event_type is None:
                continue
            events.append(NonJudgmentalEvent(
                turn_index=idx, evidence_text=sentence, event_type=event_type,
                related_patient_turns=related,
            ))
    return events


def detect_nonjudgmental_evidence(history: List[Dict[str, str]]) -> NonJudgmentalEvidence:
    """Step 14 focused model -- bundles detect_nonjudgmental_events' output
    by event type, for direct testing/golden-case inspection. Read-only
    second view, same convention as attentiveness_evidence.detect_
    attentiveness_evidence -- speaking_evidence.py calls
    detect_nonjudgmental_events directly, not this bundling function."""
    events = detect_nonjudgmental_events(history)
    return NonJudgmentalEvidence(
        potentially_judgmental_events=[e for e in events if e.event_type == EVENT_POTENTIALLY_JUDGMENTAL],
        supportive_nonjudgmental_events=[e for e in events if e.event_type == EVENT_SUPPORTIVE_NONJUDGMENTAL],
        uncertain_events=[e for e in events if e.event_type == EVENT_UNCERTAIN_JUDGMENT],
    )


if __name__ == "__main__":
    # Explicit blame ("should have").
    blame = detect_nonjudgmental_events([
        {"role": "patient", "content": "I stopped taking the medication because it was painful."},
        {"role": "nurse", "content": "You should have continued it."},
    ])
    assert len(blame) == 1
    assert blame[0].event_type == EVENT_POTENTIALLY_JUDGMENTAL
    assert blame[0].related_patient_turns == [0]

    # Explicit non-compliance judgement.
    noncompliance = detect_nonjudgmental_events([
        {"role": "nurse", "content": "You didn't follow the advice."},
    ])
    assert len(noncompliance) == 1 and noncompliance[0].event_type == EVENT_POTENTIALLY_JUDGMENTAL

    # Explicit criticism.
    criticism = detect_nonjudgmental_events([
        {"role": "nurse", "content": "You've been careless with your medication."},
    ])
    assert len(criticism) == 1 and criticism[0].event_type == EVENT_POTENTIALLY_JUDGMENTAL

    # Clinical instruction false positives (Step 9/24) -- modal verb alone
    # must NEVER become judgmental.
    assert detect_nonjudgmental_events([
        {"role": "nurse", "content": "You need to take this medication twice daily."},
    ]) == []
    assert detect_nonjudgmental_events([
        {"role": "nurse", "content": "You should call us if the pain gets worse."},
    ]) == []
    assert detect_nonjudgmental_events([
        {"role": "nurse", "content": "You must go to the emergency department if you become severely short of breath."},
    ]) == []

    # "Why didn't you..." stays uncertain, not judgmental (Step 8/11).
    why = detect_nonjudgmental_events([
        {"role": "nurse", "content": "Why didn't you take the medication?"},
    ])
    assert len(why) == 1 and why[0].event_type == EVENT_UNCERTAIN_JUDGMENT

    # Supportive normalisation.
    supportive = detect_nonjudgmental_events([
        {"role": "nurse", "content": "It's understandable that you struggled with this."},
    ])
    assert len(supportive) == 1 and supportive[0].event_type == EVENT_SUPPORTIVE_NONJUDGMENTAL

    # Speaker attribution -- patient's own judgment-shaped text never fires.
    assert detect_nonjudgmental_events([
        {"role": "patient", "content": "You should have told me sooner."},
    ]) == []

    # Determinism.
    assert detect_nonjudgmental_events(blame_history := [
        {"role": "nurse", "content": "You should have continued it."},
    ]) == detect_nonjudgmental_events(blame_history)

    # Bundled view.
    bundled = detect_nonjudgmental_evidence([
        {"role": "nurse", "content": "You should have continued it. It's understandable that you struggled with this."},
    ])
    assert len(bundled.potentially_judgmental_events) == 1
    assert len(bundled.supportive_nonjudgmental_events) == 1
    assert bundled.limitations

    print("nonjudgmental_evidence self-check OK")
