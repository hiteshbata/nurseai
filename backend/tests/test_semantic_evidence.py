"""Tests for the Semantic Evidence Layer (Step 7).

_call_ai is monkeypatched exactly like test_patient_state.py already does
for this codebase (see that file's module docstring) -- no live network,
no real model call. This means these tests verify the PLUMBING: prompt
construction, response parsing, target validation, conservative-default
behavior on failure, and source labeling. They do NOT verify that a real
model actually understands a given paraphrase or hidden-info case --
that requires a live QA pass against the real `speaking_semantic_evidence`
purpose (same as how Step 6's findings were only caught by a real
realtime session), which this sandboxed environment has no API access to
run. semantic_evidence_golden_cases.py's `expected` values describe what a
correctly-functioning classifier should return; the table-driven tests
below feed those exact values back through a mocked _call_ai to confirm
the module correctly carries them through end to end -- they are not a
claim of real-model accuracy.
"""
import asyncio

import pytest

import app.services.ai_scoring as ai_scoring
import app.services.semantic_evidence as semantic_evidence
from app.services.patient_state import SemanticHints, derive_patient_state
from semantic_evidence_golden_cases import (
    CONCERN_ADDRESSING_CASES,
    CONCERN_EXPLORATION_CASES,
    HIDDEN_INFO_CASES,
    RESOLUTION_CASES,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_semantic_cache():
    semantic_evidence._reveal_cache.clear()
    yield
    semantic_evidence._reveal_cache.clear()


def _mock_call_ai(response: dict | None, *, raise_error: bool = False):
    async def fake(*args, **kwargs):
        if raise_error:
            raise RuntimeError("simulated provider outage")
        if response is None:
            return {"raw_feedback": "I'm sorry, the AI service is temporarily unavailable.", "provider_failure": True}
        return dict(response)
    return fake


CARD = {
    "mood": "anxious",
    "questions_to_ask": ["fear of the injections", "worry about missing work"],
    "information_to_withhold": ["childhood trauma involving an uncle's painful injections"],
}


# ── Golden cases, table-driven (Step 16) ─────────────────────────────────

@pytest.mark.parametrize("case", CONCERN_EXPLORATION_CASES, ids=[c["name"] for c in CONCERN_EXPLORATION_CASES])
def test_golden_concern_exploration_cases(monkeypatch, case):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai(case["expected"]))
    result = _run(semantic_evidence.classify_nurse_concern_event(case["utterance"], case["concerns"]))
    assert result == case["expected"]


@pytest.mark.parametrize("case", CONCERN_ADDRESSING_CASES, ids=[c["name"] for c in CONCERN_ADDRESSING_CASES])
def test_golden_concern_addressing_cases(monkeypatch, case):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai(case["expected"]))
    result = _run(semantic_evidence.classify_nurse_concern_event(case["utterance"], case["concerns"]))
    assert result == case["expected"]


@pytest.mark.parametrize("case", HIDDEN_INFO_CASES, ids=[c["name"] for c in HIDDEN_INFO_CASES])
def test_golden_hidden_info_cases(monkeypatch, case):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"revealed": case["expected_revealed"]}))
    result = _run(semantic_evidence.verify_hidden_reveal(case["item"], case["statement"]))
    assert result is case["expected_revealed"]


@pytest.mark.parametrize("case", RESOLUTION_CASES, ids=[c["name"] for c in RESOLUTION_CASES])
def test_golden_resolution_cases(monkeypatch, case):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"resolved": case["expected_resolved"]}))
    result = _run(semantic_evidence.classify_patient_resolution(case["concern"], case["nurse_turn"], case["patient_turn"]))
    assert result is case["expected_resolved"]


# ── Step 15 explicit tests ────────────────────────────────────────────

# Test 1: paraphrased concern exploration recognized.
def test_1_paraphrased_concern_exploration(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai(
        {"event": "concern_exploration", "target_concern": "fear of the injections"}
    ))
    result = _run(semantic_evidence.classify_nurse_concern_event(
        "Can you tell me what worries you most about the injections?", ["fear of the injections"],
    ))
    assert result == {"event": "concern_exploration", "target_concern": "fear of the injections"}


# Test 2: false-positive hidden information rejected.
def test_2_hidden_info_false_positive_rejected(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"revealed": False}))
    result = _run(semantic_evidence.verify_hidden_reveal(
        "childhood trauma involving uncle's injections", "The injections are painful and leave bruises.",
    ))
    assert result is False


# Test 3: true hidden-information revelation confirmed.
def test_3_hidden_info_true_reveal(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"revealed": True}))
    result = _run(semantic_evidence.verify_hidden_reveal(
        "childhood trauma involving uncle's injections",
        "When I was young, my uncle used to give me injections and it was extremely painful.",
    ))
    assert result is True


# Test 4: concern addressing classified with correct target.
def test_4_concern_addressing(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai(
        {"event": "concern_addressing", "target_concern": "fear of the injections"}
    ))
    result = _run(semantic_evidence.classify_nurse_concern_event(
        "The new needle is only 4mm long, so it is much smaller than the one you remember.",
        ["fear of the injections"],
    ))
    assert result["event"] == "concern_addressing"
    assert result["target_concern"] == "fear of the injections"


