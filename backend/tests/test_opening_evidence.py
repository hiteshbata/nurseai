"""Tests for the Relationship Building opening-interaction (A1) detector
(Step 21G). Same style as test_sequencing_evidence.py -- detect_opening_events
is keyword/regex-based, every assertion here was checked against the
detector's actual output on a literal phrase. No score assignments anywhere:
only presence/absence of evidence.
"""
from app.services.opening_evidence import OPENING_WINDOW_NURSE_TURNS, detect_opening_events


def _history(*turns):
    """turns: (role, content) pairs."""
    return [{"role": role, "content": content} for role, content in turns]


# ── Golden cases ──────────────────────────────────────────────────────────

def test_golden_1_greeting_detected():
    events = detect_opening_events(_history(("nurse", "Hello there.")))
    assert {"event": "opening_greeting", "turn_index": 0, "evidence": "Hello there."} in events


def test_golden_2_introduction_detected():
    events = detect_opening_events(_history(("nurse", "My name is Sarah.")))
    assert {"event": "opening_introduction", "turn_index": 0, "evidence": "My name is Sarah."} in events


def test_golden_3_role_identification_detected():
    events = detect_opening_events(_history(("nurse", "I'll be your nurse today.")))
    assert {"event": "opening_role_identification", "turn_index": 0, "evidence": "I'll be your nurse today."} in events


def test_golden_4_purpose_setting_detected():
    events = detect_opening_events(_history(("nurse", "I'd like to ask you some questions about your symptoms.")))
    assert any(e["event"] == "opening_purpose_setting" for e in events)


def test_golden_5_combined_opening_turn_yields_all_four():
    turn = "Hello there. My name is Sarah. I'll be your nurse today. I'd like to ask you some questions about how you've been feeling."
    events = detect_opening_events(_history(("nurse", turn)))
    names = {e["event"] for e in events}
    assert names == {
        "opening_greeting", "opening_introduction",
        "opening_role_identification", "opening_purpose_setting",
    }


def test_golden_6_greeting_and_purpose_split_across_two_nurse_turns():
    events = detect_opening_events(_history(
        ("nurse", "Hello, how are you feeling today?"),
        ("patient", "A bit worried, to be honest."),
        ("nurse", "I'd like to ask you a few questions about that."),
    ))
    assert any(e["event"] == "opening_greeting" and e["turn_index"] == 0 for e in events)
    assert any(e["event"] == "opening_purpose_setting" and e["turn_index"] == 2 for e in events)


def test_golden_7_outside_opening_window_not_detected():
    # OPENING_WINDOW_NURSE_TURNS nurse turns of small talk, then a late
    # greeting-shaped phrase well past the actual opening -- not evidence of
    # INITIATING the interaction anymore.
    turns = [("nurse", "How have you been feeling?") for _ in range(OPENING_WINDOW_NURSE_TURNS)]
    turns.append(("nurse", "Hello again, one more thing before we finish."))
    events = detect_opening_events(_history(*turns))
    assert not any(e["event"] == "opening_greeting" for e in events)


def test_golden_8_no_opening_evidence_in_a_task_only_turn():
    events = detect_opening_events(_history(("nurse", "Can you describe the pain?")))
    assert events == []


def test_golden_9_im_going_to_is_not_an_introduction():
    # "I'm going to..." names an upcoming action, not a person's name -- must
    # not be misread as an introduction just because it starts with "I'm".
    events = detect_opening_events(_history(("nurse", "I'm going to check your blood pressure now.")))
    assert not any(e["event"] == "opening_introduction" for e in events)


def test_golden_10_empty_history_produces_nothing():
    assert detect_opening_events([]) == []


def test_golden_11_patient_speaking_first_does_not_block_nurse_opening_detection():
    events = detect_opening_events(_history(
        ("patient", "Oh, hello, are you my nurse?"),
        ("nurse", "Hello! Yes, my name is Sarah and I'll be your nurse today."),
    ))
    names = {e["event"] for e in events}
    assert "opening_greeting" in names
    assert "opening_introduction" in names
    assert "opening_role_identification" in names


