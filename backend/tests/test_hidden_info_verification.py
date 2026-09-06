"""Step 12B golden tests: hidden-information candidate/verification pipeline.

Covers the real QA finding (a lexical false-positive at one turn masking a
genuine disclosure at a later turn) and the surrounding rules the fix must
hold under: candidate != revealed, every relevant candidate turn gets
verified, a false positive can't block a later real disclosure, provider
failures stay conservative, and the whole thing is auditable end to end.

Same style as test_semantic_evidence.py / test_speaking_evidence.py:
_call_ai is monkeypatched, no live network/model call (Sonnet validation is
explicitly out of scope for this step -- see the module docstring in
semantic_evidence.py).
"""
import asyncio

import pytest

import app.services.ai_scoring as ai_scoring
import app.services.semantic_evidence as semantic_evidence
from app.services.evidence_reconciliation import reconcile_evidence
from app.services.patient_state import SemanticHints, derive_patient_state
from app.services.speaking_evidence import build_speaking_evidence, build_speaking_evidence_with_semantics


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_semantic_cache():
    semantic_evidence._reveal_cache.clear()
    yield
    semantic_evidence._reveal_cache.clear()


def _statement_under_test(prompt: str) -> str:
    """The prompt also embeds RECENT CONVERSATION CONTEXT (prior turns), so
    matching the whole prompt against an earlier turn's text would false-hit
    on a later turn's verification call. Pulls out just the "PATIENT'S
    STATEMENT TO CHECK" section, which is what's actually being judged."""
    marker = "PATIENT'S STATEMENT TO CHECK:\n\""
    start = prompt.index(marker) + len(marker)
    end = prompt.index('"', start)
    return prompt[start:end]


def _mock_call_ai_by_statement(verdicts: dict[str, bool]):
    """Routes each verification call to a verdict keyed by the exact
    statement text under test -- lets one test mock different answers for
    different candidate turns of the same item."""
    async def fake(messages, **kwargs):
        statement = _statement_under_test(messages[0]["content"])
        if statement not in verdicts:
            raise AssertionError(f"no mocked verdict for statement: {statement!r}")
        return {"revealed": verdicts[statement]}
    return fake


def _mock_call_ai_raises_for(needles: set[str], otherwise: dict[str, bool] | None = None):
    async def fake(messages, **kwargs):
        statement = _statement_under_test(messages[0]["content"])
        if statement in needles:
            raise RuntimeError("simulated provider outage")
        if statement not in (otherwise or {}):
            raise AssertionError(f"no mocked verdict for statement: {statement!r}")
        return {"revealed": otherwise[statement]}
    return fake


ITEM = "childhood trauma involving an uncle's painful injections"
TURN5_TEXT = "The daily injections are painful and leave bruises."
TURN10_TEXT = "When I was a kid, I watched my uncle give me those injections."
CARD = {"mood": "guarded", "information_to_withhold": [ITEM]}


def _history_with(*texts: str) -> list[dict]:
    return [{"role": "patient", "content": t} for t in texts]


# ── Test 1: candidate does NOT equal revealed ────────────────────────────

def test_1_candidate_does_not_equal_revealed():
    history = _history_with(TURN5_TEXT)
    # No semantic hints at all -- pure candidate detection, no verification.
    state = derive_patient_state(CARD, history)
    assert ITEM in state.hidden_information
    assert ITEM not in state.revealed_information

    ev = build_speaking_evidence(CARD, history)
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.candidate_detected is True
    assert outcome.final_status == "hidden"


# ── Test 2: false-positive early candidate + genuine later disclosure ───
# The exact real QA scenario from the Step 12B spec.

def test_2_false_positive_early_candidate_does_not_mask_later_disclosure(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai_by_statement({
        TURN5_TEXT: False, TURN10_TEXT: True,
    }))
    history = _history_with(TURN5_TEXT, TURN10_TEXT)

    hints = _run(semantic_evidence.hidden_info_hints(CARD, history))
    assert ITEM in hints.confirmed_hidden_reveals
    assert hints.candidate_turn_status[ITEM][0] == "verified_not_revealed"
    assert hints.candidate_turn_status[ITEM][1] == "verified_revealed"
    assert hints.confirmed_reveal_turn[ITEM] == 1

    state = derive_patient_state(CARD, history, semantic_hints=hints)
    assert ITEM in state.revealed_information
    assert ITEM not in state.hidden_information


# ── Test 3: multiple candidate turns ─────────────────────────────────────

def test_3_multiple_candidate_turns_all_tracked():
    history = _history_with(TURN5_TEXT, TURN10_TEXT, "More about the injections later.")
    turns = semantic_evidence._candidate_turns(ITEM, history)
    assert [idx for idx, _ in turns] == [0, 1, 2]


# ── Test 4: all candidates verified_not_revealed ─────────────────────────