# Test 5: patient resolution signal is evidence, not an automatic PatientState
# override on its own -- derive_patient_state only promotes to "resolved"
# when the concern already reached "addressed" (Step 6 multi-signal rule).
def test_5_resolution_signal_needs_addressed_first():
    hints = SemanticHints(resolved_concerns=frozenset({"fear of the injections"}))
    history_not_yet_addressed = [
        {"role": "patient", "content": "I'm frightened of the injections."},
    ]
    state = derive_patient_state(CARD, history_not_yet_addressed, semantic_hints=hints)
    # concern was only "raised", never "addressed" -- semantic resolution
    # evidence alone must not skip it straight to "resolved".
    assert state.concern_status["fear of the injections"] == "raised"


# Test 5b (Task 3/5): full reopen -> resolved-again lifecycle. The
# deterministic-only auto-graduation rule ("addressed" + never re-raised
# again over the rest of the FULL history) can't do this on its own once a
# concern has already been re-raised once -- it keeps checking against the
# same original addressed_at_idx forever (see speaking_evidence.py's
# documented prefix-recomputation limitation). A fresh semantic patient-side
# resolution signal is the second, independent path Step 6/7 added for
# exactly this: it doesn't care about re-raise history, only that the
# concern is currently at/above "addressed".
def test_5b_reopened_concern_can_be_resolved_again_via_semantic_signal():
    concern = "fear of the injections"
    history = [
        {"role": "patient", "content": "I'm frightened of the injections."},
        {"role": "nurse", "content": "The needle is only 4mm, much smaller than you remember."},
        {"role": "patient", "content": "Actually I'm still frightened of the injections."},  # reopens
        {"role": "nurse", "content": "Let me reassure you again -- it's a very different needle now."},
        {"role": "patient", "content": "Okay, I think I believe you now."},
    ]
    hints_addressing = SemanticHints(extra_nurse_events={
        1: [{"event": "concern_addressing", "evidence": "...", "target_concern": concern}],
        3: [{"event": "concern_addressing", "evidence": "...", "target_concern": concern}],
    })
    state = derive_patient_state(CARD, history, semantic_hints=hints_addressing)
    # Re-raised right after the first addressing -- stays "addressed", not
    # auto-resolved, and the second addressing can't move it further on its
    # own (already at "addressed").
    assert state.concern_status[concern] == "addressed"

    hints_resolved_again = SemanticHints(
        extra_nurse_events=hints_addressing.extra_nurse_events,
        resolved_concerns=frozenset({concern}),
    )
    state_resolved_again = derive_patient_state(CARD, history, semantic_hints=hints_resolved_again)
    assert state_resolved_again.concern_status[concern] == "resolved"


# Step 12A Task 7: a THIRD cycle -- reopened a second time, then resolved a
# second time. Pure deterministic prefix-recomputation cannot do this at all
# (see test_pure_deterministic_recomputation_shows_only_one_reopen_ever in
# test_speaking_evidence.py for why: addressed_at_idx is fixed at the first
# addressing turn forever). The semantic resolved_concerns hint from Test 5b
# has no such limit -- it is evaluated fresh against whatever concern_status
# the rest of the history already computed, so re-applying it after a SECOND
# re-raise resolves the concern again exactly the same way.
def test_5c_second_reopen_can_also_be_resolved_again_via_semantic_signal():
    concern = "fear of the injections"
    history = [
        {"role": "patient", "content": "I'm frightened of the injections."},
        {"role": "nurse", "content": "The needle is only 4mm, much smaller than you remember."},
        {"role": "patient", "content": "Actually I'm still frightened of the injections."},  # reopens (1st)
        {"role": "nurse", "content": "Let me reassure you again -- it's a very different needle now."},
        {"role": "patient", "content": "Okay, I think I believe you now."},
        {"role": "patient", "content": "Actually, thinking about it, I'm frightened of the injections again."},  # reopens (2nd)
        {"role": "nurse", "content": "Let's go through it one more time, slowly, together."},
        {"role": "patient", "content": "Alright, I think I can manage it now."},
    ]
    hints_addressing = SemanticHints(extra_nurse_events={
        1: [{"event": "concern_addressing", "evidence": "...", "target_concern": concern}],
        3: [{"event": "concern_addressing", "evidence": "...", "target_concern": concern}],
        6: [{"event": "concern_addressing", "evidence": "...", "target_concern": concern}],
    })
    # Without a resolution signal, three addressings + two re-raises still
    # just sits at "addressed" -- addressing alone never re-resolves it.
    state = derive_patient_state(CARD, history, semantic_hints=hints_addressing)
    assert state.concern_status[concern] == "addressed"

    hints_resolved_third_time = SemanticHints(
        extra_nurse_events=hints_addressing.extra_nurse_events,
        resolved_concerns=frozenset({concern}),
    )
    state_final = derive_patient_state(CARD, history, semantic_hints=hints_resolved_third_time)
    assert state_final.concern_status[concern] == "resolved"