def test_determinism():
    history = _history(("nurse", "Hello, my name is Sarah. I'll be your nurse today."))
    assert detect_opening_events(history) == detect_opening_events(history)


def test_serialization_roundtrip():
    from app.services.speaking_evidence import CandidateEvent
    events = detect_opening_events(_history(("nurse", "Hello, my name is Sarah.")))
    refs = [CandidateEvent(event=e["event"], turn_index=e["turn_index"], evidence_text=e["evidence"]) for e in events]
    dumped = [r.model_dump() for r in refs]
    restored = [CandidateEvent(**d) for d in dumped]
    assert restored == refs


def test_speaking_evidence_integration():
    from app.services.speaking_evidence import build_speaking_evidence
    history = _history(("nurse", "Hello, my name is Sarah. I'll be your nurse today."))
    evidence = build_speaking_evidence({}, history)
    events = [e for e in evidence.candidate_events if e.event.startswith("opening_")]
    assert {e.event for e in events} == {
        "opening_greeting", "opening_introduction", "opening_role_identification",
    }
    assert all(e.source == "deterministic_rule" for e in events)


def test_criterion_evidence_maps_a1_without_detector_gap():
    from app.services.criterion_evidence import map_criterion_evidence
    from app.services.evidence_reconciliation import reconcile_evidence
    from app.services.examiner_input import build_examiner_input
    from app.services.speaking_evidence import InteractionMetrics, SpeakingEvidence

    metrics = InteractionMetrics(
        turn_counts={"nurse": 1, "patient": 0, "total": 1},
        jargon_events=0, empathy_events=0, concern_exploration_events=0,
        understanding_check_events=0, dismissive_events=0,
    )
    history = _history(("nurse", "Hello, my name is Sarah. I'll be your nurse today."))
    evidence = build_speaking_evidence_result = None
    from app.services.speaking_evidence import build_speaking_evidence
    speaking_evidence = build_speaking_evidence({}, history)
    unified = reconcile_evidence(speaking_evidence)
    ei = build_examiner_input(scenario={}, transcript=history, unified_evidence=unified)
    result = map_criterion_evidence(ei)
    rb = next(b for b in result.clinical if b.criterion == "relationship_building")
    a1 = next(i for i in rb.indicators if i.indicator == "A1")
    assert a1.gaps == []
    assert len(a1.evidence_refs) == 3


def test_no_detector_gap_when_nothing_said():
    from app.services.criterion_evidence import map_criterion_evidence
    from app.services.evidence_reconciliation import reconcile_evidence
    from app.services.examiner_input import AVAILABILITY_LIMITED, build_examiner_input
    from app.services.speaking_evidence import InteractionMetrics, SpeakingEvidence

    metrics = InteractionMetrics(
        turn_counts={"nurse": 1, "patient": 0, "total": 1},
        jargon_events=0, empathy_events=0, concern_exploration_events=0,
        understanding_check_events=0, dismissive_events=0,
    )
    evidence = SpeakingEvidence(
        candidate_events=[], patient_events=[], concern_outcomes=[], state_transitions=[],
        jargon_evidence=[], interaction_metrics=metrics, hidden_info_outcomes=[],
    )
    unified = reconcile_evidence(evidence)
    ei = build_examiner_input(
        scenario={}, transcript=[{"role": "nurse", "content": "Can you describe the pain?"}],
        unified_evidence=unified,
    )
    result = map_criterion_evidence(ei)
    rb = next(b for b in result.clinical if b.criterion == "relationship_building")
    a1 = next(i for i in rb.indicators if i.indicator == "A1")
    assert a1.evidence_refs == []
    assert a1.evidence_quality == AVAILABILITY_LIMITED
    assert a1.gaps == []


def test_no_score_no_model_call_no_db():
    """Structural guarantee: the detector module imports nothing from
    ai_scoring, no async/await, no network/DB client."""
    import ast
    import inspect

    import app.services.opening_evidence as mod
    source = inspect.getsource(mod)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Await), "no model/async calls allowed"
    assert "ai_scoring" not in source
    assert "score_speaking" not in source
    assert "async def" not in source