def test_4_all_candidates_not_revealed_stays_hidden(monkeypatch):
    other_text = "Injections again, still just painful."
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai_by_statement({
        TURN5_TEXT: False, other_text: False,
    }))
    history = _history_with(TURN5_TEXT, other_text)

    hints = _run(semantic_evidence.hidden_info_hints(CARD, history))
    assert ITEM not in hints.confirmed_hidden_reveals
    assert hints.verification_status[ITEM] == "verified_not_revealed"

    ev = _run(build_speaking_evidence_with_semantics(CARD, history))
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.final_status == "hidden"
    assert len(outcome.candidate_turns) == 2
    assert all(ct.verification_status == "verified_not_revealed" for ct in outcome.candidate_turns)


# ── Test 5: one verified_revealed among several ──────────────────────────

def test_5_one_reveal_among_several_candidates(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai_by_statement({
        TURN5_TEXT: False, TURN10_TEXT: True,
    }))
    history = _history_with(TURN5_TEXT, TURN10_TEXT)

    ev = _run(build_speaking_evidence_with_semantics(CARD, history))
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.final_status == "revealed"
    assert outcome.turn_index == 1
    assert outcome.evidence_text == TURN10_TEXT
    assert [ct.verification_status for ct in outcome.candidate_turns] == [
        "verified_not_revealed", "verified_revealed",
    ]


# ── Test 6: provider failure on early candidate + verified reveal later ──

def test_6_early_provider_failure_does_not_block_later_confirmed_reveal(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai_raises_for(
        {TURN5_TEXT}, otherwise={TURN10_TEXT: True},
    ))
    history = _history_with(TURN5_TEXT, TURN10_TEXT)

    hints = _run(semantic_evidence.hidden_info_hints(CARD, history))
    assert hints.candidate_turn_status[ITEM][0] == "provider_failure"
    assert hints.candidate_turn_status[ITEM][1] == "verified_revealed"
    assert ITEM in hints.confirmed_hidden_reveals
    assert hints.confirmed_reveal_turn[ITEM] == 1


# ── Test 7: verified non-reveal earlier + provider failure later ────────
# Do not let an uncertain later candidate overturn a verified earlier negative.

def test_7_later_provider_failure_does_not_overturn_earlier_verified_negative(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai_raises_for(
        {TURN10_TEXT}, otherwise={TURN5_TEXT: False},
    ))
    history = _history_with(TURN5_TEXT, TURN10_TEXT)

    hints = _run(semantic_evidence.hidden_info_hints(CARD, history))
    assert ITEM not in hints.confirmed_hidden_reveals
    assert hints.verification_status[ITEM] == "verified_not_revealed"

    state = derive_patient_state(CARD, history, semantic_hints=hints)
    assert ITEM in state.hidden_information


# ── Test 8: multiple verified reveals -- deterministic attribution ──────

def test_8_multiple_verified_reveals_pick_earliest():
    third_text = "And another mention of the injections and my uncle."
    history = _history_with(TURN5_TEXT, TURN10_TEXT, third_text)

    async def fake(messages, **kwargs):
        statement = _statement_under_test(messages[0]["content"])
        return {"revealed": statement != TURN5_TEXT}  # both TURN10_TEXT and third_text reveal

    import unittest.mock
    with unittest.mock.patch.object(ai_scoring, "_call_ai", fake):
        hints = _run(semantic_evidence.hidden_info_hints(CARD, history))

    assert ITEM in hints.confirmed_hidden_reveals
    # Earliest verified reveal wins -- turn 2 (third_text) is never even
    # processed once turn 1 confirms (Step 11 cost control / Rule 6).
    assert hints.confirmed_reveal_turn[ITEM] == 1
    assert 2 not in hints.candidate_turn_status[ITEM]


# ── Test 9: no candidates ────────────────────────────────────────────────

def test_9_no_candidates_stays_not_called():
    history = _history_with("I'd just like some water, thank you.")
    hints = _run(semantic_evidence.hidden_info_hints(CARD, history))
    assert hints.verification_status.get(ITEM) is None
    assert hints.candidate_turn_status.get(ITEM, {}) == {}

    ev = build_speaking_evidence(CARD, history)
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.candidate_detected is False
    assert outcome.verification_status == "not_called"
    assert outcome.candidate_turns == []


# ── Test 10: empty/minimal hidden-information list ───────────────────────

def test_10_empty_hidden_info_list_does_not_crash():
    card = {"mood": "anxious", "information_to_withhold": []}
    history = _history_with("Hello, how are you?")
    hints = _run(semantic_evidence.hidden_info_hints(card, history))
    assert hints.confirmed_hidden_reveals == frozenset()

    ev = _run(build_speaking_evidence_with_semantics(card, history))
    assert ev.hidden_info_outcomes == []


# ── Test 11: deterministic reconstruction ────────────────────────────────

