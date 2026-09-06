"""Session-scoped Patient Simulation State (Step 1 foundation).

Derives a snapshot of what the AI patient has already revealed, what it
still must raise, and whether any emotional trigger has fired -- purely
from the interlocutor_card and the turns exchanged so far.

Deliberately stateless: both existing patient pipelines already hold the
full turn history somewhere -- the legacy REST chat path round-trips it
from the client on every request, and the realtime voice path accumulates
transcript_turns in-memory for the life of one WebSocket connection.
Recomputing state on demand from that transcript means no new database
table, cache, or session store is needed, the state can never drift from
what was actually said, and it automatically resets when a new session
starts (there is nothing to reset -- there's no history yet).

This is intentionally the smallest useful state, matching what the
interlocutor_card schema in production actually supports today. It does
not model scenario "stages" (not present in the schema), compliance
verification, or emotion transitions beyond a simple baseline/heightened
flag -- those are future steps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

from pydantic import BaseModel

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "with", "about", "that", "this", "your", "you", "i", "my",
    "have", "has", "had", "will", "would", "do", "does", "did", "not", "if",
    "it", "be", "as", "at", "by", "from", "but", "me", "am", "can", "could",
}

_WORD_RE = re.compile(r"[a-z']+")


def _keywords(text: str) -> set:
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) >= 4 and w not in _STOPWORDS}


def _normalize_token(word: str) -> str:
    """Collapses a possessive/simple-plural suffix so a hidden-info keyword
    ("uncle's") still matches the bare form a real disclosure actually uses
    ("uncle") -- the concrete gap a real QA session exposed: the patient
    said "my uncle" and the candidate filter never fired because "uncle's"
    != "uncle" as literal strings. Used only by _hidden_info_candidate
    below, not by _mentioned_in (concerns/triggers keep their existing,
    unmodified behavior)."""
    if word.endswith("'s"):
        return word[:-2]
    if word.endswith("s") and len(word) > 4:
        return word[:-1]
    return word


def _hidden_info_candidate(item: str, turns_text: str) -> bool:
    """Candidate pre-filter for hidden-information disclosure specifically
    (feeds semantic verification -- see semantic_evidence.hidden_info_hints).
    Same "any one significant keyword" breadth as _mentioned_in below -- a
    stricter generic/anchor-word split was tried and rejected: it broke the
    existing, deliberate "medication" -> "medication non-compliance" reveal
    (a real keyword match with no more-specific word to back it up), and no
    lexical rule can keep that firing while blocking a same-shape overlap
    like "injections"/"painful" on a childhood-trauma item -- see the Task 1
    proposal. The only difference from _mentioned_in is normalizing
    possessive/plural suffixes so a disclosure using the bare form of an
    item's word isn't missed on a technicality. The remaining gap (a full
    synonym swap with zero shared word, e.g. "injections" -> "syringes") is
    a real, documented limitation of lexical pre-filtering -- catching it
    needs actual paraphrase understanding, which is what the semantic layer
    (and eventually a real Sonnet call) is for, not this pre-filter.
    """
    kws = {_normalize_token(k) for k in _keywords(item)}
    if not kws:
        return False
    turn_words = {_normalize_token(w) for w in _WORD_RE.findall(turns_text.lower())}
    return any(k in turn_words for k in kws)


def _mentioned_in(item: str, turns_text: str) -> bool:
    # ponytail: naive keyword-overlap heuristic (any one of an item's
    # significant words appearing anywhere in the turns counts as a
    # mention), not semantic matching. Scenario items are short clinical
    # labels ("previous medication non-compliance") that real dialogue
    # rarely restates verbatim, so a majority-overlap bar was too strict to
    # ever fire. Upgrade path: LLM- or embedding-based reveal detection if
    # this proves too eager on real transcripts.
    kws = _keywords(item)
    if not kws:
        return False
    turn_words = set(_WORD_RE.findall(turns_text.lower()))
    return any(k in turn_words for k in kws)


@dataclass
class SemanticHints:
    """Step 7: validated output from app.services.semantic_evidence, fed into
    derive_patient_state as an optional enrichment layer -- never built here,
    so this module stays a leaf with no dependency on the semantic layer (it
    would otherwise create a patient_state <-> semantic_evidence import
    cycle, the same shape of problem already solved for jargon detection --
    see the module docstring on JARGON_EXPLANATION_WORDS above).

    All fields default empty, and passing semantic_hints=None to
    derive_patient_state is exactly equivalent to omitting it -- every
    existing caller/test that doesn't pass this param keeps its original,
    unmodified behavior.
    """
    confirmed_hidden_reveals: FrozenSet[str] = field(default_factory=frozenset)
    rejected_hidden_reveals: FrozenSet[str] = field(default_factory=frozenset)
    extra_nurse_events: Dict[int, List[Dict[str, str]]] = field(default_factory=dict)
    resolved_concerns: FrozenSet[str] = field(default_factory=frozenset)
    # Task 6 (offline evidence-observability pass): per-item AGGREGATE outcome
    # of semantic verification, keyed by hidden-info item text. One of
    # semantic_evidence's STATUS_* constants -- distinguishes a valid
    # semantic "not revealed" from a provider failure, parse failure, or
    # truncated (token-limit) response, all of which used to collapse into
    # the same "rejected" bucket with no way to tell them apart. An item
    # with no entry here was never even a candidate (see
    # speaking_evidence.HiddenInfoOutcome, which reports that case as
    # "not_called").
    verification_status: Dict[str, str] = field(default_factory=dict)
    # Step 12B: per-CANDIDATE-TURN verification outcome, item -> {turn_index:
    # status}. Replaces single-turn attribution (_first_matching_patient_
    # statement picked only the earliest keyword match, so a false-positive
    # early candidate could permanently block re-checking a genuine later
    # disclosure -- the exact real-QA gap this step fixes). Every candidate
    # turn semantic_evidence.hidden_info_hints has processed for an item
    # shows up here, confirmed or not -- the full audit trail (Rule 5).
    candidate_turn_status: Dict[str, Dict[int, str]] = field(default_factory=dict)
    # Step 12B: item -> turn_index of the EARLIEST turn that verified
    # revealed=True for it. This, not the first keyword match, is the turn a
    # reviewer should be pointed at for a genuinely revealed item (Rule 6/
    # Step 6's "earliest verified reveal" attribution rule).
    confirmed_reveal_turn: Dict[str, int] = field(default_factory=dict)


class PatientState(BaseModel):
    baseline_emotion: str
    emotional_intensity: str  # "baseline" | "heightened"
    fired_emotional_triggers: List[str]
    hidden_information: List[str]
    revealed_information: List[str]
    concerns_raised: List[str]
    concerns_unresolved: List[str]
    turns_completed: int
    # Step 4 additions -- see _derive_behavioural_state. These are new,
    # independent signals; none of the fields above changed meaning or
    # computation.
    trust: str  # "low" | "moderate" | "high"
    current_emotion: str  # small vocab; can diverge from baseline_emotion as the conversation develops, unlike emotional_intensity which stays tied to fired triggers
    concern_status: Dict[str, str]  # concern text -> "not_raised"|"raised"|"acknowledged"|"explored"|"addressed"|"resolved"
    current_concern: Optional[str]  # oldest concern not yet resolved, or None


def derive_patient_state(
    interlocutor_card: Dict[str, Any],
    history: List[Dict[str, str]],
    semantic_hints: Optional[SemanticHints] = None,
) -> PatientState:
    """Pure function: same card + same history + same semantic_hints always
    yields the same state. `history` is a list of {"role": "nurse"|"patient",
    "content": str}. `semantic_hints` is optional -- omitting it (or passing
    an empty SemanticHints, e.g. after a provider failure) means NO hidden
    item can ever show as revealed here (Step 12B Rule 1/4): candidate
    detection alone is never enough, see the `revealed` computation below.

    Field availability (confirmed schema drift between scenario-authoring
    paths): older scenarios saved via the image/PDF extraction path never
    populate emotional_triggers or information_to_withhold, so those
    default to empty lists rather than crashing or fabricating content.
    """
    card = interlocutor_card or {}
    hints = semantic_hints or SemanticHints()
    emotional_triggers = card.get("emotional_triggers") or []
    concerns = card.get("questions_to_ask") or card.get("concerns") or []
    hidden = card.get("information_to_withhold") or []
    baseline_emotion = card.get("mood") or "Cooperative"

    patient_text = " ".join(t.get("content", "") for t in history if t.get("role") == "patient")
    all_text = " ".join(t.get("content", "") for t in history)

    # Step 12B (authoritative reveal rule -- Rule 1): a lexical keyword match
    # is only ever a CANDIDATE, never proof of disclosure on its own. The
    # ONLY thing that promotes an item to revealed is a semantic
    # verification that actually confirmed it (hints.confirmed_hidden_
    # reveals) -- populated exclusively by semantic_evidence.hidden_info_
    # hints, which verifies every relevant candidate turn, not just the
    # first keyword match. No hints / no confirmation / a verification
    # failure => item stays in still_hidden, the conservative default
    # (Rule 4/Step 7). This was a real QA-found bug: the previous formula
    # also promoted an item the moment it became a candidate, unless a
    # semantic check had already rejected it -- so a brand-new candidate
    # that had never been checked at all still showed as revealed.
    revealed = [item for item in hidden if item in hints.confirmed_hidden_reveals]
    still_hidden = [item for item in hidden if item not in revealed]

    raised = [item for item in concerns if _mentioned_in(item, patient_text)]
    unresolved = [item for item in concerns if item not in raised]

    fired = [item for item in emotional_triggers if _mentioned_in(item, all_text)]

    trust, current_emotion, concern_status, current_concern = _derive_behavioural_state(card, history, concerns, hints)

    return PatientState(
        baseline_emotion=baseline_emotion,
        emotional_intensity="heightened" if fired else "baseline",
        fired_emotional_triggers=fired,
        hidden_information=still_hidden,
        revealed_information=revealed,
        concerns_raised=raised,
        concerns_unresolved=unresolved,
        turns_completed=len(history) // 2,
        trust=trust,
        current_emotion=current_emotion,
        concern_status=concern_status,
        current_concern=current_concern,
    )


def render_patient_state_prompt(state: PatientState) -> str:
    """Shared prompt block consumed by both the legacy and realtime patient
    pipelines, so they stay behaviourally consistent."""

    def _list(items: List[str], empty: str) -> str:
        return "\n".join(f"- {i}" for i in items) if items else f"- {empty}"

    if state.current_concern:
        concern_line = f"{state.current_concern} (status: {state.concern_status.get(state.current_concern, 'raised')})"
    else:
        concern_line = "none active right now"

    return f"""CONVERSATION STATE (internal -- do not reveal this section to the nurse):
