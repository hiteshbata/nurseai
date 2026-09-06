"""Tests for the Speaking Evidence Layer (Step 5).

Every assertion here was checked against build_speaking_evidence's actual
computed output, not hand-derived -- the detectors are keyword-based, so a
test transcript has to literally contain a matched phrase, and the concern
state machine has FIFO/rank-based quirks (see speaking_evidence.py's module
docstring) that aren't obvious from reading the spec alone.
"""
import asyncio

import pytest

import app.services.ai_scoring as ai_scoring
import app.services.semantic_evidence as semantic_evidence
from app.services.speaking_evidence import build_speaking_evidence, build_speaking_evidence_with_semantics


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_semantic_cache():
    # Same cache test_semantic_evidence.py clears -- (item, statement) keyed,
    # so a prior test's mocked verdict would otherwise leak into a later
    # test's supposedly-different mock response.
    semantic_evidence._reveal_cache.clear()
    yield
    semantic_evidence._reveal_cache.clear()

GOLDEN_CARD = {
    "mood": "anxious",
    "questions_to_ask": ["fear of not waking up from the anaesthetic"],
    "emotional_triggers": ["surgery"],
    "information_to_withhold": [],
}

GOLDEN_HISTORY = [
    {"role": "patient", "content": "I'm really frightened about the operation."},
    {"role": "nurse", "content": "I can understand this is worrying you."},
    {"role": "patient", "content": "I'm afraid I won't wake up from the anaesthetic."},
    {"role": "nurse", "content": "Could you tell me more about what worries you most?"},
    {"role": "nurse", "content": "That must be frightening. Let me explain what we know about your anaesthetic care."},
    {"role": "nurse", "content": "Does that make sense to you?"},
    {"role": "patient", "content": "Yes, thank you, that makes sense."},
]

CONCERN = "fear of not waking up from the anaesthetic"


# Test 1: candidate empathy event captured with turn reference.
def test_empathy_event_has_turn_reference():
    ev = build_speaking_evidence(GOLDEN_CARD, GOLDEN_HISTORY)
    empathy = [e for e in ev.candidate_events if e.event == "empathy_acknowledgement"]
    assert len(empathy) == 2
    assert empathy[0].turn_index == 1
    assert empathy[0].evidence_text == "i can understand"
    assert empathy[0].source == "deterministic_rule"


# Test 2: acknowledgement recorded separately from resolution.
def test_acknowledgement_not_flattened_into_resolution():
    ev = build_speaking_evidence(GOLDEN_CARD, GOLDEN_HISTORY)
    outcome = next(c for c in ev.concern_outcomes if c.concern == CONCERN)
    statuses = [h["status"] for h in outcome.history]
    # empathy_acknowledgement (turn 4) never appears as a cause_event in the
    # concern's own history -- it fired after the concern was already past
    # "acknowledged" rank, so _advance() (patient_state.py) correctly no-ops.
    assert "empathy_acknowledgement" not in [h["cause_event"] for h in outcome.history]
    assert statuses != ["resolved"]  # resolution isn't the only/first thing recorded


# Test 3: concern exploration captured.
def test_concern_exploration_captured():
    ev = build_speaking_evidence(GOLDEN_CARD, GOLDEN_HISTORY)
    exploration = [e for e in ev.candidate_events if e.event == "concern_exploration"]
    assert len(exploration) == 1
    assert exploration[0].turn_index == 3
    assert exploration[0].target_concern == CONCERN


# Test 4: understanding check captured independently.
def test_understanding_check_captured():
    ev = build_speaking_evidence(GOLDEN_CARD, GOLDEN_HISTORY)
    checks = [e for e in ev.candidate_events if e.event == "understanding_checked"]
    assert len(checks) == 1
    assert checks[0].turn_index == 5


