"""
Tests for the Step 4 Patient Behaviour & Emotional State Engine
(app/services/patient_state.py additions on top of the Step 1 PatientState:
trust, current_emotion, concern_status, current_concern -- and the
deterministic event detector/transition logic that computes them).

Same style as test_patient_state.py: pure functions and direct prompt-builder
calls, no live DB, no FastAPI TestClient. _call_ai is monkeypatched for the
legacy-pipeline test.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.ai_scoring as ai_scoring
import app.services.patient_state as patient_state
import app.routers.speaking_realtime as srt
from app.services.patient_state import derive_patient_state, detect_nurse_events, render_patient_state_prompt


def _run(coro):
    return asyncio.run(coro)


CARD = {
    "patient_name": "Mrs. Chen",
    "age": 58,
    "condition": "upcoming knee surgery",
    "mood": "anxious",
    "background": "Nervous first-time surgical patient.",
    "instructions_for_ai": "Be visibly anxious about the operation.",
    "emotional_triggers": ["fear about surgery"],
    "questions_to_ask": ["fear about the operation"],
    "information_to_withhold": [],
}

CONCERN = "fear about the operation"


# ── 1. Empathy acknowledges but does not resolve ────────────────────────

def test_empathy_acknowledges_but_does_not_resolve():
    history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "I understand you're worried."},
    ]
    state = derive_patient_state(CARD, history)

    assert state.concern_status[CONCERN] == "acknowledged"
    assert state.current_concern == CONCERN


# ── 2. Concern exploration is a separate event/status from understanding_checked ─

def test_concern_exploration_is_distinct_from_understanding_checked():
    exploration_events = detect_nurse_events("What worries you most about it?")
    assert any(e["event"] == "concern_exploration" for e in exploration_events)
    assert not any(e["event"] == "understanding_checked" for e in exploration_events)

    understanding_events = detect_nurse_events("Does that make sense?")
    assert any(e["event"] == "understanding_checked" for e in understanding_events)
    assert not any(e["event"] == "concern_exploration" for e in understanding_events)

    history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "What worries you most about it?"},
    ]
    state = derive_patient_state(CARD, history)
    assert state.concern_status[CONCERN] == "explored"


# ── 3. Understanding check is independent and requires prior exploration ─

def test_understanding_check_advances_only_after_exploration():
    # No exploration yet -- an understanding check alone must not fabricate
    # "addressed" out of nothing.
    history_no_exploration = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "Does that make sense?"},
    ]
    state = derive_patient_state(CARD, history_no_exploration)
    assert state.concern_status[CONCERN] == "raised"

    # Full sequence: acknowledge -> explore -> understanding check -> addressed.
    # Nothing re-raises the concern afterwards, so it also graduates to
    # resolved (see test_concern_only_resolves_after... for the distinction
    # between reaching "addressed" and staying there vs. resolving).
    history_full = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "I understand you're worried."},
        {"role": "nurse", "content": "What worries you most about it?"},
        {"role": "patient", "content": "I'm afraid I won't wake up from the anaesthetic."},
        {"role": "nurse", "content": "The anaesthetist will monitor you the whole time. Does that make sense?"},
    ]
    state_full = derive_patient_state(CARD, history_full)
    assert state_full.concern_status[CONCERN] == "resolved"


# ── 4. Dismissive response lowers trust ──────────────────────────────────

def test_dismissive_response_lowers_trust_and_does_not_advance_concern():
    history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "Don't worry, you'll be fine."},
    ]
    state = derive_patient_state(CARD, history)

    assert state.trust == "low"
    assert state.concern_status[CONCERN] == "raised"


# ── 5. Jargon detector is reused, not duplicated ─────────────────────────

def test_jargon_detector_is_the_same_object_everywhere():
    assert ai_scoring.detect_jargon is patient_state.detect_jargon
    assert ai_scoring.MEDICAL_JARGON is patient_state.MEDICAL_JARGON

    history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "You have tachycardia."},
    ]
    state = derive_patient_state(CARD, history)
    assert state.trust == "low"  # jargon counts as a negative event too


# ── 6. Emotional escalation ──────────────────────────────────────────────

def test_negative_behaviour_escalates_a_calm_baseline_patient():
    calm_card = {**CARD, "mood": "calm", "questions_to_ask": [CONCERN]}
    history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "Don't worry, you'll be fine."},
    ]
    state = derive_patient_state(calm_card, history)
    assert state.current_emotion == "anxious"


# ── 7. Emotional recovery ────────────────────────────────────────────────

def test_positive_behaviour_calms_an_anxious_patient():
    history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "I understand you're worried."},
        {"role": "nurse", "content": "What worries you most about it?"},
    ]
    state = derive_patient_state(CARD, history)
    assert state.current_emotion == "calm"
    assert state.trust == "high"


# ── 8. Unresolved concern persistence ────────────────────────────────────

def test_ignored_concern_stays_active_across_turns():
    history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "Let's talk about your diet instead."},
        {"role": "patient", "content": "Okay."},
        {"role": "nurse", "content": "How has your appetite been?"},
    ]
    state = derive_patient_state(CARD, history)
    assert state.concern_status[CONCERN] == "raised"
    assert state.current_concern == CONCERN


# ── 9. Concern resolution requires addressing AND not being re-raised ──

def test_concern_only_resolves_after_being_addressed_and_not_repeated():
    history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "I understand you're worried."},
        {"role": "nurse", "content": "What worries you most about it?"},
        {"role": "patient", "content": "I'm afraid I won't wake up from the anaesthetic."},
        {"role": "nurse", "content": "The anaesthetist monitors you throughout. Does that make sense?"},
        {"role": "patient", "content": "Yes, that's clearer, thank you."},
    ]
    state = derive_patient_state(CARD, history)
    assert state.concern_status[CONCERN] == "resolved"
    assert state.current_concern is None

    # Same sequence, but the patient brings the concern back up afterwards --
    # must NOT be marked resolved just because it was once addressed.
    history_reraised = history + [
        {"role": "nurse", "content": "Any other questions?"},
        {"role": "patient", "content": "Actually I'm still frightened about the operation."},
    ]
    state_reraised = derive_patient_state(CARD, history_reraised)
    assert state_reraised.concern_status[CONCERN] == "addressed"
    assert state_reraised.current_concern == CONCERN


# ── 10. Scenario/persona variation ───────────────────────────────────────

def test_jargon_reaction_varies_by_scenario_persona():
    confused_card = {**CARD, "mood": "confused"}
    trained_card = {**CARD, "mood": "neutral", "background": "Retired nurse, medically trained."}
    history = [{"role": "nurse", "content": "You have tachycardia."}]

    confused_state = derive_patient_state(confused_card, history)
    trained_state = derive_patient_state(trained_card, history)

    assert confused_state.trust == "low"
    assert trained_state.trust == "moderate"  # medically-trained persona shrugs off jargon


# ── 11. Legacy pipeline receives the new fields ──────────────────────────

def test_legacy_pipeline_prompt_includes_relationship_state(monkeypatch):
    captured = {}

    async def fake_call_ai(messages, **kw):
        captured["messages"] = messages
        return {"raw_feedback": "But I'm still worried...", "provider_failure": False}

    monkeypatch.setattr(ai_scoring, "_call_ai", fake_call_ai)

    history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "Don't worry, you'll be fine."},
    ]
    _run(ai_scoring.get_patient_response(CARD, history, "Anyway, let's continue."))

    system_prompt = captured["messages"][0]["content"]
    assert "RELATIONSHIP & CURRENT REACTION" in system_prompt
    assert "Trust in the nurse so far: low" in system_prompt
    assert CONCERN in system_prompt


# ── 12. Realtime pipeline receives the new fields ────────────────────────

def test_realtime_pipeline_prompt_includes_relationship_state():
    history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
        {"role": "nurse", "content": "I understand you're worried."},
    ]
    state = derive_patient_state(CARD, history)
    prompt = srt._build_realtime_system_prompt(CARD, state=state)

    assert "RELATIONSHIP & CURRENT REACTION" in prompt
    assert "Trust in the nurse so far" in prompt
    assert "{" not in prompt and "}" not in prompt


# ── 13. Session isolation: pure function, no shared mutable state ───────

def test_no_state_leakage_between_independent_derivations():
    history_a = [{"role": "patient", "content": "I'm frightened about the operation."}]
    history_b = [{"role": "nurse", "content": "Don't worry, you'll be fine."}]

    state_a = derive_patient_state(CARD, history_a)
    state_b = derive_patient_state(CARD, history_b)

    assert state_a.concern_status[CONCERN] == "raised"
    assert state_b.concern_status[CONCERN] == "not_raised"
    # The card's own list must not have been mutated by either call.
    assert CARD["questions_to_ask"] == [CONCERN]


# ── 14. Reconnect: prior + new history concatenation still works ────────

def test_reconnect_style_concatenated_history_advances_state_correctly():
    prior_history = [
        {"role": "patient", "content": "I'm frightened about the operation."},
    ]
    new_turns = [
        {"role": "nurse", "content": "I understand you're worried."},
        {"role": "nurse", "content": "What worries you most about it?"},
    ]
    state = derive_patient_state(CARD, prior_history + new_turns)

    assert state.concern_status[CONCERN] == "explored"
    assert state.trust == "high"