Already revealed -- do not present these as new information:
{_list(state.revealed_information, "nothing yet")}

Still hidden -- reveal ONLY if the nurse asks directly:
{_list(state.hidden_information, "nothing to hide")}

Concerns you have already raised -- do not repeat them as if new:
{_list(state.concerns_raised, "none yet")}

Concerns you still need to raise naturally before the conversation ends:
{_list(state.concerns_unresolved, "none outstanding")}

Current emotional state: {state.baseline_emotion} (intensity: {state.emotional_intensity})
Topics that should already feel emotionally sensitive to you:
{_list(state.fired_emotional_triggers, "none triggered yet")}

RELATIONSHIP & CURRENT REACTION (internal -- do not reveal this section to the nurse):
Trust in the nurse so far: {state.trust}
Current emotional reaction (this can shift during the conversation, unlike your baseline mood): {state.current_emotion}
Concern you are currently most focused on: {concern_line}

IMPORTANT: Being acknowledged, or asked a follow-up question, is NOT the same as being reassured. If that concern's status above is only "acknowledged" or "explored" (not yet "addressed" or "resolved"), you should still feel it hasn't really been dealt with, and may bring it up again naturally rather than dropping it.

Stay consistent with this state. Do not contradict it or re-reveal what's already marked revealed."""