# Test 5: concern lifecycle correctly represented (raised -> explored -> resolved).
def test_concern_lifecycle():
    ev = build_speaking_evidence(GOLDEN_CARD, GOLDEN_HISTORY)
    outcome = next(c for c in ev.concern_outcomes if c.concern == CONCERN)
    statuses = [h["status"] for h in outcome.history]
    assert statuses == ["raised", "explored", "resolved"]
    assert outcome.history[0]["turn_index"] == 2
    assert outcome.final_status == "resolved"
    assert outcome.resolved is True
    raised_event = next(p for p in ev.patient_events if p.event == "concern_raised")
    assert raised_event.turn_index == 2
    assert raised_event.evidence_text == CONCERN


# Test 5b (Task 3): a concern that resolves, gets re-raised, and reopens is
# recorded as a dated reopening event, not a confusing "resolved -> addressed"
# regression -- see speaking_evidence.py's module docstring LIMITATION and
# ConcernOutcome's own docstring for why the prefix-recomputed history can
# show this at all.
REOPEN_HISTORY = GOLDEN_HISTORY + [
    {"role": "patient", "content": "Actually, I'm still afraid I won't wake up from the anaesthetic."},
]


def test_concern_reopening_is_recorded_not_a_silent_regression():
    ev = build_speaking_evidence(GOLDEN_CARD, REOPEN_HISTORY)
    outcome = next(c for c in ev.concern_outcomes if c.concern == CONCERN)

    statuses = [h["status"] for h in outcome.history]
    assert statuses == ["raised", "explored", "resolved", "addressed"]
    assert outcome.resolved_at_turns == [5]
    assert outcome.reopened_events == [{
        "turn_index": 7,
        "from_status": "resolved",
        "to_status": "addressed",
        "reason": "Actually, I'm still afraid I won't wake up from the anaesthetic.",
    }]
    # Reopened, not silently resolved -- final state reflects the real
    # unresolved concern, not the premature mid-conversation snapshot.
    assert outcome.final_status == "addressed"
    assert outcome.resolved is False


# Step 12A Task 7/17: a SECOND re-raise after the first reopen. This is a
# genuine, real limitation this pass DISCOVERED (not previously documented
# this precisely): addressed_at_idx (patient_state.py's
# _derive_behavioural_state) only ever records the FIRST turn a concern
# reached "addressed", so the "auto-resolve if never re-raised again" check
# always scans forward from that same fixed point. Once any re-raise has
# happened once, it permanently sits inside that scanned window for every
# longer prefix afterward -- so pure deterministic prefix-recomputation can
# show at most ONE reopen per concern, never a second natural
# resolve-then-reopen cycle, no matter how many more times the patient later
# re-raises it. This test locks in that real, current behavior (not a bug
# introduced here) so a future change to the addressed-tracking logic has to
# consciously decide to alter it. See test_5b_reopened_concern_can_be_resolved_again_via_semantic_signal
# in test_semantic_evidence.py for the ONLY path that currently reaches
# resolved a second time -- the semantic resolved_concerns hint.
REOPEN_TWICE_HISTORY = REOPEN_HISTORY + [
    {"role": "nurse", "content": "That must be frightening. Let me explain again -- the anaesthetist monitors you the whole time."},
    {"role": "nurse", "content": "Does that make sense to you now?"},
    {"role": "patient", "content": "Yes... but honestly I'm still afraid I won't wake up from the anaesthetic."},
]


def test_pure_deterministic_recomputation_shows_only_one_reopen_ever():
    ev = build_speaking_evidence(GOLDEN_CARD, REOPEN_TWICE_HISTORY)
    outcome = next(c for c in ev.concern_outcomes if c.concern == CONCERN)

    assert len(outcome.reopened_events) == 1
    assert outcome.reopened_events[0]["turn_index"] == 7
    # The later re-raise (turn 10) never produces a second resolved->reopened
    # transition -- concern_status simply never changes again, exactly the
    # documented limitation above, not a crash or a silently wrong count.
    assert outcome.final_status == "addressed"
    assert outcome.resolved is False


