"""
Tests for the Patient Simulation State foundation (app/services/patient_state.py)
and its wiring into both patient pipelines:
  - legacy: app.services.ai_scoring.get_patient_response()
  - realtime: app.routers.speaking_realtime._build_realtime_system_prompt()

Same style as test_speaking_chat_ai_failure.py: pure functions and direct
prompt-builder calls, no live DB, no FastAPI TestClient. _call_ai is
monkeypatched to capture the messages it was given rather than hit a real
provider.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.ai_scoring as ai_scoring
import app.routers.speaking_realtime as srt
from app.services.patient_state import SemanticHints, _hidden_info_candidate, derive_patient_state, render_patient_state_prompt


def _run(coro):
    return asyncio.run(coro)


# A deterministic scenario matching the Step 1 spec's worked example.
CARD = {
    "patient_name": "Mrs. Chen",
    "age": 58,
    "condition": "upcoming knee surgery",
    "mood": "anxious",
    "background": "Nervous first-time surgical patient.",
    "instructions_for_ai": "Be visibly anxious about the operation.",
    "emotional_triggers": ["fear about surgery"],
    "questions_to_ask": ["When can I go home after the surgery?"],
    "information_to_withhold": ["previous medication non-compliance"],
}

# Old-schema card as actually saved by the image/PDF extraction path
# (scenario_generator.py:/save) -- no emotional_triggers, no
# information_to_withhold, "concerns" instead of "questions_to_ask".
OLD_SCHEMA_CARD = {
    "patient_name": "Mary",
    "age": "",
    "condition": "chest pain",
    "mood": "Cooperative",
    "background": "",
    "instructions_for_ai": "",
    "concerns": ["Will I need an operation?"],
}


# ── 1. Initial state ─────────────────────────────────────────────────────

def test_initial_state_starts_with_everything_hidden_and_unraised():
    state = derive_patient_state(CARD, [])

    assert state.hidden_information == ["previous medication non-compliance"]
    assert state.revealed_information == []
    assert state.concerns_unresolved == ["When can I go home after the surgery?"]
    assert state.concerns_raised == []
    assert state.fired_emotional_triggers == []
    assert state.emotional_intensity == "baseline"
    assert state.turns_completed == 0


# ── 2. Reveal tracking ───────────────────────────────────────────────────
# Step 12B (Rule 1): a lexical keyword match alone is only ever a candidate.
# derive_patient_state now only promotes an item to revealed_information via
# hints.confirmed_hidden_reveals -- these tests simulate what a real
# semantic verification would have produced (see semantic_evidence.py for
# how confirmed_hidden_reveals actually gets populated in production).

def test_hidden_information_moves_to_revealed_once_patient_discloses_it():
    history = [
        {"role": "nurse", "content": "Are you taking your medication regularly?"},
        {"role": "patient", "content": "Actually, I admit I stopped taking my medication a few weeks ago."},
    ]
    hints = SemanticHints(confirmed_hidden_reveals=frozenset({"previous medication non-compliance"}))
    state = derive_patient_state(CARD, history, semantic_hints=hints)

    assert "previous medication non-compliance" in state.revealed_information
    assert "previous medication non-compliance" not in state.hidden_information


def test_a_lexical_candidate_alone_never_becomes_revealed():
    # The Step 12B QA finding itself: a candidate turn with NO semantic
    # confirmation must stay hidden, never default to revealed.
    history = [
        {"role": "nurse", "content": "Are you taking your medication regularly?"},
        {"role": "patient", "content": "Actually, I admit I stopped taking my medication a few weeks ago."},
    ]
    state = derive_patient_state(CARD, history)  # no hints at all

    assert "previous medication non-compliance" not in state.revealed_information
    assert "previous medication non-compliance" in state.hidden_information


# ── 3. No accidental duplication ────────────────────────────────────────

def test_already_revealed_information_is_not_presented_as_hidden_again():
    history = [
        {"role": "nurse", "content": "Are you taking your medication regularly?"},
        {"role": "patient", "content": "I admit I stopped taking my medication a few weeks ago."},
        {"role": "nurse", "content": "How are you feeling about the surgery today?"},
        {"role": "patient", "content": "Still nervous, but ready."},
    ]
    hints = SemanticHints(confirmed_hidden_reveals=frozenset({"previous medication non-compliance"}))
    state = derive_patient_state(CARD, history, semantic_hints=hints)

    assert state.hidden_information == []
    assert state.revealed_information == ["previous medication non-compliance"]
    prompt = render_patient_state_prompt(state)
    assert "nothing to hide" in prompt
    assert "previous medication non-compliance" in prompt.split("Still hidden")[0]


# ── 4. Emotional state persistence across turns ─────────────────────────

def test_baseline_emotion_is_stable_across_turns():
    state_turn1 = derive_patient_state(CARD, [])
    state_turn2 = derive_patient_state(CARD, [
        {"role": "nurse", "content": "Hello, how are you?"},
        {"role": "patient", "content": "A bit nervous."},
    ])

    assert state_turn1.baseline_emotion == state_turn2.baseline_emotion == "anxious"


# ── 5. Trigger tracking persists once fired ─────────────────────────────

def test_fired_emotional_trigger_stays_fired_in_later_turns():
    history_after_trigger = [
        {"role": "nurse", "content": "I understand you're worried about the surgery."},
        {"role": "patient", "content": "Yes, I'm terrified something will go wrong."},
    ]
    state = derive_patient_state(CARD, history_after_trigger)
    assert state.fired_emotional_triggers == ["fear about surgery"]
    assert state.emotional_intensity == "heightened"

    # Turn 3: candidate dismisses the fear and moves on to an unrelated topic --
    # the trigger must still show as fired because it's still in the transcript.
    history_turn3 = history_after_trigger + [
        {"role": "nurse", "content": "Don't worry about that, let's talk about your diet instead."},
        {"role": "patient", "content": "Okay, if you say so."},
    ]
    state_turn3 = derive_patient_state(CARD, history_turn3)
    assert state_turn3.fired_emotional_triggers == ["fear about surgery"]
    assert state_turn3.emotional_intensity == "heightened"


# ── 6. Prompt integration: both pipelines receive the same conceptual state ─

def test_legacy_pipeline_prompt_includes_conversation_state(monkeypatch):
    captured = {}

    async def fake_call_ai(messages, **kw):
        captured["messages"] = messages
        return {"raw_feedback": "I'm okay, thank you.", "provider_failure": False}

    monkeypatch.setattr(ai_scoring, "_call_ai", fake_call_ai)

    history = [
        {"role": "nurse", "content": "Are you taking your medication regularly?"},
        {"role": "patient", "content": "I admit I stopped taking my medication a few weeks ago."},
    ]
    _run(ai_scoring.get_patient_response(CARD, history, "How do you feel about tomorrow?"))

    system_prompt = captured["messages"][0]["content"]
    assert "CONVERSATION STATE" in system_prompt
    assert "previous medication non-compliance" in system_prompt
    assert "fear about surgery" in system_prompt


def test_realtime_pipeline_prompt_includes_conversation_state():
    prompt = srt._build_realtime_system_prompt(CARD)

    assert "CONVERSATION STATE" in prompt
    assert "previous medication non-compliance" in prompt
    assert "When can I go home after the surgery?" in prompt
    # No unrendered f-string braces from the new block either.
    assert "{" not in prompt and "}" not in prompt


# ── 7. Scenario compatibility: old/minimal scenarios don't crash ───────────

def test_old_schema_scenario_degrades_to_safe_defaults_without_crashing():
    state = derive_patient_state(OLD_SCHEMA_CARD, [])

    assert state.hidden_information == []  # no information_to_withhold key at all
    assert state.concerns_unresolved == ["Will I need an operation?"]  # falls back to "concerns" key
    assert state.fired_emotional_triggers == []
    assert state.baseline_emotion == "Cooperative"

    prompt = srt._build_realtime_system_prompt(OLD_SCHEMA_CARD)
    assert "CONVERSATION STATE" in prompt
    assert "{" not in prompt and "}" not in prompt


def test_empty_card_does_not_crash():
    state = derive_patient_state({}, [])
    assert state.hidden_information == []
    assert state.concerns_unresolved == []
    assert state.baseline_emotion == "Cooperative"


# ── 8. Reset: a new session doesn't inherit the previous session's state ───

def test_new_session_starts_clean_regardless_of_a_prior_sessions_history():
    prior_session_history = [
        {"role": "nurse", "content": "Are you taking your medication regularly?"},
        {"role": "patient", "content": "I admit I stopped taking my medication a few weeks ago."},
    ]
    derive_patient_state(CARD, prior_session_history)  # simulate a finished session

    fresh_session_state = derive_patient_state(CARD, [])  # new session, no history yet
    assert fresh_session_state.hidden_information == ["previous medication non-compliance"]
    assert fresh_session_state.revealed_information == []


# ── 9. Task 1: hidden-info candidate pre-filter (Step 8/9 QA gap fix) ──────
# Golden cases (semantic_evidence_golden_cases.HIDDEN_INFO_CANDIDATE_CASES)
# exercise _hidden_info_candidate directly -- the lexical pre-filter that
# feeds semantic verification. Step 12B (Rule 1) decoupled "became a
# candidate" from "ended up revealed": derive_patient_state's
# revealed_information now only reflects real semantic confirmation (see the
# reveal-tracking tests above), so candidate detection is asserted here at
# its own layer instead of via that field. The semantic-verification-level
# cases (HIDDEN_INFO_CASES) are unaffected and still covered in
# test_semantic_evidence.py.
import pytest

from semantic_evidence_golden_cases import HIDDEN_INFO_CANDIDATE_CASES


@pytest.mark.parametrize("case", HIDDEN_INFO_CANDIDATE_CASES, ids=[c["name"] for c in HIDDEN_INFO_CANDIDATE_CASES])
def test_hidden_info_candidate_golden_cases(case):
    became_candidate = _hidden_info_candidate(case["item"], case["statement"])
    assert became_candidate is case["expected_candidate"]


def test_apostrophe_paraphrase_was_the_actual_step9_qa_miss():
    # Concretely: before Task 1's normalization fix, this candidate check
    # never fired (item keyword "uncle's" != turn word "uncle" as literal
    # strings) and verify_hidden_reveal was never even called -- the exact
    # gap Step 8/9 QA found. It must fire now.
    item = "childhood trauma involving an uncle's painful injections"
    statement = "When I was a kid, my uncle used to give me those huge glass syringes."
    assert _hidden_info_candidate(item, statement) is True