# ── JARGON DETECTION ─────────────────────────────────────────────────────
# Moved here (from app.services.ai_scoring) so this module -- the shared
# foundation both the legacy and realtime patient pipelines already depend
# on -- can reuse it for behavioural event detection below without ai_scoring
# importing patient_state importing ai_scoring back (circular). ai_scoring
# re-exports both names unchanged, so no other call site needed to change.

MEDICAL_JARGON = [
    "hypertension", "hypotension", "tachycardia", "bradycardia",
    "myocardial", "infarction", "arrhythmia", "angina",
    "dyspnea", "dyspnoea", "oedema", "edema",
    "haemorrhage", "hemorrhage", "thrombosis", "embolism",
    "contraindicated", "contraindication", "analgesic", "analgesia",
    "antipyretic", "anticoagulant", "subcutaneous", "intravenous",
    "intramuscular", "nil by mouth", "cannula", "nasogastric",
    "catheter", "cholecystectomy", "appendectomy", "biopsy",
    "malignant", "metastasis", "haemoglobin", "creatinine",
    "troponin", "electrolyte", "sepsis", "bacteremia",
    "cellulitis", "hyperglycemia", "hypoglycemia", "neuropathy",
    "paraplegia", "bronchitis", "exacerbation", "comorbidity",
    "prophylaxis", "etiology", "prognosis",
]