# Test 6: unresolved concern remains unresolved at session end.
def test_unresolved_concern_stays_unresolved():
    card = {"questions_to_ask": ["worried about the diagnosis"], "mood": "anxious"}
    history = [
        {"role": "patient", "content": "I'm worried about the diagnosis, doctor."},
        {"role": "nurse", "content": "Don't worry, you'll be fine."},
    ]
    ev = build_speaking_evidence(card, history)
    outcome = next(c for c in ev.concern_outcomes if c.concern == "worried about the diagnosis")
    assert outcome.final_status in ("raised", "not_raised")
    assert outcome.resolved is False
    assert "dismissive_response" in [e.event for e in ev.candidate_events]


# Test 7: patient-state transition captured as evidence.
def test_state_transition_captured():
    ev = build_speaking_evidence(GOLDEN_CARD, GOLDEN_HISTORY)
    emotion_transitions = [t for t in ev.state_transitions if t.field == "current_emotion"]
    assert len(emotion_transitions) == 1
    assert emotion_transitions[0].before == "anxious"
    assert emotion_transitions[0].after == "calm"
    assert emotion_transitions[0].turn_index == 1
    assert emotion_transitions[0].cause_event == "empathy_acknowledgement"


# Test 8: jargon event reused and traceable.
def test_jargon_event_reused_and_traceable():
    history = [
        {"role": "nurse", "content": "You have hypertension, we need to monitor it."},
        {"role": "patient", "content": "I do not understand, what does that mean?"},
        {"role": "nurse", "content": "Hypertension means high blood pressure."},
    ]
    ev = build_speaking_evidence({}, history)
    assert len(ev.jargon_evidence) == 1
    j = ev.jargon_evidence[0]
    assert j.term == "hypertension"
    assert j.turn_index == 0
    assert j.patient_reaction == "I do not understand, what does that mean?"
    assert j.clarified_afterward is True
    assert any(e.event == "jargon_used" for e in ev.candidate_events)
    assert ev.interaction_metrics.jargon_events == 1


# Test 9: evidence contains candidate text/source information.
def test_candidate_event_has_text_and_source():
    ev = build_speaking_evidence(GOLDEN_CARD, GOLDEN_HISTORY)
    for e in ev.candidate_events:
        assert e.evidence_text
        assert e.source == "deterministic_rule"
        assert isinstance(e.turn_index, int)


# Test 10: realtime-shaped turn references (role/text -> role/content) are preserved.
def test_realtime_turn_shape_preserved():
    # Mirrors how speaking_realtime.py's _SessionMetrics.recompute_patient_state
    # converts transcript_turns ({"role","text"}) to {"role","content"}.
    realtime_turns = [{"role": "nurse", "text": "I can understand this is worrying you."}]
    converted = [{"role": t["role"], "content": t["text"]} for t in realtime_turns]
    ev = build_speaking_evidence({}, converted)
    assert ev.candidate_events[0].turn_index == 0
    assert ev.candidate_events[0].evidence_text == "i can understand"


# Test 11: legacy conversation produces equivalent evidence concepts.
def test_legacy_shape_equivalent_to_converted_realtime_shape():
    legacy_history = [{"role": "nurse", "content": "I can understand this is worrying you."}]
    realtime_history = [{"role": t["role"], "content": t["text"]} for t in [
        {"role": "nurse", "text": "I can understand this is worrying you."}
    ]]
    assert build_speaking_evidence({}, legacy_history) == build_speaking_evidence({}, realtime_history)


# Test 12: reconnect/reconstruction produces identical evidence.
def test_reconnect_reconstruction_is_deterministic():
    first = build_speaking_evidence(GOLDEN_CARD, GOLDEN_HISTORY)
    second = build_speaking_evidence(GOLDEN_CARD, list(GOLDEN_HISTORY))  # simulate reloaded history
    assert first == second


