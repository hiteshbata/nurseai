"""Shadow Examiner Calibration Benchmark (Phase 4, Step 21K continuation).

Design doc: docs/SHADOW_EXAMINER_DESIGN.md, section 22 ("Golden consultation
plan") and Implementation Phase 4. This module builds that golden set.

Scope / hard boundary: OFFLINE ONLY. Every consultation below is hand-authored
(not sampled from production), every SpeakingEvidence object is hand-built
(not detector-derived), and every reference judgement is hand-authored by
this module's author acting as a stand-in human reviewer. Zero model calls,
zero `ai_registry` lookups, zero DB access, zero network access -- importing
this module and calling every function in it is a pure, offline operation.
This module does NOT touch `score_speaking()`, `/speaking/score`, Learning
Brain, or any student-facing score. It is not wired into anything that runs
in production.

Purpose: give three independent reviewers (a trained human, the Sonnet
Shadow Examiner, and any future candidate examiner model) the exact same
fixed input --

    consultation -> ExaminerInput -> CriterionEvidenceMap -> reference judgement

-- so their outputs are comparable on identical evidence, per
SHADOW_EXAMINER_DESIGN.md section 21 ("Human calibration plan"). The
benchmark is model-independent: `BenchmarkCase.export_dict()` below produces
a plain JSON-able dict with no Python-specific types, consumable by a human
reviewer, a Claude prompt, or any other model's API without importing this
codebase.

Reference judgements reuse `shadow_examiner.CriterionJudgement` unchanged
(same schema the future model output must satisfy) rather than inventing a
parallel "human judgement" shape -- one schema, two authors (human vs model),
is exactly what a calibration diff needs.

`evidence_quality` on every reference judgement is READ from the actual
CriterionEvidenceMap this module built for that case (via `_quality_of`),
never guessed -- it is a coverage fact the pure evidence pipeline already
computed, not something a human reviewer should re-derive by eye.

STATUS/LEVEL DISCIPLINE (design doc section 15, the single most important
calibration risk this benchmark exists to test): an indicator or criterion
with genuinely no supporting evidence this session is `status="limited_
evidence", level=None` -- never `level=0`. Several cases below (weak_overall,
information_giving_all_gaps, minimal_consultation) exist specifically to
verify a reviewer does not collapse "no evidence" into "failing score".

Cases 14-20 (added in the 13->20 expansion) extend the set with adjacent-
level borderline judgements (clinical 3/2, 2/1, 1/0 and linguistic 5/4,
4/3), a long, evidence-dense consultation, and a cross-criterion mixed-
evidence case. Every reference judgement on a borderline case is explicitly
marked as one defensible reading among several, never as an objectively
correct score -- see `tags` on each BenchmarkCase and the "reasonable
evaluator could disagree" language in those cases' justifications.
`reference_status` stays "provisional" on every case until a real human
reviewer signs off (Phase 4 does not do that sign-off).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.services.criterion_evidence import (
    LEVEL_L1_DIRECT,
    LEVEL_L2_DETERMINISTIC,
    LEVEL_L3_SEMANTIC,
    LEVEL_L4_PATIENT_OUTCOME,
    CriterionEvidenceMap,
    map_criterion_evidence,
)
from app.services.evidence_reconciliation import reconcile_evidence
from app.services.examiner_input import (
    ALL_CRITERIA,
    CRITERION_APPROPRIATENESS_OF_LANGUAGE,
    CRITERION_FLUENCY,
    CRITERION_INFORMATION_GATHERING,
    CRITERION_INFORMATION_GIVING,
    CRITERION_INTELLIGIBILITY,
    CRITERION_PATIENT_PERSPECTIVE,
    CRITERION_PROVIDING_STRUCTURE,
    CRITERION_RELATIONSHIP_BUILDING,
    CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION,
    ExaminerInput,
    build_examiner_input,
)
from app.services.shadow_examiner import (
    CLINICAL_LEVEL_LABELS,
    FAMILY_CLINICAL,
    FAMILY_LINGUISTIC,
    STATUS_ASSESSED,
    STATUS_EVIDENCE_CONFLICT_UNRESOLVED,
    STATUS_LIMITED_EVIDENCE,
    CriterionJudgement,
    EvidenceRefPointer,
    ShadowResult,
    SessionRef,
)
from app.services.speaking_evidence import (
    SOURCE_DETERMINISTIC,
    SOURCE_SEMANTIC,
    CandidateEvent,
    ConcernOutcome,
    InteractionMetrics,
    JargonEvidence,
    PatientEvent,
    SpeakingEvidence,
    StateTransition,
)

# ── Benchmark case container ──────────────────────────────────────────────


class BenchmarkCase(BaseModel):
    case_id: str
    archetype: str
    description: str
    scenario: Dict[str, Any]
    transcript: List[Dict[str, str]]
    examiner_input: ExaminerInput
    criterion_evidence_map: CriterionEvidenceMap
    reference_judgement: List[CriterionJudgement]
    # Additive (cases 1-13 default to both): free-form calibration labels
    # ("borderline", "adjacent_level", "long_consultation", ...) and an
    # explicit reminder that no case's reference judgement is an authoritative
    # score until a real human reviewer validates it (see module docstring).
    tags: List[str] = []
    reference_status: str = "provisional"

    def export_dict(self) -> Dict[str, Any]:
        """Plain-dict export for a non-Python reviewer (human doc, another
        model's prompt). Every field is already JSON-safe pydantic output --
        no Python-specific types survive."""
        return {
            "case_id": self.case_id,
            "archetype": self.archetype,
            "description": self.description,
            "tags": self.tags,
            "reference_status": self.reference_status,
            "scenario": self.scenario,
            "transcript": self.transcript,
            "examiner_input": self.examiner_input.model_dump(mode="json"),
            "criterion_evidence_map": self.criterion_evidence_map.model_dump(mode="json"),
            "reference_judgement": [j.model_dump(mode="json") for j in self.reference_judgement],
        }


# ── Small helpers shared by every case builder below ──────────────────────


def _metrics(transcript: List[Dict[str, str]]) -> InteractionMetrics:
    # ponytail: turn_counts is the only field map_criterion_evidence/
    # build_examiner_input actually read off interaction_metrics; the four
    # event-count ints exist only for InteractionMetrics' own schema and are
    # never consulted downstream of this module, so they're zeroed rather
    # than recomputed from candidate_events.
    nurse = sum(1 for t in transcript if t["role"] == "nurse")
    patient = sum(1 for t in transcript if t["role"] == "patient")
    return InteractionMetrics(
        turn_counts={"nurse": nurse, "patient": patient, "total": len(transcript)},
        jargon_events=0, empathy_events=0, concern_exploration_events=0,
        understanding_check_events=0, dismissive_events=0,
    )


def _quality_of(cem: CriterionEvidenceMap, criterion: str) -> str:
    for bundle in cem.clinical:
        if bundle.criterion == criterion:
            return bundle.criterion_evidence_quality
    for bundle in cem.linguistic:
        if bundle.criterion == criterion:
            return bundle.evidence_quality
    raise ValueError(f"unknown criterion: {criterion!r}")


def _judgement(
    cem: CriterionEvidenceMap, criterion: str, family: str, status: str, *,
    level: Optional[int] = None, justification: str,
    evidence_refs: Optional[List[EvidenceRefPointer]] = None,
    limitations: Optional[List[str]] = None,
) -> CriterionJudgement:
    level_label = CLINICAL_LEVEL_LABELS[level] if (family == FAMILY_CLINICAL and status == STATUS_ASSESSED) else None
    return CriterionJudgement(
        criterion=criterion, family=family, status=status, level=level, level_label=level_label,
        justification=justification, evidence_refs=evidence_refs or [],
        evidence_quality=_quality_of(cem, criterion), limitations=limitations or [],
    )


def _ref(source: str, evidence_id: str, turn_index: Optional[int], evidence_level: str, provenance: str) -> EvidenceRefPointer:
    return EvidenceRefPointer(evidence_id=evidence_id, turn_index=turn_index, evidence_level=evidence_level, source=source, provenance=provenance)


def build_case(
    case_id: str, archetype: str, description: str,
    scenario: Dict[str, Any], transcript: List[Dict[str, str]], *,
    candidate_events: Optional[List[CandidateEvent]] = None,
    patient_events: Optional[List[PatientEvent]] = None,
    concern_outcomes: Optional[List[ConcernOutcome]] = None,
    state_transitions: Optional[List[StateTransition]] = None,
    jargon_evidence: Optional[List[JargonEvidence]] = None,
    session_context: Optional[Dict[str, Any]] = None,
    audio_evidence: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    judgements_fn,
) -> BenchmarkCase:
    """Wires one hand-authored consultation through the real, unmodified
    pure pipeline (reconcile_evidence -> build_examiner_input ->
    map_criterion_evidence) so every case's CriterionEvidenceMap is the
    actual output of production code, not a hand-faked stand-in."""
    speaking_evidence = SpeakingEvidence(
        candidate_events=candidate_events or [], patient_events=patient_events or [],
        concern_outcomes=concern_outcomes or [], state_transitions=state_transitions or [],
        jargon_evidence=jargon_evidence or [], interaction_metrics=_metrics(transcript),
    )
    unified = reconcile_evidence(speaking_evidence)
    examiner_input = build_examiner_input(scenario, transcript, unified, session_context, audio_evidence)
    cem = map_criterion_evidence(examiner_input)
    judgements = judgements_fn(cem)
    return BenchmarkCase(
        case_id=case_id, archetype=archetype, description=description,
        scenario=scenario, transcript=transcript, examiner_input=examiner_input,
        criterion_evidence_map=cem, reference_judgement=judgements, tags=tags or [],
    )


def _scenario(
    *, id_: int, title: str, setting: str, difficulty: str, specialty: str,
    patient_name: str, age: int, condition: str, mood: str, background: str,
    concerns: List[str], tasks: List[str],
) -> Dict[str, Any]:
    return {
        "id": id_, "title": title, "setting": setting, "difficulty": difficulty, "specialty": specialty,
        "nurse_card": {"tasks": tasks},
        "interlocutor_card": {
            "patient_name": patient_name, "age": age, "condition": condition, "mood": mood,
            "background": background, "questions_to_ask": concerns,
        },
    }


def _elite_audio(overall: float, fluency: float, completeness: float, problem_words: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {
        "method": "azure",
        "azure": {
            "available": True, "overall_score": overall, "fluency_score": fluency, "completeness_score": completeness,
            "words": [], "problem_words": problem_words or [], "transcript": None,
        },
        "pattern_analysis": [], "has_azure": True,
    }


NO_AUDIO: Optional[Dict[str, Any]] = None


# ═══════════════════════════════════════════════════════════════════════
# Case 1 -- strong_overall
# ═══════════════════════════════════════════════════════════════════════

def _case_01_strong_overall() -> BenchmarkCase:
    concern = "Will I be able to walk again unaided?"
    scenario = _scenario(
        id_=101, title="Post-operative hip surgery follow-up", setting="Orthopaedic ward",
        difficulty="medium", specialty="orthopaedic", patient_name="Sam", age=58,
        condition="post-operative hip replacement", mood="anxious",
        background="First major surgery, lives alone, worried about independence.",
        concerns=[concern],
        tasks=["Explain recovery timeline", "Address mobility concerns", "Discuss pain management"],
    )
    transcript = [
        {"role": "nurse", "content": "Hello Sam, my name is Alex and I'm one of the nurses looking after you today. I'd like to ask a few questions and go through your recovery plan, is that alright?"},
        {"role": "patient", "content": "Okay, thank you. I've been really worried about walking again."},
        {"role": "nurse", "content": "I can hear that this is weighing on you, and that's completely understandable after major surgery like this."},
        {"role": "patient", "content": "The pain has also been quite bad at night."},
        {"role": "nurse", "content": "That sounds difficult. Can you tell me a bit more about when the pain is at its worst?"},
        {"role": "patient", "content": "Mostly when I try to turn over in bed."},
        {"role": "nurse", "content": "Thank you for explaining that. First I'll check your wound and mobility today, then we'll go through pain relief options, and finally I'll walk you through what to expect over the next two weeks."},
        {"role": "patient", "content": "That sounds good."},
        {"role": "nurse", "content": "Before we finish, do you have any other questions, especially about walking unaided again?"},
        {"role": "patient", "content": "Actually yes -- will I definitely be able to walk without a frame again?"},
        {"role": "nurse", "content": "That's an important question. Based on how your surgery went, the surgical team is optimistic that with physiotherapy you'll regain full unaided mobility. Does that help answer your worry?"},
        {"role": "patient", "content": "Yes, that helps a lot, thank you."},
    ]
    candidate_events = [
        CandidateEvent(event="opening_greeting", turn_index=0, evidence_text="Hello Sam, my name is Alex"),
        CandidateEvent(event="opening_introduction", turn_index=0, evidence_text="my name is Alex and I'm one of the nurses"),
        CandidateEvent(event="opening_purpose_setting", turn_index=0, evidence_text="I'd like to ask a few questions and go through your recovery plan"),
        CandidateEvent(event="empathy_acknowledgement", turn_index=2, evidence_text="I can hear that this is weighing on you"),
        CandidateEvent(event="attentive_acknowledgement", turn_index=4, evidence_text="That sounds difficult"),
        CandidateEvent(event="open_question", turn_index=4, evidence_text="Can you tell me a bit more about when the pain is at its worst?"),
        CandidateEvent(event="consultation_sequence_marker", turn_index=6, evidence_text="First I'll check your wound and mobility today, then we'll go through pain relief options"),
        CandidateEvent(event="organization_marker", turn_index=6, evidence_text="First ... then ... finally"),
        CandidateEvent(event="signposting_detected", turn_index=6, evidence_text="finally I'll walk you through what to expect"),
        CandidateEvent(event="further_information_check", turn_index=8, evidence_text="do you have any other questions"),
        CandidateEvent(event="concern_exploration", turn_index=8, evidence_text="especially about walking unaided again", target_concern=concern),
        CandidateEvent(event="concern_addressing", turn_index=10, evidence_text="the surgical team is optimistic that with physiotherapy you'll regain full unaided mobility", target_concern=concern),
        CandidateEvent(event="understanding_checked", turn_index=10, evidence_text="Does that help answer your worry?"),
    ]
    patient_events = [
        PatientEvent(event="concern_raised", turn_index=9, evidence_text=concern),
    ]
    concern_outcomes = [
        ConcernOutcome(
            concern=concern, final_status="resolved", resolved=True,
            history=[
                {"status": "raised", "turn_index": 9, "cause_event": None},
                {"status": "addressed", "turn_index": 10, "cause_event": "concern_addressing"},
                {"status": "resolved", "turn_index": 11, "cause_event": None},
            ],
            resolved_at_turns=[11],
        ),
    ]
    state_transitions = [
        StateTransition(field="current_emotion", before="anxious", after="reassured", cause_event="empathy_acknowledgement", turn_index=2),
        StateTransition(field=f"concern_status:{concern}", before="not_raised", after="raised", cause_event=None, turn_index=9),
        StateTransition(field=f"concern_status:{concern}", before="raised", after="addressed", cause_event="concern_addressing", turn_index=10),
        StateTransition(field=f"concern_status:{concern}", before="addressed", after="resolved", cause_event=None, turn_index=11),
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9001, "duration_seconds": 310.0, "interrupted_count": 0}
    audio_evidence = _elite_audio(84.0, 81.5, 96.0)

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=5,
                       justification="Azure pronunciation overall score 84.0 with no problem words flagged; clearly intelligible throughout.",
                       evidence_refs=[_ref("pronunciation", "overall_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=5,
                       justification="Fluency score 81.5, completeness 96.0; speech is smooth with no notable hesitation markers in the transcript.",
                       evidence_refs=[_ref("pronunciation", "fluency_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=5,
                       justification="Plain, patient-appropriate register throughout (\"walk without a frame\", \"pain relief options\"); no jargon detected.",
                       evidence_refs=[_ref("transcript", "turn_10", 10, LEVEL_L1_DIRECT, "direct")],
                       limitations=["jargon-absence check only covers lexical items; full register/lexis analysis unavailable this session"]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=5,
                       justification="Grammatically accurate, varied sentence structure (conditional \"with physiotherapy you'll regain\") across all turns; no structured grammar detector exists, judged from transcript alone.",
                       evidence_refs=[_ref("transcript", "turn_6", 6, LEVEL_L1_DIRECT, "direct")],
                       limitations=["no structured grammar analysis detector available"]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="Full appropriate opening (greeting, name, purpose), explicit empathy acknowledgement at turn 2, and the patient's anxious emotion resolves to reassured immediately after.",
                       evidence_refs=[
                           _ref("candidate_event", "opening_greeting", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "empathy_acknowledgement", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("state_transition", "current_emotion", 2, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ],
                       limitations=["no dedicated interruption metric beyond session-level count"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="Nurse proactively explored the mobility concern (turn 8), the patient raised it explicitly (turn 9), and it was addressed with a clear, direct answer and resolved by turn 11.",
                       evidence_refs=[
                           _ref("candidate_event", "concern_exploration", 8, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("concern_timeline", f"{concern}::resolved", 11, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="Clear explicit sequencing (\"First ... then ... finally\") announced up front and followed through in order across the remaining turns.",
                       evidence_refs=[
                           _ref("candidate_event", "consultation_sequence_marker", 6, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "organization_marker", 6, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_ASSESSED, level=2,
                       justification="One clear open question used to explore the pain (turn 4); no compound/leading questions present. No clarification or summary evidence this session, so this is graded on the single open-question sample only, not extrapolated higher.",
                       evidence_refs=[_ref("candidate_event", "open_question", 4, LEVEL_L2_DETERMINISTIC, "deterministic_rule")],
                       limitations=["no D1 active-listening-support or D4/D5 clarification/summary evidence detected this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_ASSESSED, level=2,
                       justification="Explicitly checked further questions before closing (turn 8) and confirmed understanding after answering the mobility question (turn 10); no evidence of establishing prior knowledge first.",
                       evidence_refs=[
                           _ref("candidate_event", "further_information_check", 8, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "understanding_checked", 10, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ],
                       limitations=["no E1 prior-knowledge-check evidence detected this session"]),
        ]

    return build_case(
        "case_01_strong_overall", "strong_overall",
        "Warm, structured, fully resolved consultation with elite (audio-scored) pronunciation and fluency -- the ceiling case.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        concern_outcomes=concern_outcomes, state_transitions=state_transitions,
        session_context=session_context, audio_evidence=audio_evidence, judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 2 -- weak_overall
# ═══════════════════════════════════════════════════════════════════════

def _case_02_weak_overall() -> BenchmarkCase:
    concern = "Why is my wound still red and sore?"
    scenario = _scenario(
        id_=102, title="Wound check, dismissive consultation", setting="Surgical outpatient clinic",
        difficulty="medium", specialty="surgical", patient_name="Jo", age=64,
        condition="post-operative wound healing", mood="worried",
        background="Second visit for the same concern, feels unheard.",
        concerns=[concern], tasks=["Check wound", "Reassure about healing progress"],
    )
    transcript = [
        {"role": "nurse", "content": "Right, let's have a look at that cannula site."},
        {"role": "patient", "content": "It's still really red and it hurts, is that normal?"},
        {"role": "nurse", "content": "It's fine, just deal with it, it happens to everyone."},
        {"role": "patient", "content": "It's been like this for a week though."},
        {"role": "nurse", "content": "You'll be discharged tomorrow anyway. Any other issues?"},
        {"role": "patient", "content": "No, I suppose not."},
    ]
    candidate_events = [
        CandidateEvent(event="dismissive_response", turn_index=2, evidence_text="It's fine, just deal with it, it happens to everyone."),
        CandidateEvent(event="jargon_used", turn_index=0, evidence_text="cannula site"),
        CandidateEvent(event="closed_question", turn_index=4, evidence_text="Any other issues?"),
    ]
    patient_events = [
        PatientEvent(event="concern_raised", turn_index=1, evidence_text=concern),
    ]
    concern_outcomes = [
        ConcernOutcome(
            concern=concern, final_status="raised", resolved=False,
            history=[{"status": "raised", "turn_index": 1, "cause_event": None}],
        ),
    ]
    state_transitions = [
        StateTransition(field="current_emotion", before="worried", after="worried", cause_event="dismissive_response", turn_index=2),
    ]
    jargon_evidence = [
        JargonEvidence(term="cannula", turn_index=0, evidence_text="cannula site", patient_reaction="It's still really red and it hurts, is that normal?", clarified_afterward=False),
    ]
    session_context = {"pipeline": "legacy", "session_usage_id": 9002, "duration_seconds": 65.0, "interrupted_count": 1}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this (non-Elite) session; intelligibility cannot be judged from transcript text alone.",
                       limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available; fluency cannot be inferred from spelling or word choice.",
                       limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=1,
                       justification="Unexplained clinical jargon (\"cannula site\") used with no lay explanation, and the patient's follow-up question suggests confusion, not comprehension.",
                       evidence_refs=[_ref("jargon_evidence", "cannula", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=2,
                       justification="Grammar itself is accurate throughout; scored on the small available transcript sample only, no structured grammar detector exists.",
                       evidence_refs=[_ref("transcript", "turn_2", 2, LEVEL_L1_DIRECT, "direct")],
                       limitations=["no structured grammar analysis detector available"]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_ASSESSED, level=0,
                       justification="No greeting or introduction; the patient's pain concern is met with an explicit dismissive response (\"just deal with it\") and no acknowledgement of distress follows.",
                       evidence_refs=[_ref("candidate_event", "dismissive_response", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule")]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_ASSESSED, level=0,
                       justification="The patient's concern is raised explicitly (turn 1) and never explored or addressed; the consultation moves straight to discharge logistics instead.",
                       evidence_refs=[_ref("patient_event", "concern_raised", 1, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule")]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing, signposting, or organizing language detected this session -- an evidence gap, not itself proof of disorganization.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_ASSESSED, level=1,
                       justification="Only one closed question used (\"Any other issues?\") to close out the consultation; no open questions, clarification, or summarising detected.",
                       evidence_refs=[_ref("candidate_event", "closed_question", 4, LEVEL_L2_DETERMINISTIC, "deterministic_rule")],
                       limitations=["no D1 active-listening or D4/D5 clarification/summary evidence this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No prior-knowledge check, pacing, reaction-checking, understanding-check, or further-information check detected this session.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_02_weak_overall", "weak_overall",
        "Dismissive, unstructured consultation with an unaddressed concern, unexplained jargon, and no audio evidence -- the floor case.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        concern_outcomes=concern_outcomes, state_transitions=state_transitions, jargon_evidence=jargon_evidence,
        session_context=session_context, audio_evidence=NO_AUDIO, judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 3 -- strong_language_weak_clinical
# ═══════════════════════════════════════════════════════════════════════

def _case_03_strong_language_weak_clinical() -> BenchmarkCase:
    concern = "Will the scar be very noticeable?"
    scenario = _scenario(
        id_=103, title="Fluent but clinically cold consultation", setting="Plastic surgery outpatients",
        difficulty="medium", specialty="plastic surgery", patient_name="Priya", age=34,
        condition="post-operative scar review", mood="self-conscious",
        background="Concerned about visible scarring before returning to work.",
        concerns=[concern], tasks=["Review scar healing", "Address cosmetic concerns"],
    )
    transcript = [
        {"role": "nurse", "content": "The incision has healed as expected given the surgical approach that was used."},
        {"role": "patient", "content": "I'm really worried the scar will be very noticeable at work."},
        {"role": "nurse", "content": "Scarring outcomes vary considerably between individuals and are not something I can predict definitively."},
        {"role": "patient", "content": "I just feel quite self-conscious about it."},
        {"role": "nurse", "content": "You'll need to return in six weeks for a further assessment of the site."},
    ]
    candidate_events = [
        CandidateEvent(event="dismissive_response", turn_index=2, evidence_text="Scarring outcomes vary considerably between individuals and are not something I can predict definitively."),
    ]
    patient_events = [
        PatientEvent(event="concern_raised", turn_index=1, evidence_text=concern),
        PatientEvent(event="emotional_trigger_fired", turn_index=3, evidence_text="feel quite self-conscious"),
    ]
    concern_outcomes = [
        ConcernOutcome(concern=concern, final_status="raised", resolved=False, history=[{"status": "raised", "turn_index": 1, "cause_event": None}]),
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9003, "duration_seconds": 90.0, "interrupted_count": 0}
    audio_evidence = _elite_audio(91.0, 88.0, 98.0)

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=6,
                       justification="Azure overall score 91.0, no problem words; highly intelligible.",
                       evidence_refs=[_ref("pronunciation", "overall_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=6,
                       justification="Fluency score 88.0, completeness 98.0; no disfluency evident.",
                       evidence_refs=[_ref("pronunciation", "fluency_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=5,
                       justification="No jargon; register is formal but plain and understandable throughout.",
                       evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=6,
                       justification="Complex, accurate sentence structures (\"are not something I can predict definitively\") used correctly and consistently.",
                       evidence_refs=[_ref("transcript", "turn_2", 2, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_ASSESSED, level=0,
                       justification="No greeting, and the patient's explicit self-consciousness (turn 3, an emotional-trigger event) receives no acknowledgement at all -- the nurse moves straight to logistics.",
                       evidence_refs=[
                           _ref("candidate_event", "dismissive_response", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("patient_event", "emotional_trigger_fired", 3, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_ASSESSED, level=0,
                       justification="Cosmetic concern raised explicitly (turn 1) and answered with a factually correct but unexplored, unaddressed deflection.",
                       evidence_refs=[_ref("patient_event", "concern_raised", 1, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule")]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language detected this very short session.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No questions of any kind (open, closed, or otherwise) detected this session.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="Follow-up logistics were given but with no prior-knowledge check, pacing, or invitation for questions detected.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_03_strong_language_weak_clinical", "strong_language_weak_clinical",
        "Grammatically excellent, highly intelligible English used with no relationship-building or patient-perspective engagement.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        concern_outcomes=concern_outcomes, session_context=session_context, audio_evidence=audio_evidence,
        judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 4 -- weak_language_strong_clinical
# ═══════════════════════════════════════════════════════════════════════

def _case_04_weak_language_strong_clinical() -> BenchmarkCase:
    concern = "Will I need another operation?"
    scenario = _scenario(
        id_=104, title="Simple English, strong clinical rapport", setting="Medical ward",
        difficulty="easy", specialty="general medicine", patient_name="Ahmed", age=45,
        condition="recovering from infection", mood="scared", background="Limited English proficiency, first hospital stay.",
        concerns=[concern], tasks=["Reassure patient", "Explain treatment plan simply"],
    )
    transcript = [
        {"role": "nurse", "content": "Hello Ahmed, I am nurse Kim. How you feeling today?"},
        {"role": "patient", "content": "I am scared. Will I need operation again?"},
        {"role": "nurse", "content": "I understand you are scared, this is very normal feeling. Let me explain for you."},
        {"role": "patient", "content": "Okay, please."},
        {"role": "nurse", "content": "The infection is getting better with the medicine. Doctor think you will not need operation, but we watch you close."},
        {"role": "patient", "content": "That is good to hear, thank you."},
        {"role": "nurse", "content": "You have understand what I explain? You can ask me anything, no problem."},
        {"role": "patient", "content": "Yes I understand, thank you nurse."},
    ]
    candidate_events = [
        CandidateEvent(event="opening_greeting", turn_index=0, evidence_text="Hello Ahmed, I am nurse Kim"),
        CandidateEvent(event="opening_introduction", turn_index=0, evidence_text="I am nurse Kim"),
        CandidateEvent(event="empathy_acknowledgement", turn_index=2, evidence_text="I understand you are scared, this is very normal feeling"),
        CandidateEvent(event="concern_addressing", turn_index=4, evidence_text="Doctor think you will not need operation, but we watch you close", target_concern=concern),
        CandidateEvent(event="understanding_checked", turn_index=6, evidence_text="You have understand what I explain?"),
        CandidateEvent(event="further_information_check", turn_index=6, evidence_text="You can ask me anything, no problem."),
    ]
    patient_events = [PatientEvent(event="concern_raised", turn_index=1, evidence_text=concern)]
    concern_outcomes = [
        ConcernOutcome(
            concern=concern, final_status="resolved", resolved=True,
            history=[
                {"status": "raised", "turn_index": 1, "cause_event": None},
                {"status": "addressed", "turn_index": 4, "cause_event": "concern_addressing"},
                {"status": "resolved", "turn_index": 5, "cause_event": None},
            ],
            resolved_at_turns=[5],
        ),
    ]
    state_transitions = [
        StateTransition(field="current_emotion", before="scared", after="reassured", cause_event="empathy_acknowledgement", turn_index=2),
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9004, "duration_seconds": 140.0, "interrupted_count": 0}
    audio_evidence = _elite_audio(52.0, 47.0, 80.0, problem_words=[{"word": "operation", "accuracy_score": 40.0}, {"word": "understand", "accuracy_score": 38.0}])

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=2,
                       justification="Azure overall score 52.0 with two flagged problem words; intelligible but requires listener effort at times.",
                       evidence_refs=[_ref("pronunciation", "overall_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=2,
                       justification="Fluency score 47.0; noticeably effortful but the message is always delivered.",
                       evidence_refs=[_ref("pronunciation", "fluency_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=3,
                       justification="Simple, plain register throughout, no jargon; appropriate for the patient even if grammatically imperfect.",
                       evidence_refs=[_ref("transcript", "turn_4", 4, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=2,
                       justification="Frequent article/tense errors (\"How you feeling\", \"Doctor think\", \"You have understand\") throughout, though meaning always stays clear.",
                       evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")],
                       limitations=["no structured grammar analysis detector available; judged from transcript alone"]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="Warm greeting with name and role, explicit empathy for fear, and the patient's fear resolves to reassured immediately after.",
                       evidence_refs=[
                           _ref("candidate_event", "opening_greeting", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "empathy_acknowledgement", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="The operation-fear concern is raised, directly and correctly addressed, and reaches resolved status by the next patient turn.",
                       evidence_refs=[_ref("concern_timeline", f"{concern}::resolved", 5, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule")]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No explicit sequencing or signposting language detected, though the consultation does follow a sensible informal order.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No open/closed questions, clarification, or summarising detected -- the nurse mostly gave information rather than gathered it this session.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_ASSESSED, level=2,
                       justification="Understanding explicitly checked and further questions invited before closing, though no prior-knowledge check preceded the explanation.",
                       evidence_refs=[
                           _ref("candidate_event", "understanding_checked", 6, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "further_information_check", 6, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ],
                       limitations=["no E1 prior-knowledge-check evidence detected this session"]),
        ]

    return build_case(
        "case_04_weak_language_strong_clinical", "weak_language_strong_clinical",
        "Limited-proficiency English (audio-scored low) paired with strong empathy, clear resolution, and good information-giving checks.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        concern_outcomes=concern_outcomes, state_transitions=state_transitions,
        session_context=session_context, audio_evidence=audio_evidence, judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 5 -- excellent_relationship_building
# ═══════════════════════════════════════════════════════════════════════

def _case_05_excellent_relationship_building() -> BenchmarkCase:
    scenario = _scenario(
        id_=105, title="High-anxiety patient, focus on rapport", setting="Emergency department",
        difficulty="medium", specialty="emergency", patient_name="Nina", age=29,
        condition="chest pain under investigation", mood="frightened",
        background="First time in an emergency department, lives alone, fears the worst.",
        concerns=[], tasks=["Build rapport", "Reassure while awaiting test results"],
    )
    transcript = [
        {"role": "nurse", "content": "Hi Nina, I'm Dana, one of the nurses looking after you this evening. I know waiting for these results is hard."},
        {"role": "patient", "content": "I'm terrified something is seriously wrong with my heart."},
        {"role": "nurse", "content": "That fear makes complete sense given what you're going through right now, and it's okay to feel that way."},
        {"role": "patient", "content": "Nobody else has really acknowledged that."},
        {"role": "nurse", "content": "I hear you, and I'm not going to judge you for being scared -- most people would feel exactly the same in your position."},
        {"role": "patient", "content": "Thank you, that actually helps."},
    ]
    candidate_events = [
        CandidateEvent(event="opening_greeting", turn_index=0, evidence_text="Hi Nina, I'm Dana"),
        CandidateEvent(event="opening_introduction", turn_index=0, evidence_text="one of the nurses looking after you this evening"),
        CandidateEvent(event="empathy_acknowledgement", turn_index=0, evidence_text="I know waiting for these results is hard"),
        CandidateEvent(event="attentive_acknowledgement", turn_index=2, evidence_text="That fear makes complete sense"),
        CandidateEvent(event="empathy_acknowledgement", turn_index=2, evidence_text="it's okay to feel that way"),
        CandidateEvent(event="attentive_acknowledgement", turn_index=4, evidence_text="I hear you"),
        CandidateEvent(event="supportive_nonjudgmental", turn_index=4, evidence_text="I'm not going to judge you for being scared -- most people would feel exactly the same"),
    ]
    patient_events = [PatientEvent(event="emotional_trigger_fired", turn_index=1, evidence_text="terrified something is seriously wrong with my heart")]
    state_transitions = [
        StateTransition(field="current_emotion", before="frightened", after="somewhat reassured", cause_event="empathy_acknowledgement", turn_index=4),
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9005, "duration_seconds": 80.0, "interrupted_count": 0}
    audio_evidence = _elite_audio(76.0, 74.0, 92.0)

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Azure overall score 76.0; clearly intelligible with only minor imperfection.",
                       evidence_refs=[_ref("pronunciation", "overall_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Fluency score 74.0; natural pacing throughout the short exchange.",
                       evidence_refs=[_ref("pronunciation", "fluency_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Warm, plain, non-clinical register throughout; no jargon.",
                       evidence_refs=[_ref("transcript", "turn_4", 4, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Accurate, naturally varied phrasing (\"most people would feel exactly the same in your position\").",
                       evidence_refs=[_ref("transcript", "turn_4", 4, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="Textbook A1-A4 coverage in a single short exchange: named greeting and role (A1), attentive acknowledgement twice (A2), explicit non-judgmental framing (A3), and repeated genuine empathy for a named fear (A4), with the patient's own words (\"that actually helps\") confirming impact.",
                       evidence_refs=[
                           _ref("candidate_event", "opening_greeting", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "empathy_acknowledgement", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "supportive_nonjudgmental", 4, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("patient_event", "emotional_trigger_fired", 1, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No formal concern was raised or explored this session -- the scenario has no card-defined concerns and none emerged in the transcript.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="This short rapport-focused exchange has no sequencing or signposting language to evaluate.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No questions were asked in this rapport-focused exchange.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No clinical information was given in this exchange to check understanding of.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_05_excellent_relationship_building", "excellent_relationship_building",
        "Short exchange with dense, high-quality A1-A4 relationship-building evidence; other criteria deliberately have nothing to evaluate.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        state_transitions=state_transitions, session_context=session_context, audio_evidence=audio_evidence,
        judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 6 -- poor_relationship_building
# ═══════════════════════════════════════════════════════════════════════

def _case_06_poor_relationship_building() -> BenchmarkCase:
    scenario = _scenario(
        id_=106, title="Judgmental consultation, missed care", setting="General practice",
        difficulty="medium", specialty="general practice", patient_name="Marcus", age=41,
        condition="poorly controlled diabetes", mood="ashamed",
        background="Has struggled with adherence, feels judged at previous visits.",
        concerns=[], tasks=["Discuss medication adherence"],
    )
    transcript = [
        {"role": "nurse", "content": "Your sugar levels are high again. Have you even been taking your medication properly?"},
        {"role": "patient", "content": "I've been trying, it's just been a really hard few months."},
        {"role": "nurse", "content": "Well if you'd just followed the plan none of this would be happening."},
        {"role": "patient", "content": "..."},
        {"role": "nurse", "content": "Let's get your bloods done."},
    ]
    candidate_events = [
        CandidateEvent(event="potentially_judgmental", turn_index=0, evidence_text="Have you even been taking your medication properly?"),
        CandidateEvent(event="potentially_judgmental", turn_index=2, evidence_text="Well if you'd just followed the plan none of this would be happening."),
        CandidateEvent(event="dismissive_response", turn_index=2, evidence_text="Well if you'd just followed the plan none of this would be happening."),
    ]
    patient_events = [PatientEvent(event="emotional_trigger_fired", turn_index=1, evidence_text="really hard few months")]
    state_transitions = [
        StateTransition(field="current_emotion", before="ashamed", after="withdrawn", cause_event="dismissive_response", turn_index=2),
    ]
    session_context = {"pipeline": "legacy", "session_usage_id": 9006, "duration_seconds": 45.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=1,
                       justification="Accusatory, blaming phrasing (\"Have you even\", \"if you'd just followed the plan\") is not appropriate register for a patient already ashamed about adherence.",
                       evidence_refs=[_ref("transcript", "turn_2", 2, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=3,
                       justification="Grammar itself is accurate; scored on the small available sample, no structured detector exists.",
                       evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_ASSESSED, level=0,
                       justification="No greeting; two separate judgmental remarks about adherence, and the patient's admission of a hard few months (an emotional-trigger event) is met with blame rather than acknowledgement, visibly worsening the patient's emotional state.",
                       evidence_refs=[
                           _ref("candidate_event", "potentially_judgmental", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "potentially_judgmental", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("state_transition", "current_emotion", 2, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No concern was raised or explored -- the patient's silence at turn 3 is notable but this indicator has no dedicated detector.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language detected in this brief, confrontational exchange.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="The opening line is phrased as a question but reads as accusatory rather than information-seeking; no detector-recognised open/closed question form present.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No information was given about the diabetes management plan itself in this exchange.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_06_poor_relationship_building", "poor_relationship_building",
        "Judgmental, blaming tone toward a patient already ashamed about adherence; emotional state visibly worsens.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        state_transitions=state_transitions, session_context=session_context, audio_evidence=NO_AUDIO,
        judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 7 -- poor_structure_and_questioning
# ═══════════════════════════════════════════════════════════════════════

def _case_07_poor_structure_and_questioning() -> BenchmarkCase:
    scenario = _scenario(
        id_=107, title="Leading and compound questions, no structure", setting="Pre-op assessment",
        difficulty="medium", specialty="surgical", patient_name="Lena", age=52,
        condition="pre-operative assessment", mood="neutral", background="Routine pre-op checklist visit.",
        concerns=[], tasks=["Complete pre-operative symptom check"],
    )
    transcript = [
        {"role": "nurse", "content": "You don't have any pain, nausea, or dizziness, do you?"},
        {"role": "patient", "content": "Well, I do get a bit dizzy sometimes."},
        {"role": "nurse", "content": "But that's nothing serious, right, just tiredness?"},
        {"role": "patient", "content": "I suppose so."},
        {"role": "nurse", "content": "Have you been eating and sleeping fine, and taking your usual tablets?"},
        {"role": "patient", "content": "Yes, mostly."},
    ]
    candidate_events = [
        CandidateEvent(event="compound_question", turn_index=0, evidence_text="You don't have any pain, nausea, or dizziness, do you?"),
        CandidateEvent(event="leading_question", turn_index=0, evidence_text="do you?"),
        CandidateEvent(event="leading_question", turn_index=2, evidence_text="But that's nothing serious, right, just tiredness?"),
        CandidateEvent(event="compound_question", turn_index=4, evidence_text="Have you been eating and sleeping fine, and taking your usual tablets?"),
        CandidateEvent(event="closed_question", turn_index=4, evidence_text="Have you been eating and sleeping fine"),
    ]
    session_context = {"pipeline": "legacy", "session_usage_id": 9007, "duration_seconds": 70.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=3,
                       justification="No jargon, but the leading framing (\"nothing serious, right?\") pressures the patient toward a particular answer rather than inviting an honest one.",
                       evidence_refs=[_ref("transcript", "turn_2", 2, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Grammar is accurate throughout; scored from the transcript sample alone.",
                       evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No greeting, empathy, or non-judgmental-framing evidence detected this session -- a neutral, task-focused exchange with nothing to evaluate for rapport.",
                       limitations=["no_indicator_level_detector: A1-A4 all empty this session"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="The patient's dizziness (turn 1) is a genuine cue that is immediately minimised (turn 2) rather than explored, but no dedicated cue-response detector fired here.",
                       limitations=["no_indicator_level_detector: no concern-exploration evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing, signposting, or organizing language used across the checklist-style exchange.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_ASSESSED, level=0,
                       justification="Every question is either compound (three symptoms bundled into one) or leading (\"do you?\", \"right?\") -- exactly the D3 anti-pattern -- and the dizziness the patient does disclose is talked past rather than clarified or summarised back.",
                       evidence_refs=[
                           _ref("candidate_event", "compound_question", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "leading_question", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "leading_question", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "compound_question", 4, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ],
                       limitations=["no D1 active-listening or D4/D5 clarification/summary evidence this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No clinical information was given to the patient in this pre-op checklist exchange.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_07_poor_structure_and_questioning", "poor_structure_and_questioning",
        "Compound and leading questions dominate; no sequencing/signposting anywhere -- tests both C-criteria and D3 together.",
        scenario, transcript, candidate_events=candidate_events, session_context=session_context,
        audio_evidence=NO_AUDIO, judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 8 -- information_giving_all_gaps (orthogonality stress test)
# ═══════════════════════════════════════════════════════════════════════

def _case_08_information_giving_all_gaps() -> BenchmarkCase:
    scenario = _scenario(
        id_=108, title="Information given with zero E-indicator technique", setting="Discharge planning",
        difficulty="medium", specialty="general medicine", patient_name="Robert", age=70,
        condition="ready for discharge", mood="neutral", background="Routine discharge.",
        concerns=[], tasks=["Explain discharge medication"],
    )
    transcript = [
        {"role": "nurse", "content": "You're being discharged today. Take two tablets of amoxicillin three times a day for one week, and paracetamol as needed for pain."},
        {"role": "patient", "content": "Okay."},
        {"role": "nurse", "content": "A follow-up letter will be sent to your GP."},
        {"role": "patient", "content": "Alright."},
    ]

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=2,
                       justification="Drug names given without lay explanation (\"amoxicillin\") for an elderly patient with no confirmation of comprehension.",
                       evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Grammatically accurate throughout; scored from the transcript sample alone.",
                       evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No greeting or interpersonal evidence detected in this brief, purely transactional exchange.",
                       limitations=["no_indicator_level_detector: A1-A4 all empty this session"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No concern was raised or explored this session.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language detected.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No questions were asked in this purely instructional exchange.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification=(
                           "Medication and follow-up information IS given, but none of the five information-giving "
                           "indicator behaviours (prior-knowledge check, paced delivery with reaction-checking, "
                           "invitation to contribute, understanding check, or further-information check) fired this "
                           "session. This is a deliberate calibration case: the content is delivered, but there is no "
                           "detector evidence of HOW it was delivered, so this must read as an evidence gap, not as an "
                           "earned Ineffective (0) -- collapsing the two would be the exact status/level conflation "
                           "this benchmark exists to catch."
                       ),
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_08_information_giving_all_gaps", "information_giving_all_gaps",
        "Information IS delivered but zero E1-E5 technique markers fire -- direct test of status=limited_evidence vs level=0 conflation.",
        scenario, transcript, session_context={"pipeline": "legacy", "session_usage_id": 9008, "duration_seconds": 40.0, "interrupted_count": 0},
        audio_evidence=NO_AUDIO, judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 9 -- concern_resolved_clean
# ═══════════════════════════════════════════════════════════════════════

def _case_09_concern_resolved_clean() -> BenchmarkCase:
    concern = "Is it normal to feel this tired after chemotherapy?"
    scenario = _scenario(
        id_=109, title="Single concern, cleanly resolved", setting="Oncology day unit",
        difficulty="easy", specialty="oncology", patient_name="Grace", age=61,
        condition="on chemotherapy", mood="tired", background="Third cycle of chemotherapy.",
        concerns=[concern], tasks=["Address fatigue concern"],
    )
    transcript = [
        {"role": "patient", "content": "Is it normal to feel this tired after chemotherapy?"},
        {"role": "nurse", "content": "Yes, that's a very common and expected side effect at this stage of treatment. It should ease gradually over the next week."},
        {"role": "patient", "content": "Oh good, I was worried something else was wrong."},
    ]
    candidate_events = [
        CandidateEvent(event="concern_addressing", turn_index=1, evidence_text="that's a very common and expected side effect at this stage of treatment", target_concern=concern),
    ]
    patient_events = [PatientEvent(event="concern_raised", turn_index=0, evidence_text=concern)]
    concern_outcomes = [
        ConcernOutcome(
            concern=concern, final_status="resolved", resolved=True,
            history=[
                {"status": "raised", "turn_index": 0, "cause_event": None},
                {"status": "addressed", "turn_index": 1, "cause_event": "concern_addressing"},
                {"status": "resolved", "turn_index": 2, "cause_event": None},
            ],
            resolved_at_turns=[2],
        ),
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9009, "duration_seconds": 30.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Plain, reassuring register with no jargon.",
                       evidence_refs=[_ref("transcript", "turn_1", 1, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Accurate, natural phrasing throughout.",
                       evidence_refs=[_ref("transcript", "turn_1", 1, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No greeting or empathy-specific evidence in this very short, already-in-progress exchange.",
                       limitations=["no_indicator_level_detector: A1-A4 all empty this session"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="The patient's fatigue concern is raised, directly and reassuringly addressed with a clear clinical explanation, and reaches resolved by the very next turn -- a clean, complete B1-B3 lifecycle.",
                       evidence_refs=[
                           _ref("patient_event", "concern_raised", 0, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                           _ref("candidate_event", "concern_addressing", 1, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("concern_timeline", f"{concern}::resolved", 2, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language in this three-turn exchange.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No questions were asked by the nurse in this exchange -- the patient initiated it.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="Clinical information was given as part of addressing the concern, but no separate E1-E5 technique markers fired.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_09_concern_resolved_clean", "concern_resolved",
        "Minimal, clean patient-perspective lifecycle: raised, addressed, resolved -- baseline reference for the B-criterion.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        concern_outcomes=concern_outcomes, session_context=session_context, audio_evidence=NO_AUDIO,
        judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 10 -- concern_reopened
# ═══════════════════════════════════════════════════════════════════════

def _case_10_concern_reopened() -> BenchmarkCase:
    concern = "Will the medication make me drowsy at work?"
    scenario = _scenario(
        id_=110, title="Concern resolved then reopened", setting="Community mental health clinic",
        difficulty="medium", specialty="mental health", patient_name="Tom", age=38,
        condition="starting new medication", mood="anxious", background="Concerned about work performance.",
        concerns=[concern], tasks=["Discuss medication side effects"],
    )
    transcript = [
        {"role": "patient", "content": "Will this medication make me drowsy at work?"},
        {"role": "nurse", "content": "Most people don't experience significant drowsiness at this dose, so you should be fine."},
        {"role": "patient", "content": "Okay, that's reassuring."},
        {"role": "nurse", "content": "Let's also talk about how to take it with food."},
        {"role": "patient", "content": "Actually wait -- my colleague said hers made her really sleepy for the first week. Are you sure I'll be okay driving to work?"},
        {"role": "nurse", "content": "That's a fair point to raise again -- individual reactions do vary, so let's be cautious: avoid driving for the first few days and monitor how you feel."},
    ]
    candidate_events = [
        CandidateEvent(event="concern_addressing", turn_index=1, evidence_text="Most people don't experience significant drowsiness at this dose", target_concern=concern),
        CandidateEvent(event="concern_addressing", turn_index=5, evidence_text="let's be cautious: avoid driving for the first few days and monitor how you feel", target_concern=concern),
    ]
    patient_events = [
        PatientEvent(event="concern_raised", turn_index=0, evidence_text=concern),
        PatientEvent(event="concern_raised", turn_index=4, evidence_text="Are you sure I'll be okay driving to work?"),
    ]
    concern_outcomes = [
        ConcernOutcome(
            concern=concern, final_status="addressed", resolved=False,
            history=[
                {"status": "raised", "turn_index": 0, "cause_event": None},
                {"status": "addressed", "turn_index": 1, "cause_event": "concern_addressing"},
                {"status": "resolved", "turn_index": 2, "cause_event": None},
                {"status": "raised", "turn_index": 4, "cause_event": None},
                {"status": "addressed", "turn_index": 5, "cause_event": "concern_addressing"},
            ],
            resolved_at_turns=[2],
            reopened_events=[{"turn_index": 4, "from_status": "resolved", "to_status": "raised", "reason": "my colleague said hers made her really sleepy for the first week"}],
        ),
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9010, "duration_seconds": 100.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Plain, reassuring register with no jargon throughout.",
                       evidence_refs=[_ref("transcript", "turn_5", 5, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Accurate, natural phrasing throughout.",
                       evidence_refs=[_ref("transcript", "turn_5", 5, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No greeting, empathy, or non-judgmental-framing evidence detected this session; the respectful handling of the reopened concern (turn 5) is B-criterion evidence, not A1-A4 evidence.",
                       limitations=["no_indicator_level_detector: A1/A3/A4 empty; A2 has only a zero interrupted_count signal this session"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_ASSESSED, level=2,
                       justification=(
                           "The drowsiness concern was resolved once (turn 2) but genuinely reopened by new information "
                           "the patient introduced (turn 4) -- the reopened_events record shows this explicitly. The "
                           "second addressing (turn 5) is more cautious and appropriately adjusted (advising against "
                           "driving) rather than just repeating the first answer, but the concern's FINAL status is "
                           "'addressed', not 'resolved' -- this must not be read as a failure of the first response, "
                           "which was reasonable given the information available at the time."
                       ),
                       evidence_refs=[
                           _ref("concern_timeline", f"{concern}::resolved", 2, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                           _ref("concern_timeline", f"{concern}::raised", 4, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                           _ref("concern_timeline", f"{concern}::addressed", 5, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language detected this session.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No questions were asked by the nurse this session.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="Information was given as part of addressing the concern, but no separate E1-E5 technique markers fired.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_10_concern_reopened", "concern_reopened",
        "A concern reaches resolved, then is genuinely reopened by new patient information -- tests reopened_events handling.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        concern_outcomes=concern_outcomes, session_context=session_context, audio_evidence=NO_AUDIO,
        judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 11 -- multiple_concerns_one_ignored
# ═══════════════════════════════════════════════════════════════════════

def _case_11_multiple_concerns_one_ignored() -> BenchmarkCase:
    concern_a = "When can I go back to playing sport?"
    concern_b = "Will this leave a permanent scar?"
    scenario = _scenario(
        id_=111, title="Two concerns, one answered, one dropped", setting="Sports medicine clinic",
        difficulty="medium", specialty="sports medicine", patient_name="Kayla", age=22,
        condition="post-operative knee surgery", mood="eager", background="Competitive athlete.",
        concerns=[concern_a, concern_b], tasks=["Discuss return to sport", "Address cosmetic concerns"],
    )
    transcript = [
        {"role": "patient", "content": "When can I go back to playing sport? And will this leave a permanent scar?"},
        {"role": "nurse", "content": "You can expect to return to light training around 8 weeks, with full competitive play by around 4 months, depending on your physio progress."},
        {"role": "patient", "content": "That's helpful, thank you."},
        {"role": "nurse", "content": "Let's book your first physio appointment now."},
    ]
    candidate_events = [
        CandidateEvent(event="concern_addressing", turn_index=1, evidence_text="return to light training around 8 weeks, with full competitive play by around 4 months", target_concern=concern_a),
    ]
    patient_events = [
        PatientEvent(event="concern_raised", turn_index=0, evidence_text=concern_a),
        PatientEvent(event="concern_raised", turn_index=0, evidence_text=concern_b),
    ]
    concern_outcomes = [
        ConcernOutcome(
            concern=concern_a, final_status="resolved", resolved=True,
            history=[
                {"status": "raised", "turn_index": 0, "cause_event": None},
                {"status": "addressed", "turn_index": 1, "cause_event": "concern_addressing"},
                {"status": "resolved", "turn_index": 2, "cause_event": None},
            ],
            resolved_at_turns=[2],
        ),
        ConcernOutcome(concern=concern_b, final_status="raised", resolved=False, history=[{"status": "raised", "turn_index": 0, "cause_event": None}]),
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9011, "duration_seconds": 55.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Plain register, no jargon.", evidence_refs=[_ref("transcript", "turn_1", 1, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Accurate, well-structured phrasing.", evidence_refs=[_ref("transcript", "turn_1", 1, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No greeting or empathy-specific evidence in this brief, task-focused exchange.",
                       limitations=["no_indicator_level_detector: A1-A4 all empty this session"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_ASSESSED, level=1,
                       justification=(
                           "Two concerns were raised in the same patient turn. The sport-return concern was answered "
                           "thoroughly and reached resolved. The scarring concern received no acknowledgement at all "
                           "and its final status remains 'raised' -- the consultation moves straight to booking physio. "
                           "One well-handled concern does not offset one entirely dropped concern; the criterion is "
                           "judged on the complete concern set, not the better half of it."
                       ),
                       evidence_refs=[
                           _ref("patient_event", "concern_raised", 0, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                           _ref("concern_timeline", f"{concern_a}::resolved", 2, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ],
                       limitations=[f"'{concern_b}' has no addressing/resolution evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language detected this session.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No questions asked by the nurse this session.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="Timeline information was given as part of addressing one concern, but no separate E1-E5 technique markers fired.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_11_multiple_concerns_one_ignored", "multiple_concerns_one_ignored",
        "Patient raises two concerns in one turn; one is answered well, the other is silently dropped.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        concern_outcomes=concern_outcomes, session_context=session_context, audio_evidence=NO_AUDIO,
        judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 12 -- conflicting_evidence (precedence-resolvable AND genuinely unresolved)
# ═══════════════════════════════════════════════════════════════════════

def _case_12_conflicting_evidence() -> BenchmarkCase:
    scenario = _scenario(
        id_=112, title="Detectors disagree about the same turns", setting="Rehabilitation ward",
        difficulty="hard", specialty="rehabilitation", patient_name="Diane", age=55,
        condition="stroke rehabilitation", mood="frustrated", background="Slow progress is causing frustration.",
        concerns=[], tasks=["Respond to frustration about slow progress"],
    )
    transcript = [
        {"role": "patient", "content": "I've been doing these exercises for weeks and I feel no better at all."},
        {"role": "nurse", "content": "Just deal with it, progress takes time and there's nothing more I can do about that."},
        {"role": "patient", "content": "That's easy for you to say."},
        {"role": "nurse", "content": "I understand this is frustrating, and it says nothing about your effort -- recovery timelines vary a lot between patients."},
    ]
    # Turn 1: deterministic dismissive_response and a semantic-source attentive_acknowledgement
    # disagree about the SAME utterance -- resolvable via the L1/L2 > L3 precedence rule
    # (SHADOW_EXAMINER_DESIGN.md section 11): trust the deterministic dismissive-language
    # detection over the semantic classifier's reading.
    #
    # Turn 3: two semantic-source events (potentially_judgmental vs supportive_nonjudgmental)
    # disagree about the SAME utterance with NO deterministic evidence to arbitrate between
    # them -- the genuinely-unresolvable case the design doc's escape hatch exists for.
    candidate_events = [
        CandidateEvent(event="dismissive_response", turn_index=1, evidence_text="Just deal with it, progress takes time and there's nothing more I can do about that.", source=SOURCE_DETERMINISTIC),
        CandidateEvent(event="attentive_acknowledgement", turn_index=1, evidence_text="Just deal with it, progress takes time and there's nothing more I can do about that.", source=SOURCE_SEMANTIC),
        CandidateEvent(event="supportive_nonjudgmental", turn_index=3, evidence_text="it says nothing about your effort", source=SOURCE_SEMANTIC),
        CandidateEvent(event="potentially_judgmental", turn_index=3, evidence_text="it says nothing about your effort", source=SOURCE_SEMANTIC),
    ]
    patient_events = [PatientEvent(event="emotional_trigger_fired", turn_index=0, evidence_text="feel no better at all")]
    session_context = {"pipeline": "realtime", "session_usage_id": 9012, "duration_seconds": 60.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=2,
                       justification="No jargon, but the turn-1 phrasing is dismissive in register regardless of how it is later classified.",
                       evidence_refs=[_ref("transcript", "turn_1", 1, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Grammar itself is accurate throughout.", evidence_refs=[_ref("transcript", "turn_3", 3, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_EVIDENCE_CONFLICT_UNRESOLVED,
                       justification=(
                           "Two separate turns carry contradictory classifications of the same utterance. At turn 1, a "
                           "deterministic detector flags dismissive_response while a semantic classifier flagged the "
                           "identical line as attentive_acknowledgement -- per evidence-hierarchy precedence (L2 "
                           "deterministic outranks L3 semantic) that one alone would resolve to a dismissive reading. "
                           "But at turn 3, two semantic signals disagree about the same sentence -- supportive_"
                           "nonjudgmental vs potentially_judgmental -- with no deterministic or direct-transcript "
                           "signal available to arbitrate (both are L3_semantic, so precedence does not apply). "
                           "Whether turn 3 reads as a genuine repair attempt or a further minimisation materially "
                           "changes the overall criterion level, so no single defensible level can be committed to "
                           "without resolving it; a human OET reviewer would need tone/context neither classifier "
                           "captured."
                       ),
                       evidence_refs=[
                           _ref("candidate_event", "dismissive_response", 1, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "attentive_acknowledgement", 1, LEVEL_L3_SEMANTIC, "semantic_model"),
                           _ref("candidate_event", "supportive_nonjudgmental", 3, LEVEL_L3_SEMANTIC, "semantic_model"),
                           _ref("candidate_event", "potentially_judgmental", 3, LEVEL_L3_SEMANTIC, "semantic_model"),
                       ],
                       limitations=["turn 1 resolves via evidence-hierarchy precedence; turn 3 does not, and blocks a defensible overall level"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No concern was raised, explored, or addressed in this exchange -- it is entirely about the patient's frustration with progress, not a specific concern with a lifecycle to judge.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language detected this session.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No questions asked by the nurse this session.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No structured information-giving technique markers fired this session.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_12_conflicting_evidence", "conflicting_evidence",
        "Deterministic vs semantic evidence disagree about the same turn twice: once resolvable by precedence, once genuinely unresolved.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        session_context=session_context, audio_evidence=NO_AUDIO, judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 13 -- minimal_very_short_consultation
# ═══════════════════════════════════════════════════════════════════════

def _case_13_minimal_consultation() -> BenchmarkCase:
    scenario = _scenario(
        id_=113, title="Bare two-turn exchange", setting="Corridor, informal", difficulty="easy",
        specialty="general", patient_name="Unnamed", age=0, condition="unspecified", mood="neutral",
        background="", concerns=[], tasks=[],
    )
    transcript = [
        {"role": "nurse", "content": "Hi."},
        {"role": "patient", "content": "Hi."},
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9013, "duration_seconds": 4.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence, and even if there were, a single-word exchange is too short to judge acoustic intelligibility.",
                       limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence, and a single word carries no fluency signal in any case.",
                       limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="\"Hi\" alone is too minimal a sample to judge register or lexical appropriateness against.",
                       limitations=["sample too short to support a defensible judgement despite structural PARTIAL evidence_quality"]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="A single greeting word contains no grammatical structure to evaluate.",
                       limitations=["sample too short to support a defensible judgement despite structural PARTIAL evidence_quality"]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="A bare \"Hi\" with no name, role, or purpose does not meet the bar for a scored A1-A4 judgement; there is nothing else in the transcript to weigh.",
                       limitations=["no_indicator_level_detector: A1-A4 all empty this session"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No concern was raised or explored in this two-word exchange.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="A two-turn exchange has no structure to sequence or signpost.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No questions were asked in this exchange.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No information was given in this exchange.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_13_minimal_consultation", "minimal_very_short_consultation",
        "A two-turn, two-word consultation -- almost every criterion must correctly land on limited_evidence, not a low score.",
        scenario, transcript, session_context=session_context, audio_evidence=NO_AUDIO, judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 14 -- borderline_clinical_3_vs_2 (relationship_building)
# ═══════════════════════════════════════════════════════════════════════
# Cases 14-18: adjacent-level judgement calls. Each reference judgement below
# explicitly names the adjacent level a reasonable reviewer could pick
# instead, and why this module's author picked the level it did -- these are
# calibration_critical precisely because two careful reviewers could land on
# different sides of the boundary; the reference is one defensible reading,
# never an objectively correct score (see module docstring).

def _case_14_borderline_clinical_3_vs_2() -> BenchmarkCase:
    scenario = _scenario(
        id_=114, title="Postnatal ward, feeding support", setting="Postnatal ward", difficulty="medium",
        specialty="maternity", patient_name="Mia", age=27, condition="day 1 post-partum, breastfeeding difficulty",
        mood="exhausted", background="First baby, struggling to establish feeding, feeling like she's failing.",
        concerns=[], tasks=["Support with breastfeeding"],
    )
    transcript = [
        {"role": "nurse", "content": "Hello Mia, I'm nurse Priya, I'll be helping you with feeding today. Is now an alright time to chat?"},
        {"role": "patient", "content": "Yes, though I'm exhausted and worried I'm doing this all wrong."},
        {"role": "nurse", "content": "That's a lot to carry after such a big change, and feeling that way is completely understandable."},
        {"role": "patient", "content": "The baby won't latch properly and I don't know what I'm doing."},
        {"role": "nurse", "content": "Okay."},
        {"role": "patient", "content": "It's frustrating."},
        {"role": "nurse", "content": "Let's have a look together and see what might help."},
    ]
    candidate_events = [
        CandidateEvent(event="opening_greeting", turn_index=0, evidence_text="Hello Mia, I'm nurse Priya"),
        CandidateEvent(event="opening_introduction", turn_index=0, evidence_text="I'm nurse Priya"),
        CandidateEvent(event="opening_purpose_setting", turn_index=0, evidence_text="I'll be helping you with feeding today"),
        CandidateEvent(event="empathy_acknowledgement", turn_index=2, evidence_text="feeling that way is completely understandable"),
        CandidateEvent(event="attentive_acknowledgement_uncertain", turn_index=4, evidence_text="Okay.", source=SOURCE_SEMANTIC),
    ]
    patient_events = [
        PatientEvent(event="emotional_trigger_fired", turn_index=1, evidence_text="exhausted and worried I'm doing this all wrong"),
        PatientEvent(event="emotional_trigger_fired", turn_index=5, evidence_text="It's frustrating"),
    ]
    state_transitions = [
        StateTransition(field="current_emotion", before="anxious", after="mildly reassured", cause_event="empathy_acknowledgement", turn_index=2),
        StateTransition(field="current_emotion", before="mildly reassured", after="frustrated", cause_event=None, turn_index=5),
    ]
    session_context = {"pipeline": "legacy", "session_usage_id": 9014, "duration_seconds": 60.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Plain, warm register throughout, no jargon.",
                       evidence_refs=[_ref("transcript", "turn_2", 2, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Accurate, natural phrasing throughout.",
                       evidence_refs=[_ref("transcript", "turn_2", 2, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_ASSESSED, level=2,
                       justification=(
                           "BORDERLINE 3 vs 2: the opening (name, role, purpose) is a full, clean A1, and the turn-2 "
                           "empathy response is genuine and well-targeted at the patient's stated worry -- a reviewer "
                           "weighting that strong start heavily could reasonably score this Adept use (3). This "
                           "reference scores Competent use (2) instead because the only other candidate A2 evidence "
                           "is a single bare 'Okay' at turn 4 (flagged uncertain by the classifier itself), and the "
                           "patient's second, more frustrated disclosure at turn 5 receives no further empathetic "
                           "response at all before the nurse moves on -- consistent excellent attentiveness across "
                           "the whole exchange is what would justify a 3, and it isn't quite sustained here. This is "
                           "a genuine judgement call, not an objectively correct answer; a careful reviewer scoring "
                           "3 instead would not be wrong."
                       ),
                       evidence_refs=[
                           _ref("candidate_event", "opening_greeting", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "empathy_acknowledgement", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "attentive_acknowledgement_uncertain", 4, LEVEL_L3_SEMANTIC, "semantic_model"),
                           _ref("state_transition", "current_emotion", 5, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ],
                       limitations=["borderline 3-vs-2 call; see justification for the case for scoring 3 instead"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="The latch difficulty is an emotional disclosure handled under relationship-building, not a scenario-defined concern with its own raised/addressed/resolved lifecycle this session.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language detected this session.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No open/closed questions detected this session.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No clinical information was given in this brief exchange.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_14_borderline_clinical_3_vs_2", "borderline_clinical_3_vs_2",
        "Strong opening and one genuine empathy response, but thin follow-through on a second disclosure -- an adjacent 3-vs-2 relationship-building call.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        state_transitions=state_transitions, session_context=session_context, audio_evidence=NO_AUDIO,
        tags=["borderline", "adjacent_level", "calibration_critical", "clinical_3_vs_2"], judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 15 -- borderline_clinical_2_vs_1 (providing_structure)
# ═══════════════════════════════════════════════════════════════════════

def _case_15_borderline_clinical_2_vs_1() -> BenchmarkCase:
    scenario = _scenario(
        id_=115, title="Diabetes medication review", setting="Diabetes clinic", difficulty="medium",
        specialty="endocrine", patient_name="Fatima", age=48, condition="type 2 diabetes, dose adjustment",
        mood="neutral", background="Routine review of insulin dosing.",
        concerns=[], tasks=["Review blood sugar readings", "Explain new insulin dose"],
    )
    transcript = [
        {"role": "nurse", "content": "Right, so today we need to go through your blood sugar readings and then your new insulin dose."},
        {"role": "patient", "content": "Okay."},
        {"role": "nurse", "content": "Your readings have been a bit up and down this week."},
        {"role": "patient", "content": "Yes, I noticed that too."},
        {"role": "nurse", "content": "So, moving on, your new dose is 12 units in the morning."},
        {"role": "patient", "content": "Alright, and in the evening?"},
        {"role": "nurse", "content": "We'll get to that in a second."},
        {"role": "patient", "content": "Okay."},
        {"role": "nurse", "content": "Evening dose stays the same, 8 units."},
    ]
    candidate_events = [
        CandidateEvent(event="consultation_sequence_marker_partial", turn_index=0, evidence_text="today we need to go through your blood sugar readings and then your new insulin dose"),
        CandidateEvent(event="topic_transition_detected", turn_index=4, evidence_text="So, moving on"),
        CandidateEvent(event="organization_marker_partial", turn_index=6, evidence_text="We'll get to that in a second"),
    ]
    session_context = {"pipeline": "legacy", "session_usage_id": 9015, "duration_seconds": 75.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Plain register, no jargon.", evidence_refs=[_ref("transcript", "turn_4", 4, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Accurate throughout.", evidence_refs=[_ref("transcript", "turn_4", 4, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No greeting or empathy evidence detected in this task-focused exchange.",
                       limitations=["no_indicator_level_detector: A1-A4 all empty this session"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No concern was raised or explored this session.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_ASSESSED, level=1,
                       justification=(
                           "BORDERLINE 2 vs 1: all three C-indicators have SOME evidence -- an upfront two-item "
                           "sequence announcement (C1, though only 'partial' quality, not a fuller multi-step "
                           "sequence), an explicit topic-transition signpost 'moving on' (C2), and a deferral phrase "
                           "'we'll get to that in a second' offered as informal organisation (C3, also only "
                           "'partial'). A reviewer crediting genuine presence across all three sub-indicators could "
                           "reasonably call this Competent use (2). This reference scores Partially effective use "
                           "(1) because none of the three pieces is a full-strength example -- the sequencing "
                           "covers only two items instead of the full session, and the C3 evidence is a promise to "
                           "organise later rather than an actual organising technique in the moment. Reasonable "
                           "evaluators could differ on how much partial-quality evidence across three indicators "
                           "should be worth relative to one gap."
                       ),
                       evidence_refs=[
                           _ref("candidate_event", "consultation_sequence_marker_partial", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "topic_transition_detected", 4, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "organization_marker_partial", 6, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ],
                       limitations=["borderline 2-vs-1 call; see justification for the case for scoring 2 instead"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No open/closed questions were asked by the nurse this session.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="Dose information was given, but no E1-E5 technique markers fired this session.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_15_borderline_clinical_2_vs_1", "borderline_clinical_2_vs_1",
        "Sequencing, signposting, and organisation are all attempted but each only partially -- an adjacent 2-vs-1 providing-structure call.",
        scenario, transcript, candidate_events=candidate_events, session_context=session_context,
        audio_evidence=NO_AUDIO, tags=["borderline", "adjacent_level", "calibration_critical", "clinical_2_vs_1"],
        judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 16 -- borderline_clinical_1_vs_0 (information_gathering)
# ═══════════════════════════════════════════════════════════════════════

def _case_16_borderline_clinical_1_vs_0() -> BenchmarkCase:
    scenario = _scenario(
        id_=116, title="Phone triage, mixed questioning technique", setting="Telephone triage", difficulty="hard",
        specialty="general practice", patient_name="Walter", age=67, condition="reported mild chest tightness",
        mood="neutral", background="Called in about occasional chest tightness after exertion.",
        concerns=[], tasks=["Triage reported symptoms"],
    )
    transcript = [
        {"role": "nurse", "content": "You haven't had any chest pain or shortness of breath, have you?"},
        {"role": "patient", "content": "No, not really."},
        {"role": "nurse", "content": "And you're managing okay at home, taking all your tablets, eating fine?"},
        {"role": "patient", "content": "I think so."},
        {"role": "nurse", "content": "Can you tell me more about what 'not really' chest pain means?"},
        {"role": "patient", "content": "Sometimes a slight tightness after stairs."},
        {"role": "nurse", "content": "That's just normal, right?"},
        {"role": "patient", "content": "Maybe."},
    ]
    candidate_events = [
        CandidateEvent(event="leading_question", turn_index=0, evidence_text="have you?"),
        CandidateEvent(event="compound_question", turn_index=2, evidence_text="managing okay at home, taking all your tablets, eating fine?"),
        CandidateEvent(event="open_question", turn_index=4, evidence_text="Can you tell me more about what 'not really' chest pain means?"),
        CandidateEvent(event="clarification_request", turn_index=4, evidence_text="Can you tell me more about what 'not really' chest pain means?", related_patient_turns=[1]),
        CandidateEvent(event="leading_question", turn_index=6, evidence_text="That's just normal, right?"),
    ]
    session_context = {"pipeline": "legacy", "session_usage_id": 9016, "duration_seconds": 65.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=3,
                       justification="No jargon, but the leading framing ('that's just normal, right?') pressures a particular answer.",
                       evidence_refs=[_ref("transcript", "turn_6", 6, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Grammar is accurate throughout.", evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No greeting or empathy evidence detected this session.",
                       limitations=["no_indicator_level_detector: A1-A4 all empty this session"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No formal concern lifecycle this session; the chest-tightness disclosure is D-criterion evidence, not a scenario concern.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language detected this session.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_ASSESSED, level=0,
                       justification=(
                           "BORDERLINE 1 vs 0: turn 4 is a genuine, well-formed open question that also functions as "
                           "a D4 clarification of the patient's vague 'not really' -- real technique, and it does "
                           "surface a clinically relevant detail (tightness after stairs). A reviewer weighting that "
                           "one strong moment could reasonably call this Partially effective use (1). This reference "
                           "scores Ineffective use (0) instead because the very next question (turn 6) immediately "
                           "reframes that new disclosure as 'just normal, right?' -- a leading question that "
                           "pressures the patient back toward minimising the symptom they had just been drawn out "
                           "on, on top of the leading/compound questions bracketing the exchange at turns 0 and 2. "
                           "The single good moment is undone by what follows it rather than built on; a careful "
                           "reviewer scoring 1 to credit the open/clarifying technique on its own terms would not be "
                           "wrong."
                       ),
                       evidence_refs=[
                           _ref("candidate_event", "leading_question", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "compound_question", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "open_question", 4, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "clarification_request", 4, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "leading_question", 6, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ],
                       limitations=["borderline 1-vs-0 call; see justification for the case for scoring 1 instead"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No information was given to the patient in this triage exchange.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_16_borderline_clinical_1_vs_0", "borderline_clinical_1_vs_0",
        "One genuine open/clarifying question surrounded by leading and compound questions that undercut it -- an adjacent 1-vs-0 information-gathering call.",
        scenario, transcript, candidate_events=candidate_events, session_context=session_context,
        audio_evidence=NO_AUDIO, tags=["borderline", "adjacent_level", "calibration_critical", "clinical_1_vs_0"],
        judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 17 -- borderline_linguistic_5_vs_4 (intelligibility)
# ═══════════════════════════════════════════════════════════════════════

def _case_17_borderline_linguistic_5_vs_4() -> BenchmarkCase:
    scenario = _scenario(
        id_=117, title="Routine follow-up, near-native pronunciation", setting="Outpatient clinic", difficulty="medium",
        specialty="general medicine", patient_name="Elin", age=39, condition="routine follow-up", mood="calm",
        background="Straightforward review visit.", concerns=[], tasks=["Review progress"],
    )
    transcript = [
        {"role": "nurse", "content": "Hello, how have you been getting on since your last visit?"},
        {"role": "patient", "content": "Pretty well, thank you."},
        {"role": "nurse", "content": "That's good to hear. Any new symptoms at all?"},
        {"role": "patient", "content": "No, nothing new."},
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9017, "duration_seconds": 35.0, "interrupted_count": 0}
    audio_evidence = _elite_audio(78.0, 80.0, 95.0)

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification=(
                           "BORDERLINE 5 vs 4: Azure overall pronunciation score is 78.0 with zero flagged problem "
                           "words, which is genuinely close to the range this benchmark's other cases treat as fully "
                           "intelligible (case_01 scored 84.0 as a 5). A reviewer reading 'no problem words at all' "
                           "as sufficient on its own could reasonably score this a 5. This reference scores 4 "
                           "(clearly intelligible, only minor imperfection) instead, more conservatively, because a "
                           "score in the high-70s sits closer to the middle of the observed range than to the "
                           "clearly-5 cases elsewhere in this benchmark, and proximity to a boundary should not by "
                           "itself be read as clearing it. This is a genuine judgement call: nothing in the evidence "
                           "here objectively rules out 5."
                       ),
                       evidence_refs=[_ref("pronunciation", "overall_score", None, LEVEL_L1_DIRECT, "direct")],
                       limitations=["borderline 5-vs-4 call; see justification for the case for scoring 5 instead"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Fluency score 80.0, completeness 95.0; natural pacing throughout.",
                       evidence_refs=[_ref("pronunciation", "fluency_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Plain, natural register, no jargon.", evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Accurate, natural phrasing throughout this short exchange.",
                       evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="Only a bare greeting, no name/role/purpose or empathy evidence this session.",
                       limitations=["no_indicator_level_detector: A1-A4 all empty this session"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No concern was raised or explored in this routine check-in.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language in this brief exchange.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="Only closed check-in questions detected, no D-indicator technique markers fired.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No clinical information was given in this check-in exchange.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_17_borderline_linguistic_5_vs_4", "borderline_linguistic_5_vs_4",
        "Azure pronunciation score sits in the high-70s with zero problem words -- an adjacent 5-vs-4 intelligibility call.",
        scenario, transcript, session_context=session_context, audio_evidence=audio_evidence,
        tags=["borderline", "adjacent_level", "calibration_critical", "linguistic_5_vs_4"], judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 18 -- borderline_linguistic_4_vs_3 (fluency)
# ═══════════════════════════════════════════════════════════════════════

def _case_18_borderline_linguistic_4_vs_3() -> BenchmarkCase:
    scenario = _scenario(
        id_=118, title="Medication counselling, mid-range fluency", setting="Pharmacy clinic", difficulty="medium",
        specialty="general medicine", patient_name="Karim", age=51, condition="new blood pressure medication",
        mood="attentive", background="Starting a new antihypertensive.", concerns=[], tasks=["Explain new medication"],
    )
    transcript = [
        {"role": "nurse", "content": "So, this new tablet, um, it will help to lower your blood pressure over the next few weeks."},
        {"role": "patient", "content": "Okay, how often do I take it?"},
        {"role": "nurse", "content": "Once a day, in the -- in the morning, with food if possible."},
        {"role": "patient", "content": "Got it, thank you."},
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9018, "duration_seconds": 45.0, "interrupted_count": 0}
    audio_evidence = _elite_audio(70.0, 64.0, 88.0)

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=3,
                       justification="Azure overall score 70.0, no problem words flagged; generally intelligible with some listener effort.",
                       evidence_refs=[_ref("pronunciation", "overall_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=3,
                       justification=(
                           "BORDERLINE 4 vs 3: fluency score is 64.0 with completeness 88.0, and the transcript shows "
                           "two short hesitation markers ('um', a self-corrected 'in the -- in the morning'). A "
                           "reviewer reading these as brief, natural self-corrections that never break communication "
                           "could reasonably score this a 4 (occasional lapses only). This reference scores 3 "
                           "(effective but with noticeable hesitation) instead because there are two separate "
                           "disfluency markers in a very short, four-turn exchange -- proportionally more frequent "
                           "than the single-lapse pattern a 4 would suggest -- though the message is always "
                           "delivered clearly. A careful reviewer scoring 4 here would not be wrong."
                       ),
                       evidence_refs=[_ref("pronunciation", "fluency_score", None, LEVEL_L1_DIRECT, "direct")],
                       limitations=["borderline 4-vs-3 call; see justification for the case for scoring 4 instead"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Plain register, no jargon.", evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Grammar itself is accurate despite the hesitation markers.",
                       evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No greeting or empathy evidence in this brief medication-counselling exchange.",
                       limitations=["no_indicator_level_detector: A1-A4 all empty this session"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No concern was raised or explored this session.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language detected this session.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="The patient asked the only question in this exchange; no nurse D-indicator technique markers fired.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="Dosing information was given, but no E1-E5 technique markers fired this session.",
                       limitations=["no_indicator_level_detector: E1-E5 all empty this session"]),
        ]

    return build_case(
        "case_18_borderline_linguistic_4_vs_3", "borderline_linguistic_4_vs_3",
        "Mid-60s fluency score with two short hesitation markers in a very brief exchange -- an adjacent 4-vs-3 fluency call.",
        scenario, transcript, session_context=session_context, audio_evidence=audio_evidence,
        tags=["borderline", "adjacent_level", "calibration_critical", "linguistic_4_vs_3"], judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 19 -- long_consultation_dense_evidence
# ═══════════════════════════════════════════════════════════════════════

def _case_19_long_consultation() -> BenchmarkCase:
    concern_driving = "When can I drive again?"
    concern_forever = "Will I need this medication forever?"
    scenario = _scenario(
        id_=119, title="Cardiac rehab follow-up after myocardial infarction", setting="Cardiac rehabilitation clinic",
        difficulty="hard", specialty="cardiology", patient_name="Mr. Okafor", age=56,
        condition="recovering from myocardial infarction", mood="shaken",
        background="Delivery driver, first heart attack, many practical and long-term questions.",
        concerns=[concern_driving, concern_forever],
        tasks=["Discuss return to driving/work", "Explain new medications", "Check understanding throughout"],
    )
    transcript = [
        {"role": "nurse", "content": "Hello Mr. Okafor, I'm nurse Elena, one of the cardiac rehab nurses. I'd like to go through your recovery and answer your questions today -- is that alright?"},
        {"role": "patient", "content": "Yes, thank you. I have a lot of questions, I'm still a bit shaken from all this."},
        {"role": "nurse", "content": "That's completely understandable after a heart attack, it's a lot to take in, and I'm glad you've got questions ready."},
        {"role": "patient", "content": "When can I drive again? I deliver parcels for a living."},
        {"role": "nurse", "content": "That's an important one. Can you tell me a bit more about what your driving day usually looks like?"},
        {"role": "patient", "content": "Long hours, a lot of getting in and out of the van, sometimes lifting heavy boxes."},
        {"role": "nurse", "content": "Thanks for explaining that. Generally, after this type of heart attack, most people can return to ordinary driving after about four weeks, but delivery work with heavy lifting usually needs six to eight weeks and a doctor's sign-off."},
        {"role": "patient", "content": "Okay, that makes sense I suppose."},
        {"role": "nurse", "content": "Does that answer what you were asking, or is there more to the driving question?"},
        {"role": "patient", "content": "That's clear for now, thank you."},
        {"role": "nurse", "content": "Good. Now, before I go through your new medications, what do you already know about statins?"},
        {"role": "patient", "content": "Not much, just that they're for cholesterol I think."},
        {"role": "nurse", "content": "That's right. So, first I'll explain what each tablet does, then we'll talk about timing, and finally about any side effects to watch for."},
        {"role": "patient", "content": "Sounds good."},
        {"role": "nurse", "content": "This one, atorvastatin, lowers your cholesterol to protect your arteries. How does that sound so far?"},
        {"role": "patient", "content": "Alright, though I'm a bit worried about taking tablets forever."},
        {"role": "nurse", "content": "I hear that concern, and it's a common one. Moving on to the second question you raised earlier -- will you need this medication forever?"},
        {"role": "patient", "content": "Yes, that's exactly it."},
        {"role": "nurse", "content": "Most people on this medication after a heart attack do stay on it long-term, because it keeps protecting your heart, but your GP will review it at every check-up rather than just leaving it unchanged forever. How do you feel about that?"},
        {"role": "patient", "content": "Okay, that's reassuring actually."},
        {"role": "nurse", "content": "So just to summarise -- driving in four to eight weeks depending on the lifting, and the cholesterol tablet is a long-term one reviewed regularly at your check-ups. Does that match what you understood?"},
        {"role": "patient", "content": "Yes, that matches. Actually, wait -- does the four weeks include motorway driving, or just local roads? A lot of my delivery routes are motorway."},
        {"role": "nurse", "content": "Good question to raise again -- motorway driving specifically needs the fuller six-to-eight-week recovery too, given the higher speeds and concentration needed, so let's be cautious there rather than the shorter four-week estimate."},
        {"role": "patient", "content": "Right, that's really helpful, thank you for being so thorough."},
    ]
    candidate_events = [
        CandidateEvent(event="opening_greeting", turn_index=0, evidence_text="Hello Mr. Okafor, I'm nurse Elena"),
        CandidateEvent(event="opening_introduction", turn_index=0, evidence_text="I'm nurse Elena, one of the cardiac rehab nurses"),
        CandidateEvent(event="opening_purpose_setting", turn_index=0, evidence_text="I'd like to go through your recovery and answer your questions today"),
        CandidateEvent(event="empathy_acknowledgement", turn_index=2, evidence_text="That's completely understandable after a heart attack"),
        CandidateEvent(event="open_question", turn_index=4, evidence_text="Can you tell me a bit more about what your driving day usually looks like?"),
        CandidateEvent(event="concern_exploration", turn_index=4, evidence_text="what your driving day usually looks like", target_concern=concern_driving),
        CandidateEvent(event="concern_addressing", turn_index=6, evidence_text="most people can return to ordinary driving after about four weeks, but delivery work ... needs six to eight weeks", target_concern=concern_driving),
        CandidateEvent(event="understanding_checked", turn_index=8, evidence_text="Does that answer what you were asking"),
        CandidateEvent(event="prior_knowledge_check", turn_index=10, evidence_text="what do you already know about statins"),
        CandidateEvent(event="consultation_sequence_marker", turn_index=12, evidence_text="First I'll explain what each tablet does, then we'll talk about timing, and finally about any side effects"),
        CandidateEvent(event="organization_marker", turn_index=12, evidence_text="First ... then ... finally"),
        CandidateEvent(event="reaction_response", turn_index=14, evidence_text="How does that sound so far?", related_patient_turns=[15], related_information_turns=[14]),
        CandidateEvent(event="empathy_acknowledgement", turn_index=16, evidence_text="I hear that concern, and it's a common one"),
        CandidateEvent(event="concern_addressing", turn_index=16, evidence_text="will you need this medication forever?", target_concern=concern_forever),
        CandidateEvent(event="concern_addressing", turn_index=18, evidence_text="most people ... do stay on it long-term ... your GP will review it at every check-up", target_concern=concern_forever),
        CandidateEvent(event="contribution_invitation", turn_index=18, evidence_text="How do you feel about that?", related_patient_turns=[19], related_information_turns=[18]),
        CandidateEvent(event="summary_statement", turn_index=20, evidence_text="just to summarise -- driving in four to eight weeks ... reviewed regularly", related_patient_turns=[7, 15]),
        CandidateEvent(event="summary_check", turn_index=20, evidence_text="Does that match what you understood?", related_patient_turns=[7, 15]),
        CandidateEvent(event="understanding_checked", turn_index=20, evidence_text="Does that match what you understood?"),
        CandidateEvent(event="reflective_response", turn_index=22, evidence_text="Good question to raise again", related_patient_turns=[21]),
        CandidateEvent(event="concern_addressing", turn_index=22, evidence_text="motorway driving specifically needs the fuller six-to-eight-week recovery too", target_concern=concern_driving),
    ]
    patient_events = [
        PatientEvent(event="emotional_trigger_fired", turn_index=1, evidence_text="I'm still a bit shaken from all this"),
        PatientEvent(event="concern_raised", turn_index=3, evidence_text=concern_driving),
        PatientEvent(event="concern_raised", turn_index=15, evidence_text="I'm a bit worried about taking tablets forever"),
        PatientEvent(event="concern_raised", turn_index=21, evidence_text="does the four weeks include motorway driving, or just local roads?"),
    ]
    concern_outcomes = [
        ConcernOutcome(
            concern=concern_driving, final_status="addressed", resolved=False,
            history=[
                {"status": "raised", "turn_index": 3, "cause_event": None},
                {"status": "addressed", "turn_index": 6, "cause_event": "concern_addressing"},
                {"status": "resolved", "turn_index": 9, "cause_event": None},
                {"status": "raised", "turn_index": 21, "cause_event": None},
                {"status": "addressed", "turn_index": 22, "cause_event": "concern_addressing"},
            ],
            resolved_at_turns=[9],
            reopened_events=[{"turn_index": 21, "from_status": "resolved", "to_status": "raised", "reason": "motorway driving specifically was not covered by the original four-week estimate"}],
        ),
        ConcernOutcome(
            concern=concern_forever, final_status="resolved", resolved=True,
            history=[
                {"status": "raised", "turn_index": 15, "cause_event": None},
                {"status": "addressed", "turn_index": 16, "cause_event": "concern_addressing"},
                {"status": "addressed", "turn_index": 18, "cause_event": "concern_addressing"},
                {"status": "resolved", "turn_index": 19, "cause_event": None},
            ],
            resolved_at_turns=[19],
        ),
    ]
    jargon_evidence = [
        JargonEvidence(term="atorvastatin", turn_index=14, evidence_text="atorvastatin", clarified_afterward=True),
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9019, "duration_seconds": 620.0, "interrupted_count": 0}
    audio_evidence = _elite_audio(88.0, 85.0, 97.0)

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=5,
                       justification="Azure overall score 88.0 across a long, sustained exchange with no problem words flagged; clearly intelligible throughout.",
                       evidence_refs=[_ref("pronunciation", "overall_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=5,
                       justification="Fluency score 85.0, completeness 97.0 sustained across a long, multi-topic consultation.",
                       evidence_refs=[_ref("pronunciation", "fluency_score", None, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Plain register throughout; the one piece of clinical jargon ('atorvastatin') is immediately followed by a plain-language explanation of what it does.",
                       evidence_refs=[_ref("jargon_evidence", "atorvastatin", 14, LEVEL_L2_DETERMINISTIC, "deterministic_rule")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=5,
                       justification="Accurate, varied, naturally complex phrasing sustained across a long consultation covering multiple topics.",
                       evidence_refs=[_ref("transcript", "turn_18", 18, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="Full appropriate opening (A1), and repeated genuine empathy for two separate disclosures at turns 2 and 16 (A4) sustained across a long consultation, with no dismissive or judgmental language anywhere in the transcript.",
                       evidence_refs=[
                           _ref("candidate_event", "opening_greeting", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "empathy_acknowledgement", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "empathy_acknowledgement", 16, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification=(
                           "Two separate concerns are each fully explored, addressed, and resolved (B1-B3 complete "
                           "lifecycle for both), and the driving concern is genuinely reopened by new information "
                           "late in the consultation (turn 21) -- the nurse explicitly recognises the reopening "
                           "('Good question to raise again') and gives an adjusted, more cautious answer specific to "
                           "motorway driving rather than repeating the original estimate. Handling a reopened "
                           "concern this well, on top of two clean original resolutions, across a long multi-topic "
                           "session is the strongest pattern this benchmark's B-criterion cases show."
                       ),
                       evidence_refs=[
                           _ref("concern_timeline", f"{concern_driving}::resolved", 9, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                           _ref("concern_timeline", f"{concern_driving}::raised", 21, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                           _ref("concern_timeline", f"{concern_driving}::addressed", 22, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                           _ref("concern_timeline", f"{concern_forever}::resolved", 19, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="Explicit sequencing announced and followed ('First...then...finally', turn 12) and a clear topic-transition signpost when returning to an earlier question (turn 16), sustained purposefully across a long, multi-topic consultation.",
                       evidence_refs=[
                           _ref("candidate_event", "consultation_sequence_marker", 12, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "organization_marker", 12, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="One clear open question exploring the driving concern (D2, turn 4), and an explicit summary that invites correction (D5, turn 20, immediately validated when the patient does raise a correction at turn 21) -- with zero compound/leading questions anywhere across a long, many-turn consultation.",
                       evidence_refs=[
                           _ref("candidate_event", "open_question", 4, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "summary_statement", 20, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "summary_check", 20, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ],
                       limitations=["no D4 clarification-request evidence this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_ASSESSED, level=3,
                       justification="Prior-knowledge check before explaining medication (E1, turn 10), a reaction-check during delivery (E2, turn 14), an explicit invitation to react after the long-term-medication explanation (E3, turn 18), and understanding checks after both major explanations (E4, turns 8 and 20) -- repeated, varied information-giving technique sustained across multiple information-giving sequences in a long consultation.",
                       evidence_refs=[
                           _ref("candidate_event", "prior_knowledge_check", 10, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "reaction_response", 14, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "contribution_invitation", 18, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "understanding_checked", 8, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "understanding_checked", 20, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                       ],
                       limitations=["no E5 further-information-check evidence this session"]),
        ]

    return build_case(
        "case_19_long_consultation", "long_consultation_dense_evidence",
        (
            "A long, multi-topic consultation with two concerns, one genuinely reopened late by new information, "
            "repeated empathy and understanding-checks, and evidence drawn from candidate events, patient events, "
            "concern timelines, state transitions, jargon evidence, and audio scoring at once -- tests whether a "
            "future reviewer (human or Shadow Examiner) can track evidence volume and context across many turns "
            "without losing the reopening or double-counting the two concerns."
        ),
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        concern_outcomes=concern_outcomes, jargon_evidence=jargon_evidence, session_context=session_context,
        audio_evidence=audio_evidence, tags=["long_consultation", "evidence_volume", "concern_reopened", "multi_source_evidence"],
        judgements_fn=judgements,
    )


# ═══════════════════════════════════════════════════════════════════════
# Case 20 -- conflicting_mixed_evidence
# ═══════════════════════════════════════════════════════════════════════

def _case_20_conflicting_mixed_evidence() -> BenchmarkCase:
    scenario = _scenario(
        id_=120, title="Unexpected extended stay, mixed technique and outcome", setting="Surgical ward",
        difficulty="hard", specialty="surgical", patient_name="Mr. Osei", age=60,
        condition="post-operative, unexpected extended admission", mood="disappointed",
        background="Was expecting discharge tomorrow; now told he needs a longer stay for wound care.",
        concerns=[], tasks=["Deliver news of extended stay", "Explain wound care plan"],
    )
    transcript = [
        {"role": "nurse", "content": "Hi Mr. Osei, I know today's news about needing a longer hospital stay must be hard to hear."},
        {"role": "patient", "content": "Yeah... I really thought I'd be going home tomorrow."},
        {"role": "nurse", "content": "I completely understand how disappointing that is, and I'm sorry you're feeling this way."},
        {"role": "patient", "content": "..."},
        {"role": "nurse", "content": "Before I explain the wound care plan, what do you already know about how deep wounds like yours usually heal?"},
        {"role": "patient", "content": "Not much really, I was told it just takes time."},
        {"role": "nurse", "content": "That's roughly right. So this wound needs daily dressing changes for two weeks, then a nurse review, and if it's healing well by then you'll likely need one more week after that before it's fully closed."},
        {"role": "patient", "content": "Okay... so wait, does that mean three weeks total, or three weeks just for the dressings?"},
    ]
    candidate_events = [
        CandidateEvent(event="empathy_acknowledgement", turn_index=0, evidence_text="I know today's news about needing a longer hospital stay must be hard to hear"),
        CandidateEvent(event="empathy_acknowledgement", turn_index=2, evidence_text="I completely understand how disappointing that is, and I'm sorry you're feeling this way"),
        CandidateEvent(event="prior_knowledge_check", turn_index=4, evidence_text="what do you already know about how deep wounds like yours usually heal"),
    ]
    patient_events = [
        PatientEvent(event="emotional_trigger_fired", turn_index=1, evidence_text="I really thought I'd be going home tomorrow"),
    ]
    state_transitions = [
        StateTransition(field="current_emotion", before="hopeful", after="disappointed", cause_event=None, turn_index=1),
        StateTransition(field="current_emotion", before="disappointed", after="withdrawn", cause_event=None, turn_index=3),
    ]
    session_context = {"pipeline": "realtime", "session_usage_id": 9020, "duration_seconds": 50.0, "interrupted_count": 0}

    def judgements(cem: CriterionEvidenceMap) -> List[CriterionJudgement]:
        return [
            _judgement(cem, CRITERION_INTELLIGIBILITY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_FLUENCY, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE,
                       justification="No audio evidence available for this session.", limitations=["no_audio_evidence"]),
            _judgement(cem, CRITERION_APPROPRIATENESS_OF_LANGUAGE, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Plain, gentle register throughout, no unexplained jargon.",
                       evidence_refs=[_ref("transcript", "turn_0", 0, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RESOURCES_OF_GRAMMAR_AND_EXPRESSION, FAMILY_LINGUISTIC, STATUS_ASSESSED, level=4,
                       justification="Accurate, natural phrasing throughout.", evidence_refs=[_ref("transcript", "turn_6", 6, LEVEL_L1_DIRECT, "direct")]),
            _judgement(cem, CRITERION_RELATIONSHIP_BUILDING, FAMILY_CLINICAL, STATUS_ASSESSED, level=1,
                       justification=(
                           "MIXED/CONFLICTING EVIDENCE: two separate, well-targeted empathy acknowledgements (L2 "
                           "deterministic technique evidence, turns 0 and 2) are genuine and correctly aimed at the "
                           "patient's disappointment. But the patient outcome evidence (L4) tells a different story "
                           "-- the state transition at turn 3 shows the patient moving from disappointed to "
                           "withdrawn immediately after both empathy responses, and the literal '...' is direct "
                           "transcript evidence the words did not land. A reviewer weighting the technique evidence "
                           "on its own terms could reasonably score this higher (Competent use, 2); this reference "
                           "weights the patient-outcome signal more heavily when the two diverge, since an "
                           "acknowledgement that measurably fails to reach the patient is weaker evidence of "
                           "effective relationship-building than the same words landing would be. This is a "
                           "deliberate test of how much weight technique-presence should get when outcome evidence "
                           "points the other way -- not a claim that 1 is the only defensible score."
                       ),
                       evidence_refs=[
                           _ref("candidate_event", "empathy_acknowledgement", 0, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("candidate_event", "empathy_acknowledgement", 2, LEVEL_L2_DETERMINISTIC, "deterministic_rule"),
                           _ref("state_transition", "current_emotion", 3, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                           _ref("patient_event", "emotional_trigger_fired", 1, LEVEL_L4_PATIENT_OUTCOME, "deterministic_rule"),
                       ],
                       limitations=["technique evidence (L2) and patient-outcome evidence (L4) point in different directions; see justification"]),
            _judgement(cem, CRITERION_PATIENT_PERSPECTIVE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No scenario-defined concern was raised this session; the discharge-news reaction is relationship-building evidence, not a concern lifecycle.",
                       limitations=["no_indicator_level_detector: no concern-related evidence this session"]),
            _judgement(cem, CRITERION_PROVIDING_STRUCTURE, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No sequencing or signposting language detected this session.",
                       limitations=["no_indicator_level_detector: C1/C2/C3 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GATHERING, FAMILY_CLINICAL, STATUS_LIMITED_EVIDENCE,
                       justification="No D-indicator technique markers fired this session; the prior-knowledge check at turn 4 is E-criterion evidence, not D.",
                       limitations=["no_indicator_level_detector: D1-D5 all empty this session"]),
            _judgement(cem, CRITERION_INFORMATION_GIVING, FAMILY_CLINICAL, STATUS_ASSESSED, level=1,
                       justification=(
                           "MIXED/CONFLICTING EVIDENCE: the prior-knowledge check before explaining the wound-care "
                           "plan (E1, turn 4) is genuine good technique, and clear information is then given (turn "
                           "6). But no E4 understanding-check follows it, and the patient's own next turn is direct "
                           "transcript evidence of real confusion about the timeline just explained ('does that mean "
                           "three weeks total, or three weeks just for the dressings?'). Good information-giving "
                           "TECHNIQUE is present, but the OUTCOME shows the message did not land -- a reviewer "
                           "crediting the E1 technique on its own could reasonably score this higher (2); this "
                           "reference scores 1 because the missing E4 check is exactly what would have caught the "
                           "confusion the patient in fact had."
                       ),
                       evidence_refs=[_ref("candidate_event", "prior_knowledge_check", 4, LEVEL_L2_DETERMINISTIC, "deterministic_rule")],
                       limitations=["E1 technique evidence and the turn-7 confusion (visible in the transcript, outside this criterion's evidence-ref set) point in different directions; no E4 evidence to resolve it; see justification"]),
        ]

    return build_case(
        "case_20_conflicting_mixed_evidence", "conflicting_mixed_evidence",
        "Genuine empathy technique paired with a worsening patient outcome, and a good prior-knowledge check paired with visible unaddressed confusion -- cross-criterion mixed evidence, not a single-event conflict.",
        scenario, transcript, candidate_events=candidate_events, patient_events=patient_events,
        state_transitions=state_transitions, session_context=session_context, audio_evidence=NO_AUDIO,
        tags=["conflict", "mixed_evidence", "calibration_critical", "patient_outcome_vs_technique"],
        judgements_fn=judgements,
    )


# ── Registry ───────────────────────────────────────────────────────────

_CASE_BUILDERS = [
    _case_01_strong_overall, _case_02_weak_overall, _case_03_strong_language_weak_clinical,
    _case_04_weak_language_strong_clinical, _case_05_excellent_relationship_building,
    _case_06_poor_relationship_building, _case_07_poor_structure_and_questioning,
    _case_08_information_giving_all_gaps, _case_09_concern_resolved_clean, _case_10_concern_reopened,
    _case_11_multiple_concerns_one_ignored, _case_12_conflicting_evidence, _case_13_minimal_consultation,
    _case_14_borderline_clinical_3_vs_2, _case_15_borderline_clinical_2_vs_1,
    _case_16_borderline_clinical_1_vs_0, _case_17_borderline_linguistic_5_vs_4,
    _case_18_borderline_linguistic_4_vs_3, _case_19_long_consultation, _case_20_conflicting_mixed_evidence,
]

GOLDEN_SET: List[BenchmarkCase] = [builder() for builder in _CASE_BUILDERS]


# ── Validation / export ────────────────────────────────────────────────

def validate_case(case: BenchmarkCase) -> ShadowResult:
    """Wraps a case's reference_judgement in a dummy ShadowResult purely to
    reuse ShadowResult's own validators (exactly 9 criteria, no duplicates,
    all present) -- same schema a real model output will be checked against,
    so a golden-set authoring mistake is caught the same way a bad model
    response would be."""
    return ShadowResult(
        session_ref=SessionRef(pipeline="benchmark", session_usage_id=None),
        criteria=case.reference_judgement,
        evaluation_metadata={
            "model": "human_reviewer_placeholder", "prompt_version": "golden_set_v1",
            "generated_at": "n/a", "criteria_unavailable": [], "evidence_complete": True,
        },
    )


def cited_evidence_ids(cem: CriterionEvidenceMap, criterion: str) -> set:
    """Every evidence_id that actually appears in the CriterionEvidenceMap
    for `criterion` -- used to catch a reference judgement citing an
    evidence_id that was never actually produced by the pipeline (the same
    anti-hallucination property the future model prompt itself enforces)."""
    ids: set = set()
    for bundle in cem.clinical:
        if bundle.criterion != criterion:
            continue
        for indicator in bundle.indicators:
            ids.update(ref.evidence_id for ref in indicator.evidence_refs)
    for bundle in cem.linguistic:
        if bundle.criterion != criterion:
            continue
        ids.update(ref.evidence_id for ref in bundle.evidence_refs)
    return ids


def export_golden_set_json(path: str) -> None:
    """Writes the whole golden set as a plain JSON array -- the model-
    independent artifact section 22/the task's own opening framing calls
    for, consumable by a human reviewer or any other model's API without
    importing this codebase."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump([case.export_dict() for case in GOLDEN_SET], f, indent=2)