# Hoisted to module level (was function-local) so the Speaking Evidence
# layer (app.services.speaking_evidence) can reuse the same "was this term
# actually explained" check for its jargon clarified_afterward field,
# instead of re-deriving its own word list.
JARGON_EXPLANATION_WORDS = [
    "means", "meaning", "that is", "in other words",
    "which is", "or in simple", "basically",
    "what we call", "also called", "known as", "in plain",
]


def detect_jargon(nurse_message: str) -> str | None:
    message_lower = nurse_message.lower()
    for term in MEDICAL_JARGON:
        if term in message_lower:
            term_index = message_lower.find(term)
            surrounding = message_lower[
                max(0, term_index - 20):
                min(len(message_lower), term_index + 100)
            ]
            if any(w in surrounding for w in JARGON_EXPLANATION_WORDS):
                continue
            return term
    return None


# ── BEHAVIOURAL EVENT DETECTION (Step 4) ─────────────────────────────────
# Deterministic, keyword-based. This is a foundation, not a communication-
# understanding engine: paraphrases the lists below don't cover will be
# missed, and a coincidental match (e.g. "I understand the surgery is at
# 9am" isn't empathy) can produce a false positive. Documented limitation,
# not fixed here -- a stronger evidence layer is future work, not Step 4.
# Do NOT add an LLM call here: event detection stays free so behavioural
# state can be recomputed on every turn with no extra cost/latency/risk of
# an LLM inventing an event that never happened.

_EMPATHY_PHRASES = [
    "i understand you", "i can understand", "that must be", "i hear you",
    "i know this is", "i realise this", "i realize this", "sorry to hear",
    "that sounds", "i can see that", "it's understandable", "it is understandable",
]

_CONCERN_EXPLORATION_PHRASES = [
    "what concerns you most", "what worries you", "what's worrying you",
    "what is worrying you", "tell me more about what", "can you tell me more about",
    "what's on your mind about", "what concerns you about",
]

_UNDERSTANDING_CHECK_PHRASES = [
    "does that make sense", "did that make sense", "do you understand what i",
    "is that clear", "does that answer your question", "how does that sound",
    "do you have any questions about what i",
]

_DISMISSIVE_PHRASES = [
    "don't worry", "do not worry", "you'll be fine", "you will be fine",
    "it's nothing", "it is nothing", "there's nothing to worry", "calm down",
    "it's not a big deal", "no need to worry",
]