# Test 13: empty/minimal scenario does not crash.
def test_empty_scenario_does_not_crash():
    ev = build_speaking_evidence({}, [])
    assert ev.candidate_events == []
    assert ev.patient_events == []
    assert ev.concern_outcomes == []
    assert ev.state_transitions == []
    assert ev.jargon_evidence == []
    assert ev.interaction_metrics.turn_counts == {"nurse": 0, "patient": 0, "total": 0}

    ev_none_card = build_speaking_evidence(None, [{"role": "nurse", "content": "Hello there."}])
    assert ev_none_card.interaction_metrics.turn_counts["total"] == 1


# Test 14: session isolation -- two independent calls never share state.
def test_session_isolation():
    history_a = [{"role": "nurse", "content": "I can understand this is worrying you."}]
    history_b = [{"role": "nurse", "content": "Don't worry, you'll be fine."}]
    ev_a = build_speaking_evidence({}, history_a)
    ev_b = build_speaking_evidence({}, history_b)
    assert ev_a.candidate_events[0].event == "empathy_acknowledgement"
    assert ev_b.candidate_events[0].event == "dismissive_response"
    # Rebuilding ev_a again after ev_b must give the same result -- no
    # shared/mutated module state leaking between calls.
    assert build_speaking_evidence({}, history_a) == ev_a


# Test 15 (Step 10): multiple concerns tracked independently, not conflated.
def test_multiple_concerns_tracked_independently():
    card = {
        "questions_to_ask": ["fear of the injections", "worry about missing work"],
        "mood": "anxious",
    }
    history = [
        {"role": "patient", "content": "I'm frightened of the injections."},
        {"role": "patient", "content": "I'm also worried about missing work."},
        {"role": "nurse", "content": "I can understand this is worrying you."},
    ]
    ev = build_speaking_evidence(card, history)
    assert len(ev.concern_outcomes) == 2
    by_concern = {c.concern: c for c in ev.concern_outcomes}
    # FIFO single-target design (speaking_evidence.py's own docstring): only
    # the earliest-raised concern advances on the nurse's empathy turn, the
    # other stays exactly where the patient left it -- not silently merged.
    assert by_concern["fear of the injections"].final_status == "acknowledged"
    assert by_concern["worry about missing work"].final_status == "raised"


# ── Hidden-information turn linkage (Step 10) ────────────────────────────

HIDDEN_ITEM = "childhood trauma involving an uncle's painful injections"
HIDDEN_CARD = {"mood": "anxious", "information_to_withhold": [HIDDEN_ITEM]}


def test_hidden_info_outcome_links_candidate_to_its_turn():
    history = [{"role": "patient", "content": "Daily injections are painful and leave bruises."}]
    ev = build_speaking_evidence(HIDDEN_CARD, history)
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.candidate_detected is True
    assert outcome.turn_index == 0
    assert outcome.evidence_text == "Daily injections are painful and leave bruises."


def test_hidden_info_outcome_no_candidate_has_no_turn_reference():
    history = [{"role": "patient", "content": "I'd like some water please."}]
    ev = build_speaking_evidence(HIDDEN_CARD, history)
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.candidate_detected is False
    assert outcome.turn_index is None
    assert outcome.evidence_text is None


# ── Semantic-layer HiddenInfoOutcome status matrix (Step 10/12) ──────────
# build_speaking_evidence_with_semantics was previously only covered
# indirectly (test_semantic_evidence.py exercises the classifiers it calls,
# test_admin_speaking_evidence.py stubs it out with provider_failure). These
# drive the whole outcome -- candidate_detected/verification_status/
# final_status -- through every status semantic_evidence.hidden_info_hints
# can actually produce, so the inspector's status matrix isn't guesswork.

def _mock_call_ai(response):
    async def fake(*args, **kwargs):
        return dict(response)
    return fake


def _mock_call_ai_raises():
    async def fake(*args, **kwargs):
        raise RuntimeError("simulated provider outage")
    return fake


HIDDEN_HISTORY = [{"role": "patient", "content": "Daily injections are painful and leave bruises."}]