def test_11_deterministic_reconstruction(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai_by_statement({
        TURN5_TEXT: False, TURN10_TEXT: True,
    }))
    history = _history_with(TURN5_TEXT, TURN10_TEXT)
    first = _run(build_speaking_evidence_with_semantics(CARD, history))
    second = _run(build_speaking_evidence_with_semantics(CARD, list(history)))
    assert first.model_dump() == second.model_dump()


# ── Test 12: realtime (incremental) state behavior ───────────────────────
# Mirrors how speaking_realtime.py calls hidden_info_hints after every turn
# with `prior` carried forward -- a turn already processed must never be
# re-verified, and a false-positive rejection at an early turn must not
# block a genuine reveal that arrives in a LATER incremental call.

def test_12_incremental_live_calls_never_reverify_and_catch_later_reveal(monkeypatch):
    calls: list[str] = []

    async def fake(messages, **kwargs):
        prompt = messages[0]["content"]
        calls.append(prompt)
        statement = _statement_under_test(prompt)
        return {"revealed": statement != TURN5_TEXT}

    monkeypatch.setattr(ai_scoring, "_call_ai", fake)

    # Turn 5 arrives first (live, one turn at a time).
    history_after_turn5 = _history_with(TURN5_TEXT)
    hints = _run(semantic_evidence.hidden_info_hints(CARD, history_after_turn5))
    assert ITEM not in hints.confirmed_hidden_reveals
    assert len(calls) == 1

    # Turn 10 arrives later, in a SEPARATE call with prior carried forward.
    history_after_turn10 = _history_with(TURN5_TEXT, TURN10_TEXT)
    hints = _run(semantic_evidence.hidden_info_hints(CARD, history_after_turn10, prior=hints))
    assert ITEM in hints.confirmed_hidden_reveals
    assert hints.confirmed_reveal_turn[ITEM] == 1
    # Only ONE new call was made (turn 10) -- turn 5 was never re-verified.
    assert len(calls) == 2

    state = derive_patient_state(CARD, history_after_turn10, semantic_hints=hints)
    assert ITEM in state.revealed_information


# ── Test 13: admin evidence representation ───────────────────────────────

def test_13_admin_evidence_shows_every_candidate_turn_not_collapsed(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai_by_statement({
        TURN5_TEXT: False, TURN10_TEXT: True,
    }))
    history = _history_with(TURN5_TEXT, TURN10_TEXT)
    ev = _run(build_speaking_evidence_with_semantics(CARD, history))
    unified = reconcile_evidence(ev)

    outcome = unified.hidden_info_outcomes[0]
    assert outcome.final_status == "revealed"
    assert len(outcome.candidate_turns) == 2
    assert outcome.candidate_turns[0].turn_index == 0
    assert outcome.candidate_turns[0].verification_status == "verified_not_revealed"
    assert outcome.candidate_turns[1].turn_index == 1
    assert outcome.candidate_turns[1].verification_status == "verified_revealed"


# ── Test 14: session isolation ────────────────────────────────────────────

def test_14_session_isolation_between_independent_calls(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai_by_statement({
        TURN5_TEXT: False, TURN10_TEXT: True,
    }))
    history_a = _history_with(TURN5_TEXT)
    history_b = _history_with(TURN10_TEXT)

    hints_a = _run(semantic_evidence.hidden_info_hints(CARD, history_a))
    hints_b = _run(semantic_evidence.hidden_info_hints(CARD, history_b))

    assert ITEM not in hints_a.confirmed_hidden_reveals
    assert ITEM in hints_b.confirmed_hidden_reveals
    # Re-running session A again gives the identical result -- no leakage
    # from session B's confirmed state.
    hints_a_again = _run(semantic_evidence.hidden_info_hints(CARD, history_a))
    assert hints_a_again.confirmed_hidden_reveals == hints_a.confirmed_hidden_reveals


# ── Step 17: the real QA fixture, offline ────────────────────────────────

def test_step17_real_qa_fixture_turn5_false_positive_turn10_12_genuine_reveal(monkeypatch):
    turn10_12_text = "When I was a kid, my uncle used to give me those injections and it still upsets me."
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai_by_statement({
        TURN5_TEXT: False, turn10_12_text: True,
    }))
    history = [
        {"role": "nurse", "content": "Can you tell me about your daily routine?"},
        {"role": "patient", "content": TURN5_TEXT},
        {"role": "nurse", "content": "Is there anything about the injections that bothers you specifically?"},
        {"role": "patient", "content": turn10_12_text},
    ]

    ev = _run(build_speaking_evidence_with_semantics(CARD, history))
    outcome = ev.hidden_info_outcomes[0]

    assert outcome.final_status == "revealed"
    assert outcome.turn_index == 3  # the turn 10-12 disclosure, not turn 5
    assert outcome.evidence_text == turn10_12_text
    turn_by_index = {ct.turn_index: ct.verification_status for ct in outcome.candidate_turns}
    assert turn_by_index[1] == "verified_not_revealed"
    assert turn_by_index[3] == "verified_revealed"