# Test 6: persistent concern stays not resolved.
def test_6_persistent_concern_not_resolved(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"resolved": False}))
    result = _run(semantic_evidence.classify_patient_resolution(
        "fear of the injections", "The needle is only 4mm.", "I'm still very worried.",
    ))
    assert result is False


# Test 7: multiple concerns -- correct target picked, not FIFO-guessed.
def test_7_multiple_concerns_correct_target(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai(
        {"event": "concern_exploration", "target_concern": "fear of the injections"}
    ))
    result = _run(semantic_evidence.classify_nurse_concern_event(
        "What worries you most about the injections specifically?",
        ["worry about missing work", "fear of the injections"],
    ))
    assert result["target_concern"] == "fear of the injections"


# Test 8: source labeling -- deterministic stays deterministic_rule, semantic
# events get semantic_model, verified through the actual state-machine hook.
def test_8_source_labeling():
    hints = SemanticHints(extra_nurse_events={0: [{
        "event": "concern_addressing", "evidence": "...", "target_concern": "fear of the injections",
    }]})
    history = [
        {"role": "nurse", "content": "The needle we use is only 4mm long."},
        {"role": "patient", "content": "I'm still frightened of the injections though."},
    ]
    from app.services.speaking_evidence import build_speaking_evidence
    evidence = build_speaking_evidence(CARD, history)
    # No deterministic phrase matched "The needle we use is only 4mm long" --
    # build_speaking_evidence alone (no hints) sees no candidate_events here.
    assert evidence.candidate_events == []

    # Re-raised in the very next turn, so the deterministic
    # never-re-raised-again auto-graduation to "resolved" doesn't fire --
    # isolates what the semantic "addressed" event itself contributed.
    state = derive_patient_state(CARD, history, semantic_hints=hints)
    assert state.concern_status["fear of the injections"] == "addressed"


# Test 9: a semantic call failure must not break the session -- deterministic
# evidence/state stays fully available.
def test_9_semantic_failure_is_non_fatal(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai(None, raise_error=True))

    reveal_result = _run(semantic_evidence.verify_hidden_reveal("some hidden item", "some statement"))
    assert reveal_result is None

    event_result = _run(semantic_evidence.classify_nurse_concern_event("utterance", ["a concern"]))
    assert event_result is None

    resolution_result = _run(semantic_evidence.classify_patient_resolution("a concern", "nurse turn", "patient turn"))
    assert resolution_result is None

    # And the underlying pipeline keeps working with zero hints -- exactly
    # like the semantic layer was never wired in.
    state = derive_patient_state(CARD, [{"role": "patient", "content": "I'm frightened of the injections."}])
    assert state.concerns_raised == ["fear of the injections"]


# Also cover the provider_failure shape _call_ai itself returns (as opposed
# to a raised exception) -- both must be treated identically (None).
def test_9b_provider_failure_response_is_non_fatal(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai(None))
    result = _run(semantic_evidence.verify_hidden_reveal("item", "statement"))
    assert result is None


# hidden_info_hints must fall back to "stays hidden" (never revealed) when
# the semantic call fails -- the conservative default per Step 7/9, not a
# reversion to trusting the keyword match.
def test_9c_hidden_info_hints_conservative_on_failure(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai(None))
    history = [
        {"role": "patient", "content": "Daily injections are painful and leave bruises."},
    ]
    hints = _run(semantic_evidence.hidden_info_hints(CARD, history))
    item = "childhood trauma involving an uncle's painful injections"
    assert item in hints.rejected_hidden_reveals
    assert item not in hints.confirmed_hidden_reveals

    state = derive_patient_state(CARD, history, semantic_hints=hints)
    assert item not in state.revealed_information
    assert item in state.hidden_information


# Test 10: no hallucinated target -- an unlisted concern string is nulled out.
def test_10_no_hallucinated_target(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai(
        {"event": "concern_exploration", "target_concern": "something not in the concerns list"}
    ))
    result = _run(semantic_evidence.classify_nurse_concern_event(
        "What's worrying you?", ["fear of the injections"],
    ))
    assert result == {"event": "concern_exploration", "target_concern": None}


# ── hidden_info_hints end-to-end (Finding 1's actual worked example) ─────

def test_finding_1_worked_example_not_revealed(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"revealed": False}))
    history = [{"role": "patient", "content": "Daily injections are painful and leave bruises."}]
    hints = _run(semantic_evidence.hidden_info_hints(CARD, history))
    state = derive_patient_state(CARD, history, semantic_hints=hints)
    item = "childhood trauma involving an uncle's painful injections"
    assert item in state.hidden_information
    assert item not in state.revealed_information


def test_finding_1_worked_example_revealed(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"revealed": True}))
    history = [{
        "role": "patient",
        "content": "When I was a child, my uncle gave me injections and they were extremely painful.",
    }]
    hints = _run(semantic_evidence.hidden_info_hints(CARD, history))
    state = derive_patient_state(CARD, history, semantic_hints=hints)
    item = "childhood trauma involving an uncle's painful injections"
    assert item in state.revealed_information
    assert item not in state.hidden_information