def test_hidden_info_verified_revealed(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"revealed": True}))
    ev = _run(build_speaking_evidence_with_semantics(HIDDEN_CARD, HIDDEN_HISTORY))
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.candidate_detected is True
    assert outcome.verification_status == "verified_revealed"
    assert outcome.final_status == "revealed"
    assert outcome.turn_index == 0


def test_hidden_info_verified_not_revealed(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"revealed": False}))
    ev = _run(build_speaking_evidence_with_semantics(HIDDEN_CARD, HIDDEN_HISTORY))
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.candidate_detected is True
    assert outcome.verification_status == "verified_not_revealed"
    assert outcome.final_status == "hidden"


def test_hidden_info_candidate_not_detected(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"revealed": True}))
    history = [{"role": "patient", "content": "I'd like some water please."}]
    ev = _run(build_speaking_evidence_with_semantics(HIDDEN_CARD, history))
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.candidate_detected is False
    assert outcome.verification_status == "not_called"
    assert outcome.final_status == "hidden"
    assert outcome.turn_index is None


def test_hidden_info_provider_failure(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai_raises())
    ev = _run(build_speaking_evidence_with_semantics(HIDDEN_CARD, HIDDEN_HISTORY))
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.candidate_detected is True
    assert outcome.verification_status == "provider_failure"
    assert outcome.final_status == "hidden"  # conservative default, not a silent miss


def test_hidden_info_parse_failure(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"raw_feedback": "not json"}))
    ev = _run(build_speaking_evidence_with_semantics(HIDDEN_CARD, HIDDEN_HISTORY))
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.verification_status == "parse_failure"
    assert outcome.final_status == "hidden"


def test_hidden_info_token_limit(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"raw_feedback": "truncat", "finish_reason": "length"}))
    ev = _run(build_speaking_evidence_with_semantics(HIDDEN_CARD, HIDDEN_HISTORY))
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.verification_status == "token_limit"
    assert outcome.final_status == "hidden"


def test_hidden_info_malformed_response(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"unexpected_key": True}))
    ev = _run(build_speaking_evidence_with_semantics(HIDDEN_CARD, HIDDEN_HISTORY))
    outcome = ev.hidden_info_outcomes[0]
    assert outcome.verification_status == "malformed_response"
    assert outcome.final_status == "hidden"


# ── Step 12A Task 6: a valid semantic "none" must not erase deterministic evidence ──

CONCERN_CARD = {"mood": "anxious", "questions_to_ask": ["fear of the injections"]}
CONCERN_NONE_HISTORY = [
    {"role": "patient", "content": "I'm frightened of the injections."},
    {"role": "nurse", "content": "Let's go through your paperwork before we start."},
]


def test_semantic_none_does_not_erase_or_add_anything(monkeypatch):
    # classify_nurse_concern_event returns a genuine "none" -- the nurse's
    # turn had nothing to do with the concern. This must add NOTHING to
    # candidate_events (deterministic-only evidence here is exactly the B2
    # cue-response pairing -- concern_raised at turn 0 immediately followed
    # by a nurse turn with no lexical engagement match, Step 21F's
    # cue_response_uncertain tier -- and no "none" placeholder, semantic or
    # otherwise, is ever added on top of it).
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"event": "none", "target_concern": None}))
    deterministic_only = build_speaking_evidence(CONCERN_CARD, CONCERN_NONE_HISTORY)
    with_semantics = _run(build_speaking_evidence_with_semantics(CONCERN_CARD, CONCERN_NONE_HISTORY))

    assert [e.event for e in deterministic_only.candidate_events] == ["cue_response_uncertain"]
    assert with_semantics.candidate_events == deterministic_only.candidate_events
    assert [e for e in with_semantics.candidate_events if e.source == "semantic_model"] == []
    # Concern outcome is identical either way -- semantic "none" contributed nothing.
    assert deterministic_only.concern_outcomes == with_semantics.concern_outcomes


# ── Step 21A: question-behaviour detector wired into candidate_events ────