def detect_nurse_events(nurse_message: str) -> List[Dict[str, str]]:
    """One nurse turn -> zero or more behavioural events, each
    {"event": name, "evidence": matched phrase/term}. Independent checks --
    a single turn can carry more than one event (an empathetic follow-up
    question fires both empathy_acknowledgement and concern_exploration).
    Reuses detect_jargon() rather than a second jargon detector."""
    text = nurse_message.lower()
    events: List[Dict[str, str]] = []

    jargon_term = detect_jargon(nurse_message)
    if jargon_term:
        events.append({"event": "jargon_used", "evidence": jargon_term})

    for phrase in _EMPATHY_PHRASES:
        if phrase in text:
            events.append({"event": "empathy_acknowledgement", "evidence": phrase})
            break
    for phrase in _CONCERN_EXPLORATION_PHRASES:
        if phrase in text:
            events.append({"event": "concern_exploration", "evidence": phrase})
            break
    for phrase in _UNDERSTANDING_CHECK_PHRASES:
        if phrase in text:
            events.append({"event": "understanding_checked", "evidence": phrase})
            break
    for phrase in _DISMISSIVE_PHRASES:
        if phrase in text:
            events.append({"event": "dismissive_response", "evidence": phrase})
            break
    return events


# ── EMOTIONAL / RELATIONSHIP STATE TRANSITIONS (Step 4) ──────────────────

_CONCERN_RANK = {
    "not_raised": 0, "raised": 1, "acknowledged": 2,
    "explored": 3, "addressed": 4, "resolved": 5,
}
# Public alias -- speaking_evidence.py (Task 3) needs this to detect a
# concern's status rank dropping across recomputed prefixes (a "reopening",
# not a bug) without reaching into a name another module shouldn't import.
CONCERN_RANK = _CONCERN_RANK

_NEGATIVE_EMOTIONS = {"anxious", "frustrated", "confused", "angry", "embarrassed"}


def _emotion_bucket(mood: str) -> str:
    """Maps the card's free-text `mood` onto the small emotion vocabulary
    current_emotion moves within. Deliberately coarse -- see module-level
    limitation note on scenario awareness."""
    m = mood.lower()
    if any(w in m for w in ("anxious", "nervous", "worried", "scared", "frightened")):
        return "anxious"
    if any(w in m for w in ("angry", "irritated", "furious")):
        return "angry"
    if "frustrat" in m:
        return "frustrated"
    if "confus" in m:
        return "confused"
    if any(w in m for w in ("embarrass", "ashamed")):
        return "embarrassed"
    if any(w in m for w in ("calm", "cooperative", "relax")):
        return "calm"
    return "neutral"


def _jargon_weight(card: Dict[str, Any], baseline_bucket: str) -> int:
    """Scenario-aware magnitude for a jargon_used event -- the one place
    Step 4 has enough existing scenario signal (mood + persona/background
    text) to vary the reaction without inventing a new schema field. A
    dedicated per-scenario "reactivity" field would be a cleaner home for
    this and is documented as future schema work, not built here."""
    persona_text = " ".join([
        str(card.get("background", "")), str(card.get("instructions_for_ai", "")),
        str(card.get("mood", "")),
    ]).lower()
    if any(w in persona_text for w in ("nurse", "doctor", "medically trained", "healthcare worker", "medical background")):
        return 0
    if baseline_bucket == "confused":
        return -2
    return -1


