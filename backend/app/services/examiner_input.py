"""ExaminerInput Assembler (Step 19).

Packages (scenario, transcript, UnifiedEvidence, session metadata, optional
audio evidence) into one deterministic, typed contract for the FUTURE OET
Examiner. This module does not score, judge, or call any model -- it only
assembles what already exists elsewhere into one traceable shape.

Architecture:

    Scenario + Transcript + UnifiedEvidence + audio evidence + session metadata
        -> build_examiner_input() (pure function, no I/O)
        -> ExaminerInput
        -> [FUTURE] Criterion Evidence Mapper
        -> [FUTURE] Shadow Examiner

Hard boundary (see task spec): 0 model calls, 0 DB access, 0 mutation of any
upstream evidence object, 0 scoring logic. build_examiner_input never reruns
PatientState/semantic evidence/reconciliation/pronunciation -- it consumes
their already-computed output and reports anything unavailable as a
structured EvidenceGap, never a guessed value and never a score.

MISSING vs NEGATIVE (Step 16/J): ExaminerInput carries no score field
anywhere. An EvidenceGap can only ever describe evidence availability
(reason_code + availability), never "the candidate performed badly" --
there is structurally nothing here a gap could set to a bad value.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.services.evidence_reconciliation import UnifiedEvidence
from app.services.speaking_evidence import JargonEvidence

# ── Criterion identifiers (Step 12) ──────────────────────────────────────
# Plain string constants, matching this codebase's existing convention
# (SOURCE_DETERMINISTIC, PROVENANCE_HYBRID, ...) rather than an Enum. These
# name the OFFICIAL OET spec's own vocabulary (see the uploaded Assessment
# Criteria PDF), deliberately decoupled from ai_scoring.score_speaking's
# ad-hoc prompt keys ("empathy", "grammar") -- this contract targets the
# future examiner, not the current scorer, and must not silently inherit
# that prompt's naming choices.

CRITERION_INTELLIGIBILITY = "intelligibility"
CRITERION_FLUENCY = "fluency"
CRITERION_APPROPRIATENESS_OF_LANGUAGE = "appropriateness_of_language"
CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION = "resources_of_grammar_and_expression"

CRITERION_RELATIONSHIP_BUILDING = "relationship_building"
CRITERION_PATIENT_PERSPECTIVE = "patient_perspective"
CRITERION_PROVIDING_STRUCTURE = "providing_structure"
CRITERION_INFORMATION_GATHERING = "information_gathering"
CRITERION_INFORMATION_GIVING = "information_giving"

LINGUISTIC_CRITERIA: List[str] = [
    CRITERION_INTELLIGIBILITY, CRITERION_FLUENCY,
    CRITERION_APPROPRIATENESS_OF_LANGUAGE, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION,
]
CLINICAL_CRITERIA: List[str] = [
    CRITERION_RELATIONSHIP_BUILDING, CRITERION_PATIENT_PERSPECTIVE, CRITERION_PROVIDING_STRUCTURE,
    CRITERION_INFORMATION_GATHERING, CRITERION_INFORMATION_GIVING,
]
ALL_CRITERIA: List[str] = LINGUISTIC_CRITERIA + CLINICAL_CRITERIA

# ── Clinical indicators (Step 12/17) ─────────────────────────────────────
# Evidence REFERENCES inside the 5 clinical criteria, not separate scores
# (19 indicators, 5 criteria -- never 19 scores, per the task spec).

INDICATORS_BY_CRITERION: Dict[str, List[str]] = {
    CRITERION_INTELLIGIBILITY: [],
    CRITERION_FLUENCY: [],
    CRITERION_APPROPRIATENESS_OF_LANGUAGE: [],
    CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION: [],
    CRITERION_RELATIONSHIP_BUILDING: ["A1", "A2", "A3", "A4"],
    CRITERION_PATIENT_PERSPECTIVE: ["B1", "B2", "B3"],
    CRITERION_PROVIDING_STRUCTURE: ["C1", "C2", "C3"],
    CRITERION_INFORMATION_GATHERING: ["D1", "D2", "D3", "D4", "D5"],
    CRITERION_INFORMATION_GIVING: ["E1", "E2", "E3", "E4", "E5"],
}

INDICATOR_TEXT: Dict[str, str] = {
    "A1": "initiating the interaction appropriately (greeting, introductions, nature of interview)",
    "A2": "demonstrating an attentive and respectful attitude",
    "A3": "adopting a non-judgmental approach",
    "A4": "showing empathy for feelings/predicament/emotional state",
    "B1": "eliciting and exploring the patient's ideas/concerns/expectations",
    "B2": "picking up the patient's cues",
    "B3": "relating explanations to elicited ideas/concerns/expectations",
    "C1": "sequencing the interview purposefully and logically",
    "C2": "signposting changes in topic",
    "C3": "using organising techniques in explanations",
    "D1": "facilitating the patient's narrative with active listening techniques, minimising interruption",
    "D2": "using initially open questions, appropriately moving to closed questions",
    "D3": "NOT using compound questions/leading questions",
    "D4": "clarifying statements which are vague or need amplification",
    "D5": "summarising information to encourage correction/invite further information",
    "E1": "establishing initially what the patient already knows",
    "E2": "pausing periodically when giving information, using the response to guide next steps",
    "E3": "encouraging the patient to contribute reactions/feelings",
    "E4": "checking whether the patient has understood information",
    "E5": "discovering what further information the patient needs",
}

# ── Evidence-quality vocabulary (Step 21) ────────────────────────────────
# Describes evidence AVAILABILITY/QUALITY only -- never candidate
# performance quality.
AVAILABILITY_STRONG = "STRONG"
AVAILABILITY_PARTIAL = "PARTIAL"
AVAILABILITY_LIMITED = "LIMITED"
AVAILABILITY_INSUFFICIENT = "INSUFFICIENT"

# ── Gap reason codes ──────────────────────────────────────────────────────
REASON_NO_AUDIO_EVIDENCE = "no_audio_evidence"
REASON_JARGON_DETECTOR_PARTIAL_COVERAGE = "jargon_detector_partial_coverage"
REASON_NO_GRAMMAR_DETECTOR = "no_grammar_detector"
REASON_NO_INDICATOR_LEVEL_DETECTOR = "no_indicator_level_detector"


class ScenarioContext(BaseModel):
    scenario_id: Optional[int] = None
    title: str = ""
    setting: str = ""
    difficulty: Optional[str] = None
    specialty: Optional[str] = None
    nurse_tasks: List[str] = []
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_condition: Optional[str] = None
    patient_mood: Optional[str] = None
    patient_background: Optional[str] = None
    patient_concerns: List[str] = []
    hidden_information_items: List[str] = []  # internal only -- never expose to students
    emotional_triggers: List[str] = []


class TranscriptTurn(BaseModel):
    role: str
    content: str
    turn_index: int


class PronunciationEvidence(BaseModel):
    overall_score: float
    fluency_score: float
    completeness_score: float
    words: List[Dict[str, Any]] = []
    problem_words: List[Dict[str, Any]] = []
    transcript: Optional[str] = None


class LinguisticEvidence(BaseModel):
    pronunciation: Optional[PronunciationEvidence] = None
    accent_pattern_hints: List[Dict[str, Any]] = []
    jargon_evidence: List[JargonEvidence] = []
    grammar_evidence_note: str = "transcript only -- no structured grammar evidence source exists today"


class ClinicalEvidence(BaseModel):
    unified_evidence: UnifiedEvidence


class SessionContext(BaseModel):
    pipeline: Optional[str] = None
    session_usage_id: Optional[int] = None
    duration_seconds: Optional[float] = None
    turn_count: int = 0
    nurse_turn_count: int = 0
    patient_turn_count: int = 0
    interrupted_count: Optional[int] = None


class AudioAvailability(BaseModel):
    audio_available: bool
    pronunciation_evidence_available: bool
    fluency_evidence_available: bool


class EvidenceGap(BaseModel):
    criterion: str
    indicator: Optional[str] = None
    reason_code: str
    missing_evidence_type: str
    availability: str  # STRONG|PARTIAL|LIMITED|INSUFFICIENT -- evidence quality, never performance


class ExaminerInput(BaseModel):
    scenario_context: ScenarioContext
    transcript: List[TranscriptTurn]
    linguistic_evidence: LinguisticEvidence
    clinical_evidence: ClinicalEvidence
    session_context: SessionContext
    audio_availability: AudioAvailability
    evidence_gaps: List[EvidenceGap]
    criteria: List[str] = ALL_CRITERIA


def _build_scenario_context(scenario: Dict[str, Any]) -> ScenarioContext:
    scenario = scenario or {}
    nurse_card = scenario.get("nurse_card") or {}
    card = scenario.get("interlocutor_card") or {}
    return ScenarioContext(
        scenario_id=scenario.get("id"),
        title=scenario.get("title") or "",
        setting=scenario.get("setting") or "",
        difficulty=scenario.get("difficulty"),
        specialty=scenario.get("specialty"),
        nurse_tasks=list(nurse_card.get("tasks") or []),
        patient_name=card.get("patient_name"),
        patient_age=card.get("age"),
        patient_condition=card.get("condition"),
        patient_mood=card.get("mood"),
        patient_background=card.get("background"),
        patient_concerns=list(card.get("questions_to_ask") or card.get("concerns") or []),
        hidden_information_items=list(card.get("information_to_withhold") or []),
        emotional_triggers=list(card.get("emotional_triggers") or []),
    )


def _build_transcript(transcript: List[Dict[str, str]]) -> List[TranscriptTurn]:
    return [
        TranscriptTurn(role=t.get("role", ""), content=t.get("content", ""), turn_index=idx)
        for idx, t in enumerate(transcript or [])
    ]


def _build_pronunciation(audio_evidence: Optional[Dict[str, Any]]) -> tuple[Optional[PronunciationEvidence], List[Dict[str, Any]]]:
    """Reads the existing, unmodified shape returned by
    pronunciation.get_pronunciation_feedback() (or None). Never calls Azure,
    never fabricates a score -- azure.available must be True for a
    PronunciationEvidence to exist at all."""
    audio_evidence = audio_evidence or {}
    azure = audio_evidence.get("azure") or {}
    pattern_hints = list(audio_evidence.get("pattern_analysis") or [])

    if not azure.get("available"):
        return None, pattern_hints

    pronunciation = PronunciationEvidence(
        overall_score=azure.get("overall_score", 0),
        fluency_score=azure.get("fluency_score", 0),
        completeness_score=azure.get("completeness_score", 0),
        words=list(azure.get("words") or []),
        problem_words=list(azure.get("problem_words") or []),
        transcript=azure.get("transcript"),
    )
    return pronunciation, pattern_hints


def _build_session_context(
    session_context: Optional[Dict[str, Any]], unified_evidence: UnifiedEvidence,
) -> SessionContext:
    session_context = session_context or {}
    turn_counts = unified_evidence.interaction_metrics.turn_counts
    return SessionContext(
        pipeline=session_context.get("pipeline"),
        session_usage_id=session_context.get("session_usage_id"),
        duration_seconds=session_context.get("duration_seconds"),
        turn_count=turn_counts.get("total", 0),
        nurse_turn_count=turn_counts.get("nurse", 0),
        patient_turn_count=turn_counts.get("patient", 0),
        interrupted_count=session_context.get("interrupted_count"),
    )


def _build_evidence_gaps(
    pronunciation: Optional[PronunciationEvidence],
) -> List[EvidenceGap]:
    gaps: List[EvidenceGap] = []

    if pronunciation is None:
        for criterion in (CRITERION_INTELLIGIBILITY, CRITERION_FLUENCY):
            gaps.append(EvidenceGap(
                criterion=criterion, reason_code=REASON_NO_AUDIO_EVIDENCE,
                missing_evidence_type="acoustic_pronunciation_data", availability=AVAILABILITY_INSUFFICIENT,
            ))

    gaps.append(EvidenceGap(
        criterion=CRITERION_APPROPRIATENESS_OF_LANGUAGE, reason_code=REASON_JARGON_DETECTOR_PARTIAL_COVERAGE,
        missing_evidence_type="full_register_and_lexis_analysis", availability=AVAILABILITY_PARTIAL,
    ))

    gaps.append(EvidenceGap(
        criterion=CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, reason_code=REASON_NO_GRAMMAR_DETECTOR,
        missing_evidence_type="structured_grammar_analysis", availability=AVAILABILITY_INSUFFICIENT,
    ))

    for criterion in CLINICAL_CRITERIA:
        for indicator in INDICATORS_BY_CRITERION[criterion]:
            gaps.append(EvidenceGap(
                criterion=criterion, indicator=indicator, reason_code=REASON_NO_INDICATOR_LEVEL_DETECTOR,
                missing_evidence_type="indicator_specific_evidence", availability=AVAILABILITY_PARTIAL,
            ))

    return gaps


def build_examiner_input(
    scenario: Dict[str, Any],
    transcript: List[Dict[str, str]],
    unified_evidence: UnifiedEvidence,
    session_context: Optional[Dict[str, Any]] = None,
    audio_evidence: Optional[Dict[str, Any]] = None,
) -> ExaminerInput:
    """Pure function: same inputs always yield the same ExaminerInput. No DB
    access, no network, no LLM calls, no mutation of any input object.

    `scenario`: raw scenario row dict (title/setting/nurse_card/
    interlocutor_card), same shape routers already fetch.
    `transcript`: list of {"role", "content"} turns, same shape both
    speaking pipelines already normalize to.
    `unified_evidence`: output of evidence_reconciliation.reconcile_evidence
    -- reused wholesale, never recomputed here.
    `session_context`: optional dict of {"pipeline", "session_usage_id",
    "duration_seconds", "interrupted_count"} -- any missing key stays None,
    never guessed.
    `audio_evidence`: optional, the exact dict shape returned by
    pronunciation.get_pronunciation_feedback() -- or None if no audio
    evidence exists for this session.
    """
    if not isinstance(unified_evidence, UnifiedEvidence):
        raise ValueError("unified_evidence must be a UnifiedEvidence instance")
    if transcript is not None and not isinstance(transcript, list):
        raise ValueError("transcript must be a list of {role, content} turns")

    pronunciation, pattern_hints = _build_pronunciation(audio_evidence)

    linguistic_evidence = LinguisticEvidence(
        pronunciation=pronunciation,
        accent_pattern_hints=pattern_hints,
        jargon_evidence=list(unified_evidence.jargon_evidence),
    )

    audio_availability = AudioAvailability(
        audio_available=pronunciation is not None,
        pronunciation_evidence_available=pronunciation is not None,
        fluency_evidence_available=pronunciation is not None,
    )

    return ExaminerInput(
        scenario_context=_build_scenario_context(scenario),
        transcript=_build_transcript(transcript),
        linguistic_evidence=linguistic_evidence,
        clinical_evidence=ClinicalEvidence(unified_evidence=unified_evidence),
        session_context=_build_session_context(session_context, unified_evidence),
        audio_availability=audio_availability,
        evidence_gaps=_build_evidence_gaps(pronunciation),
    )