def test_open_question_captured_as_candidate_event():
    history = [{"role": "nurse", "content": "What brings you in today?"}]
    ev = build_speaking_evidence({}, history)
    q = [e for e in ev.candidate_events if e.event == "open_question"]
    assert len(q) == 1
    assert q[0].turn_index == 0
    assert q[0].target_concern is None


def test_compound_and_leading_question_both_captured_same_turn():
    history = [{"role": "nurse", "content": "You don't smoke, do you? And do you drink alcohol?"}]
    ev = build_speaking_evidence({}, history)
    events = {e.event for e in ev.candidate_events if e.turn_index == 0}
    assert {"compound_question", "leading_question", "closed_question"} <= events


def test_question_event_does_not_affect_cause_event_or_target_concern():
    # Question-type events are an independent signal (D2/D3) -- they must
    # never be attributed to a concern the way empathy/exploration events are.
    card = {"mood": "anxious", "questions_to_ask": ["fear of the injections"]}
    history = [
        {"role": "patient", "content": "I'm frightened of the injections."},
        {"role": "nurse", "content": "What worries you most about the injections?"},
    ]
    ev = build_speaking_evidence(card, history)
    question_events = [e for e in ev.candidate_events if e.event in ("open_question", "closed_question")]
    assert question_events and all(e.target_concern is None for e in question_events)


# ── Step 21B: structure-evidence (C2/C3) detector wired into candidate_events ──

def test_signposting_captured_as_candidate_event():
    history = [{"role": "nurse", "content": "Now let's talk about your medication."}]
    ev = build_speaking_evidence({}, history)
    events = {e.event for e in ev.candidate_events if e.turn_index == 0}
    assert {"signposting_detected", "topic_transition_detected"} <= events


def test_ordinary_transition_word_not_captured_as_signposting():
    history = [{"role": "nurse", "content": "Then I felt better."}]
    ev = build_speaking_evidence({}, history)
    assert not any(e.event.startswith("signposting") for e in ev.candidate_events)


def test_organization_sequence_spans_turns_with_correct_turn_indexes():
    history = [
        {"role": "nurse", "content": "There are three things I'd like to explain."},
        {"role": "patient", "content": "Okay."},
        {"role": "nurse", "content": "First, your medication."},
        {"role": "nurse", "content": "Second, your diet."},
        {"role": "nurse", "content": "Finally, your follow-up."},
    ]
    ev = build_speaking_evidence({}, history)
    markers = [e for e in ev.candidate_events if e.event == "organization_marker"]
    assert [m.turn_index for m in markers] == [0, 2, 3, 4]


def test_lone_ordinal_marker_is_partial():
    history = [{"role": "nurse", "content": "First, let's look at your chart."}]
    ev = build_speaking_evidence({}, history)
    partial = [e for e in ev.candidate_events if e.event == "organization_marker_partial"]
    assert len(partial) == 1 and partial[0].turn_index == 0


def test_question_and_signpost_same_turn_both_captured():
    # question_behaviour classifies open/closed off the text UP TO the first
    # "?" as one clause -- put the question first so it stays its own clause,
    # independent of the signpost sentence that follows.
    history = [{"role": "nurse", "content": "How often are you taking it? Now let's talk about your diet."}]
    ev = build_speaking_evidence({}, history)
    events = {e.event for e in ev.candidate_events if e.turn_index == 0}
    assert "signposting_detected" in events
    assert "open_question" in events


# ── Step 21H: attentiveness-evidence (A2) detector wired into candidate_events ──

def test_acknowledgement_captured_as_candidate_event():
    history = [{"role": "nurse", "content": "I see."}]
    ev = build_speaking_evidence({}, history)
    events = [e for e in ev.candidate_events if e.event == "attentive_acknowledgement"]
    assert len(events) == 1 and events[0].turn_index == 0


def test_reflective_response_captured_with_related_patient_turn():
    history = [
        {"role": "patient", "content": "I'm worried about the injections."},
        {"role": "nurse", "content": "You're worried the injections may be painful."},
    ]
    ev = build_speaking_evidence({}, history)
    events = [e for e in ev.candidate_events if e.event == "reflective_response"]
    assert len(events) == 1
    assert events[0].turn_index == 1
    assert events[0].related_patient_turns == [0]