def _derive_behavioural_state(
    card: Dict[str, Any], history: List[Dict[str, str]], concerns: List[str],
    hints: Optional[SemanticHints] = None,
) -> tuple[str, str, Dict[str, str], Optional[str]]:
    """Single deterministic pass over the full history -> (trust,
    current_emotion, concern_status, current_concern). Pure function --
    same card+history+hints always yields the same result, matching
    derive_patient_state's existing contract.

    A concern's status only ever advances (_CONCERN_RANK order), never
    regresses -- and "resolved" is never reached by an empathy phrase or
    understanding check alone. It requires an actual addressing event AND
    the patient not raising that same concern again anywhere later in the
    history (checked in the second pass below). This is the fix for
    design correction #1: acknowledged/explored is not resolved.

    Step 7: `hints.extra_nurse_events` merges in semantic-detected
    concern_exploration/concern_addressing events the phrase-list-based
    detect_nurse_events() missed (Finding 2), keyed by turn index, treated
    identically to a deterministic match. `hints.resolved_concerns` is a
    second, independent path to "resolved" (patient-side semantic
    resolution signal) alongside the existing addressed-and-never-reraised
    rule -- multi-signal per Step 6, not a replacement.
    """
    hints = hints or SemanticHints()
    baseline_bucket = _emotion_bucket(str(card.get("mood") or ""))
    jargon_weight = _jargon_weight(card, baseline_bucket)

    concern_status: Dict[str, str] = {c: "not_raised" for c in concerns}
    addressed_at_idx: Dict[str, int] = {}
    raise_order: List[str] = []
    score = 0

    def _advance(c: str, new_status: str, idx: int) -> None:
        if _CONCERN_RANK[new_status] > _CONCERN_RANK[concern_status[c]]:
            concern_status[c] = new_status
            if new_status == "addressed":
                addressed_at_idx[c] = idx

    for idx, turn in enumerate(history):
        role = turn.get("role")
        content = turn.get("content", "")
        if role == "patient":
            for c in concerns:
                if concern_status[c] == "not_raised" and _mentioned_in(c, content):
                    concern_status[c] = "raised"
                    raise_order.append(c)
        elif role == "nurse":
            # Oldest concern still below "addressed" is the implicit target
            # of this turn's events -- simplest FIFO rule that avoids a
            # branching per-concern classifier (Step 11).
            target = next(
                (c for c in raise_order if _CONCERN_RANK[concern_status[c]] < _CONCERN_RANK["addressed"]),
                None,
            )
            turn_events = detect_nurse_events(content) + hints.extra_nurse_events.get(idx, [])
            for ev in turn_events:
                name = ev["event"]
                # A semantic event may name its own target concern directly
                # (Step 8 -- avoids the FIFO guess when several concerns are
                # in play, e.g. Test 7); falls back to the FIFO target for
                # deterministic events, which never carry this field. Only
                # trusted if it's actually one of this scenario's concerns --
                # never lets model output name a concern that doesn't exist.
                ev_target = ev.get("target_concern")
                event_target = ev_target if ev_target in concern_status else target
                if name == "empathy_acknowledgement":
                    score += 1
                    if event_target:
                        _advance(event_target, "acknowledged", idx)
                elif name == "concern_exploration":
                    score += 1
                    if event_target:
                        _advance(event_target, "explored", idx)
                elif name == "concern_addressing":
                    # Semantic-only event (Finding 2): direct evidence of
                    # addressing a concern, without requiring the
                    # explored -> understanding_checked deterministic path.
                    score += 1
                    if event_target:
                        _advance(event_target, "addressed", idx)
                elif name == "understanding_checked":
                    score += 1
                    if event_target and concern_status[event_target] == "explored":
                        _advance(event_target, "addressed", idx)
                elif name == "dismissive_response":
                    score -= 1
                elif name == "jargon_used":
                    score += jargon_weight

    # An addressed concern the patient never brings up again graduates to
    # resolved. Still addressed (not resolved) if it re-surfaces later --
    # re-raising it is itself evidence it wasn't actually settled.
    for c, status in concern_status.items():
        if status == "addressed":
            idx = addressed_at_idx[c]
            reraised = any(
                t.get("role") == "patient" and _mentioned_in(c, t.get("content", ""))
                for t in history[idx + 1:]
            )
            if not reraised:
                concern_status[c] = "resolved"

    # Step 7 (Step 6 multi-signal requirement): a semantic-confirmed patient
    # resolution statement ("I think I could do that, it's not as scary as
    # I thought") is a second, earlier path to "resolved" -- doesn't need to
    # wait for "never re-raised again" over the rest of the (possibly still
    # in-progress) conversation. Still gated on "addressed" already being
    # reached -- semantic evidence augments the state machine, it doesn't
    # let a concern skip straight from "raised" to "resolved" (Step 6).
    for c in hints.resolved_concerns:
        if c in concern_status and _CONCERN_RANK[concern_status[c]] >= _CONCERN_RANK["addressed"]:
            concern_status[c] = "resolved"

    trust = "low" if score <= -1 else "high" if score >= 2 else "moderate"
    if score <= -1 and baseline_bucket in ("calm", "neutral"):
        current_emotion = "anxious"
    elif score >= 1 and baseline_bucket in _NEGATIVE_EMOTIONS:
        current_emotion = "calm"
    else:
        current_emotion = baseline_bucket

    current_concern = next(
        (c for c in raise_order if concern_status[c] != "resolved"),
        None,
    )
    return trust, current_emotion, concern_status, current_concern
