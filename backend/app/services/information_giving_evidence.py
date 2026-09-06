"""Information Giving (E1/E2/E3/E5) detector (Step 21E).

Fifth Information Giving/Gathering-family detector, after question_behaviour.py's
D2/D3 (21A), structure_evidence.py's C2/C3 (21B), sequencing_evidence.py's C1
(21C), and information_gathering_evidence.py's D4/D5 (21D). Same shape, same
limitation: this classifies SURFACE FORM (explicit phrasing), not whether the
information-giving was actually effective. A rare phrasing outside the
patterns below is missed, not mis-scored -- there is no score here, only
evidence (criterion_evidence.py's MISSING vs NEGATIVE rule).

    E1: "establishing initially what the patient already knows" -> emits
        "prior_knowledge_check" / "prior_knowledge_uncertain" (bare closed
        form "do you know anything about X" -- plausibly E1, plausibly small
        talk, Step 3/17: never forced)
    E2: "pausing periodically when giving information, using the response to
        guide next steps" -> emits "reaction_response" (confirmed: nurse
        info turn -> patient reaction -> nurse adapts) / "reaction_response_
        uncertain" (a patient turn precedes, but the info-giving context
        before it is missing/ambiguous)
    E3: "encouraging the patient to contribute reactions/feelings" -> emits
        "contribution_invitation" (an info-giving turn precedes) /
        "contribution_invitation_uncertain" (no clear info-giving context --
        the B1 grey zone, Step 11: never auto-promoted)
    E5: "discovering what further information the patient needs" -> emits
        "further_information_check" / "further_information_uncertain" (a
        bare, unqualified "any questions?" -- genuinely ambiguous with E4)

E4 (patient_state.py's understanding_checked) is untouched and lives
elsewhere -- see the E5-vs-E4 lexicon note below.

INFORMATION-GIVING CONTEXT (Step 14/I of the design): a nurse turn counts as
"information-giving" if it is declarative (contains no "?") -- the same
conservative surface-form proxy this whole detector family already uses
(question_behaviour.py classifies the opposite: turns that ARE questions).
No semantic "is this actually clinical information" check is attempted.

E1 vs D2 (Step 10/E): "What do you already know about insulin?" legitimately
produces both E1 and D2 (open_question) -- independent detectors, no
deduplication (same precedent as D4/D2 overlap in information_gathering_
evidence.py).

E2/E3 vs B1/empathy (Step 3/6/11/F/G): E2's phrase list overlaps with
patient_state._EMPATHY_PHRASES in spirit but is gated hard on the
info-turn -> patient-reaction -> nurse-response STRUCTURE, so a bare, isolated
empathy statement (no preceding patient turn at all) never becomes E2
evidence. E3's phrase list overlaps with patient_state._CONCERN_EXPLORATION_
PHRASES (B1) in spirit ("what do you think" vs "what worries you") but uses a
disjoint literal vocabulary, so no lexical double-count; genuine E2+E3 or
E3+B1 double-evidence on the SAME sentence is legitimate and never deduped
(Step 5/11).

E5 vs E4 (Step 9/H): E5's lexicon requires "other"/"else"/"again"/"concerns
about" -- deliberately excludes every phrase in patient_state.
_UNDERSTANDING_CHECK_PHRASES ("does that make sense", "is that clear", "how
does that sound", "do you have any questions about what i", ...) so the two
never share a literal match. A bare "Do you have any questions?" (no
qualifier either way) is reported as further_information_uncertain rather
than guessed.

LIMITATIONS (Step 24/K):
  - purely lexical: real E1/E2/E3/E5 behaviour phrased outside the patterns
    below is missed, never scored as absent.
  - "information-giving context" is a no-"?" proxy, not semantic
    understanding of clinical content -- a declarative turn that is small
    talk, or a question that is actually informational ("Do you know insulin
    can cause bruising?"), can mis-classify the context check.
  - E2's "patient reaction" is structural position only (the turn right
    before the response), never a check that the patient's words actually
    expressed worry/reaction.
  - no ASR punctuation robustness: a dropped "?" can shift a turn between
    "information-giving" and "question" for the context check.
  - E1/E3 uncertain tiers are a genuine grey zone this detector resolves
    conservatively (uncertain, never forced to confident or dropped).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from pydantic import BaseModel

EVENT_PRIOR_KNOWLEDGE_CHECK = "prior_knowledge_check"
EVENT_PRIOR_KNOWLEDGE_UNCERTAIN = "prior_knowledge_uncertain"
EVENT_REACTION_RESPONSE = "reaction_response"
EVENT_REACTION_RESPONSE_UNCERTAIN = "reaction_response_uncertain"
EVENT_CONTRIBUTION_INVITATION = "contribution_invitation"
EVENT_CONTRIBUTION_INVITATION_UNCERTAIN = "contribution_invitation_uncertain"
EVENT_FURTHER_INFORMATION_CHECK = "further_information_check"
EVENT_FURTHER_INFORMATION_UNCERTAIN = "further_information_uncertain"

PROVENANCE_DETERMINISTIC = "deterministic_rule"
EVIDENCE_LEVEL_DETERMINISTIC = "L2_deterministic"

LIMITATIONS: List[str] = [
    "Detects surface-form E1/E2/E3/E5 phrasing only -- real information-giving "
    "behaviour worded outside the known patterns is missed, not scored as absent.",
    "'Information-giving context' is a no-question-mark proxy on the nearby "
    "nurse turn, not semantic understanding of clinical content.",
    "E2's 'patient reaction' is structural position (the turn immediately "
    "before the response), never verified to actually express a reaction.",
    "No ASR punctuation robustness -- a dropped '?' can shift a turn between "
    "the information-giving and question classification used for context.",
    "E1/E3 uncertain tiers (closed-form knowledge checks; invitations with no "
    "clear preceding information) are a genuine grey zone resolved "
    "conservatively, never forced to confident or dropped.",
]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


def _is_information_giving_turn(turn: Optional[Dict[str, str]]) -> bool:
    """Step I: a nurse turn with no '?' at all is treated as declarative/
    information-giving. Conservative proxy, not semantic content analysis --
    see module LIMITATIONS."""
    if not turn or turn.get("role") != "nurse":
        return False
    content = turn.get("content", "")
    return bool(content.strip()) and "?" not in content


# ── E1 prior knowledge ──────────────────────────────────────────────────────
_STRONG_PRIOR_KNOWLEDGE_RE = re.compile(
    r"\b(?:what do you (?:already )?know about|what have you (?:already )?heard about"
    r"|how much do you know about|have you (?:been told|heard) anything about"
    r"|what have you been told about|what do you understand about)\s+(.+)",
    re.IGNORECASE,
)
_WEAK_PRIOR_KNOWLEDGE_RE = re.compile(
    r"\bdo you know (?:anything|much) about\s+(.+)",
    re.IGNORECASE,
)


def _extract_target(match_text: str) -> Optional[str]:
    target = match_text.strip().rstrip("?.! ").strip()
    return target or None


def _prior_knowledge_tier(sentence: str) -> Optional[tuple]:
    m = _STRONG_PRIOR_KNOWLEDGE_RE.search(sentence)
    if m:
        return "strong", _extract_target(m.group(1))
    m = _WEAK_PRIOR_KNOWLEDGE_RE.search(sentence)
    if m:
        return "weak", _extract_target(m.group(1))
    return None


class PriorKnowledgeEvent(BaseModel):
    turn_index: int
    evidence_text: str
    event_type: str  # EVENT_PRIOR_KNOWLEDGE_CHECK | EVENT_PRIOR_KNOWLEDGE_UNCERTAIN
    target: Optional[str] = None
    provenance: str = PROVENANCE_DETERMINISTIC
    evidence_level: str = EVIDENCE_LEVEL_DETERMINISTIC


def detect_prior_knowledge_events(history: List[Dict[str, str]]) -> List[PriorKnowledgeEvent]:
    """Per-turn (E1 needs no multi-turn context to be evidence, unlike E2/E3),
    same contract as question_behaviour.detect_question_events."""
    events: List[PriorKnowledgeEvent] = []
    for idx, turn in enumerate(history or []):
        if turn.get("role") != "nurse":
            continue
        for sentence in _sentences(turn.get("content", "")):
            tier = _prior_knowledge_tier(sentence)
            if tier is None:
                continue
            level, target = tier
            events.append(PriorKnowledgeEvent(
                turn_index=idx, evidence_text=sentence,
                event_type=EVENT_PRIOR_KNOWLEDGE_CHECK if level == "strong" else EVENT_PRIOR_KNOWLEDGE_UNCERTAIN,
                target=target,
            ))
    return events


# ── E2 reaction / response ──────────────────────────────────────────────────
_REACTION_RESPONSE_PHRASES = [
    "i can see that's worrying you", "i can see why that worries you",
    "i can see this is worrying you", "i can see that this is worrying you",
    "i understand this may be difficult to hear", "i understand that may be difficult to hear",
    "would you like me to explain that again", "would you like me to go over that again",
    "let's go over that again", "let me go over that again",
    "how does that sound to you", "how are you feeling about that",
]


def _reaction_response_sentence(content: str) -> Optional[str]:
    text = content.lower()
    for phrase in _REACTION_RESPONSE_PHRASES:
        if phrase in text:
            for sentence in _sentences(content):
                if phrase in sentence.lower():
                    return sentence
            return content.strip()
    return None


class ReactionResponseEvent(BaseModel):
    turn_index: int
    evidence_text: str
    event_type: str  # EVENT_REACTION_RESPONSE | EVENT_REACTION_RESPONSE_UNCERTAIN
    related_patient_turns: List[int] = []
    related_information_turns: List[int] = []
    provenance: str = PROVENANCE_DETERMINISTIC
    evidence_level: str = EVIDENCE_LEVEL_DETERMINISTIC


def detect_reaction_response_events(history: List[Dict[str, str]]) -> List[ReactionResponseEvent]:
    """Whole-transcript (Step B/4/13: needs the two turns before this one),
    same shape as information_gathering_evidence.detect_clarification_events."""
    history = history or []
    events: List[ReactionResponseEvent] = []
    for idx, turn in enumerate(history):
        if turn.get("role") != "nurse":
            continue
        sentence = _reaction_response_sentence(turn.get("content", ""))
        if sentence is None:
            continue

        prev = history[idx - 1] if idx > 0 else None
        if not prev or prev.get("role") != "patient":
            # No patient reaction precedes this at all -- isolated empathy,
            # not E2 evidence (Step 21's own false-positive example).
            continue

        patient_idx = idx - 1
        info_turn = history[idx - 2] if idx - 2 >= 0 else None
        if _is_information_giving_turn(info_turn):
            events.append(ReactionResponseEvent(
                turn_index=idx, evidence_text=sentence, event_type=EVENT_REACTION_RESPONSE,
                related_patient_turns=[patient_idx], related_information_turns=[idx - 2],
            ))
        else:
            events.append(ReactionResponseEvent(
                turn_index=idx, evidence_text=sentence, event_type=EVENT_REACTION_RESPONSE_UNCERTAIN,
                related_patient_turns=[patient_idx],
            ))
    return events


# ── E3 contribution invitation ──────────────────────────────────────────────
_CONTRIBUTION_INVITATION_RE = re.compile(
    r"\b(?:how do you feel about that|what do you think about that|how does that sound"
    r"|what are your thoughts|does that concern you|would you like to tell me what you think)\b",
    re.IGNORECASE,
)


class ContributionInvitationEvent(BaseModel):
    turn_index: int
    evidence_text: str
    event_type: str  # EVENT_CONTRIBUTION_INVITATION | EVENT_CONTRIBUTION_INVITATION_UNCERTAIN
    related_information_turns: List[int] = []
    provenance: str = PROVENANCE_DETERMINISTIC
    evidence_level: str = EVIDENCE_LEVEL_DETERMINISTIC


def detect_contribution_invitation_events(history: List[Dict[str, str]]) -> List[ContributionInvitationEvent]:
    """Whole-transcript (Step 7/13: needs nearby turns to judge information
    context), same shape as detect_reaction_response_events above."""
    history = history or []
    events: List[ContributionInvitationEvent] = []
    for idx, turn in enumerate(history):
        if turn.get("role") != "nurse":
            continue
        content = turn.get("content", "")
        sentences = _sentences(content)
        for i, sentence in enumerate(sentences):
            if not _CONTRIBUTION_INVITATION_RE.search(sentence):
                continue

            # Step 7: same-turn earlier declarative sentence counts as the
            # information context (e.g. "Insulin can cause bruising. How does
            # that sound?"); otherwise fall back to nearby turns.
            same_turn_info = any("?" not in s for s in sentences[:i])
            if same_turn_info:
                events.append(ContributionInvitationEvent(
                    turn_index=idx, evidence_text=sentence, event_type=EVENT_CONTRIBUTION_INVITATION,
                    related_information_turns=[idx],
                ))
                continue

            prev = history[idx - 1] if idx > 0 else None
            if _is_information_giving_turn(prev):
                events.append(ContributionInvitationEvent(
                    turn_index=idx, evidence_text=sentence, event_type=EVENT_CONTRIBUTION_INVITATION,
                    related_information_turns=[idx - 1],
                ))
                continue

            info_before_reaction = history[idx - 2] if prev and prev.get("role") == "patient" and idx - 2 >= 0 else None
            if _is_information_giving_turn(info_before_reaction):
                events.append(ContributionInvitationEvent(
                    turn_index=idx, evidence_text=sentence, event_type=EVENT_CONTRIBUTION_INVITATION,
                    related_information_turns=[idx - 2],
                ))
                continue

            events.append(ContributionInvitationEvent(
                turn_index=idx, evidence_text=sentence, event_type=EVENT_CONTRIBUTION_INVITATION_UNCERTAIN,
            ))
    return events


# ── E5 further information needs ────────────────────────────────────────────
_STRONG_FURTHER_INFO_RE = re.compile(
    r"\b(?:do you have any other questions|is there anything else you(?:'d| would) like"
    r"|what else would you like me to explain|is there anything you(?:'d| would) like me to"
    r"|do you have any concerns about (?:that|this)|is there anything else you want to ask"
    r"|any other questions)\b",
    re.IGNORECASE,
)
_WEAK_FURTHER_INFO_RE = re.compile(r"\bdo you have any questions\??\s*$", re.IGNORECASE)


def _further_info_tier(sentence: str) -> Optional[str]:
    if _STRONG_FURTHER_INFO_RE.search(sentence):
        return "strong"
    if _WEAK_FURTHER_INFO_RE.search(sentence.strip()):
        return "weak"
    return None


class FurtherInformationEvent(BaseModel):
    turn_index: int
    evidence_text: str
    event_type: str  # EVENT_FURTHER_INFORMATION_CHECK | EVENT_FURTHER_INFORMATION_UNCERTAIN
    provenance: str = PROVENANCE_DETERMINISTIC
    evidence_level: str = EVIDENCE_LEVEL_DETERMINISTIC


def detect_further_information_events(history: List[Dict[str, str]]) -> List[FurtherInformationEvent]:
    """Per-turn (no multi-turn context needed), same contract as
    detect_prior_knowledge_events above."""
    events: List[FurtherInformationEvent] = []
    for idx, turn in enumerate(history or []):
        if turn.get("role") != "nurse":
            continue
        for sentence in _sentences(turn.get("content", "")):
            tier = _further_info_tier(sentence)
            if tier is None:
                continue
            events.append(FurtherInformationEvent(
                turn_index=idx, evidence_text=sentence,
                event_type=EVENT_FURTHER_INFORMATION_CHECK if tier == "strong" else EVENT_FURTHER_INFORMATION_UNCERTAIN,
            ))
    return events


class InformationGivingEvidence(BaseModel):
    prior_knowledge_events: List[PriorKnowledgeEvent] = []
    reaction_response_events: List[ReactionResponseEvent] = []
    contribution_invitation_events: List[ContributionInvitationEvent] = []
    further_information_events: List[FurtherInformationEvent] = []
    limitations: List[str] = LIMITATIONS


def detect_information_giving_evidence(history: List[Dict[str, str]]) -> InformationGivingEvidence:
    """Step L bundling entry point -- speaking_evidence.py calls the four
    detector functions directly (same per-detector call shape as every other
    detector in this family); this exists for callers wanting the whole
    E1/E2/E3/E5 picture at once (golden cases, admin inspection)."""
    return InformationGivingEvidence(
        prior_knowledge_events=detect_prior_knowledge_events(history),
        reaction_response_events=detect_reaction_response_events(history),
        contribution_invitation_events=detect_contribution_invitation_events(history),
        further_information_events=detect_further_information_events(history),
    )


if __name__ == "__main__":
    # E1
    e1 = detect_prior_knowledge_events([{"role": "nurse", "content": "What do you already know about insulin?"}])
    assert len(e1) == 1 and e1[0].event_type == EVENT_PRIOR_KNOWLEDGE_CHECK and e1[0].target == "insulin"

    assert detect_prior_knowledge_events([{"role": "nurse", "content": "Do you know where the clinic is?"}]) == []
    assert detect_prior_knowledge_events([{"role": "nurse", "content": "What medication are you taking?"}]) == []

    weak_e1 = detect_prior_knowledge_events([{"role": "nurse", "content": "Do you know much about diabetes?"}])
    assert len(weak_e1) == 1 and weak_e1[0].event_type == EVENT_PRIOR_KNOWLEDGE_UNCERTAIN

    # E2
    e2 = detect_reaction_response_events([
        {"role": "nurse", "content": "Insulin injections can sometimes cause bruising."},
        {"role": "patient", "content": "I'm worried they'll hurt."},
        {"role": "nurse", "content": "I can see why that worries you. Let's talk about ways to make it more comfortable."},
    ])
    assert len(e2) == 1 and e2[0].event_type == EVENT_REACTION_RESPONSE
    assert e2[0].related_patient_turns == [1] and e2[0].related_information_turns == [0]

    isolated = detect_reaction_response_events([
        {"role": "nurse", "content": "I can see that's worrying you. Let's talk about that."},
    ])
    assert isolated == []

    ambiguous_e2 = detect_reaction_response_events([
        {"role": "patient", "content": "I'm scared."},
        {"role": "nurse", "content": "I can see that's worrying you."},
    ])
    assert len(ambiguous_e2) == 1 and ambiguous_e2[0].event_type == EVENT_REACTION_RESPONSE_UNCERTAIN

    # E3
    e3 = detect_contribution_invitation_events([
        {"role": "nurse", "content": "Insulin can help control your blood sugar. How does that sound to you?"},
    ])
    assert len(e3) == 1 and e3[0].event_type == EVENT_CONTRIBUTION_INVITATION

    assert detect_contribution_invitation_events([{"role": "nurse", "content": "What happened yesterday?"}]) == []

    # E5
    e5 = detect_further_information_events([{"role": "nurse", "content": "Do you have any other questions?"}])
    assert len(e5) == 1 and e5[0].event_type == EVENT_FURTHER_INFORMATION_CHECK

    assert detect_further_information_events([{"role": "nurse", "content": "Do you understand?"}]) == []

    weak_e5 = detect_further_information_events([{"role": "nurse", "content": "Do you have any questions?"}])
    assert len(weak_e5) == 1 and weak_e5[0].event_type == EVENT_FURTHER_INFORMATION_UNCERTAIN

    print("information_giving_evidence self-check OK")