def test_clinical_i_understand_not_captured_as_acknowledgement():
    history = [{"role": "nurse", "content": "I understand the medication schedule."}]
    ev = build_speaking_evidence({}, history)
    assert not any(e.event.startswith("attentive_acknowledgement") for e in ev.candidate_events)


def test_acknowledgement_and_dismissive_can_coexist_in_same_session():
    history = [
        {"role": "patient", "content": "I'm scared."},
        {"role": "nurse", "content": "I see."},
        {"role": "patient", "content": "I'm still worried about the pain."},
        {"role": "nurse", "content": "Don't worry, you'll be fine."},
    ]
    ev = build_speaking_evidence({}, history)
    events = {e.event for e in ev.candidate_events}
    assert "attentive_acknowledgement" in events
    assert "dismissive_response" in events


# ── Step 21I: nonjudgmental-evidence (A3) detector wired into candidate_events ──

def test_potentially_judgmental_captured_as_candidate_event():
    history = [
        {"role": "patient", "content": "I stopped taking the medication because it was painful."},
        {"role": "nurse", "content": "You should have continued it."},
    ]
    ev = build_speaking_evidence({}, history)
    events = [e for e in ev.candidate_events if e.event == "potentially_judgmental"]
    assert len(events) == 1
    assert events[0].turn_index == 1
    assert events[0].related_patient_turns == [0]


def test_supportive_nonjudgmental_captured_as_candidate_event():
    history = [{"role": "nurse", "content": "It's understandable that you struggled with this."}]
    ev = build_speaking_evidence({}, history)
    events = [e for e in ev.candidate_events if e.event == "supportive_nonjudgmental"]
    assert len(events) == 1


def test_clinical_need_to_not_captured_as_judgmental():
    history = [{"role": "nurse", "content": "You need to take this medication twice daily."}]
    ev = build_speaking_evidence({}, history)
    assert not any(e.event == "potentially_judgmental" for e in ev.candidate_events)


def test_a3_and_a4_can_coexist_in_same_session():
    history = [
        {"role": "patient", "content": "I'm scared about the surgery."},
        {"role": "nurse", "content": "I can understand you feeling that way."},
        {"role": "patient", "content": "I didn't take the medication because it hurt."},
        {"role": "nurse", "content": "You should have continued it."},
    ]
    ev = build_speaking_evidence({}, history)
    events = {e.event for e in ev.candidate_events}
    assert "empathy_acknowledgement" in events
    assert "potentially_judgmental" in events


def test_no_model_call_for_nonjudgmental_detection():
    history = [{"role": "nurse", "content": "You should have continued it."}]
    ev = build_speaking_evidence({}, history)
    events = [e for e in ev.candidate_events if e.event == "potentially_judgmental"]
    assert events and all(e.source == "deterministic_rule" for e in events)


def test_no_model_call_for_structure_detection():
    # Deterministic-only builder -- no semantic/model layer involved at all.
    history = [{"role": "nurse", "content": "Now let's talk about your medication. First, the dosage."}]
    ev = build_speaking_evidence({}, history)
    structure_events = [e for e in ev.candidate_events if e.event.startswith(("signposting", "organization_marker"))]
    assert structure_events and all(e.source == "deterministic_rule" for e in structure_events)


# ── Step 12A Task 8: session reconstruction determinism, including the semantic layer ──

def test_semantics_enriched_evidence_is_deterministic_given_same_mocked_responses(monkeypatch):
    monkeypatch.setattr(ai_scoring, "_call_ai", _mock_call_ai({"revealed": True}))
    first = _run(build_speaking_evidence_with_semantics(HIDDEN_CARD, HIDDEN_HISTORY))
    second = _run(build_speaking_evidence_with_semantics(HIDDEN_CARD, list(HIDDEN_HISTORY)))
    assert first.model_dump() == second.model_dump()
