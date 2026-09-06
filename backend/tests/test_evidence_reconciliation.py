"""Tests for the Unified Evidence Reconciliation Layer (Step 11).

Pure unit tests: every SpeakingEvidence input is hand-built directly from its
pydantic models (no LLM mocking, no async) -- reconcile_evidence() is a pure
function over already-computed evidence, so these exercise exactly the
regrouping/provenance logic, not the upstream detectors already covered by
test_speaking_evidence.py and test_semantic_evidence.py.
"""
import pytest

from app.services.evidence_reconciliation import (
    PROVENANCE_DETERMINISTIC,
    PROVENANCE_HYBRID,
    PROVENANCE_SEMANTIC,
    REASON_NOT_A_CANDIDATE,
    REASON_SEMANTIC_UNAVAILABLE_CONSERVATIVE_DEFAULT,
    REASON_SEMANTIC_VERIFIED_NOT_REVEALED,
    REASON_SEMANTIC_VERIFIED_REVEALED,
    VIOLATION_VERIFIED_NOT_REVEALED_BUT_FINAL_REVEALED,
    VIOLATION_VERIFIED_REVEALED_BUT_FINAL_HIDDEN,
    VIOLATION_VERIFIED_WITHOUT_CANDIDATE,
    check_integrity,
    reconcile_evidence,
)
from app.services.speaking_evidence import (
    CandidateEvent,
    ConcernOutcome,
    HiddenInfoOutcome,
    InteractionMetrics,
    PatientEvent,
    SOURCE_DETERMINISTIC,
    SOURCE_SEMANTIC,
    SpeakingEvidence,
)

EMPTY_METRICS = InteractionMetrics(
    turn_counts={"nurse": 0, "patient": 0, "total": 0},
    jargon_events=0, empathy_events=0, concern_exploration_events=0,
    understanding_check_events=0, dismissive_events=0,
)


def _evidence(**overrides) -> SpeakingEvidence:
    base = dict(
        candidate_events=[], patient_events=[], concern_outcomes=[],
        state_transitions=[], jargon_evidence=[], interaction_metrics=EMPTY_METRICS,
        hidden_info_outcomes=[],
    )
    base.update(overrides)
    return SpeakingEvidence(**base)


# Test 1: deterministic-only candidate event stays deterministic_rule.
def test_1_deterministic_only():
    ev = _evidence(candidate_events=[
        CandidateEvent(event="empathy_acknowledgement", turn_index=1, evidence_text="i understand you"),
    ])
    unified = reconcile_evidence(ev)
    assert len(unified.candidate_events) == 1
    assert unified.candidate_events[0].provenance == PROVENANCE_DETERMINISTIC


# Test 2: semantic-only candidate event stays semantic_model.
def test_2_semantic_only():
    ev = _evidence(candidate_events=[
        CandidateEvent(event="concern_exploration", turn_index=3, evidence_text="why does that worry you?",
                        source=SOURCE_SEMANTIC, target_concern="fear of injections"),
    ])
    unified = reconcile_evidence(ev)
    assert len(unified.candidate_events) == 1
    assert unified.candidate_events[0].provenance == PROVENANCE_SEMANTIC
    assert unified.candidate_events[0].target_concern == "fear of injections"


# Test 3: same turn + same event from both sources -> hybrid, both evidence texts kept.
def test_3_both_agree_is_hybrid():
    ev = _evidence(candidate_events=[
        CandidateEvent(event="empathy_acknowledgement", turn_index=2, evidence_text="i can understand"),
        CandidateEvent(event="empathy_acknowledgement", turn_index=2, evidence_text="that must be hard",
                        source=SOURCE_SEMANTIC),
    ])
    unified = reconcile_evidence(ev)
    assert len(unified.candidate_events) == 1
    entry = unified.candidate_events[0]
    assert entry.provenance == PROVENANCE_HYBRID
    assert {e["source"] for e in entry.evidence} == {SOURCE_DETERMINISTIC, SOURCE_SEMANTIC}


# Test 4: deterministic misses, semantic detects -> semantic provenance (no
# deterministic entry ever existed for this turn/event).
def test_4_deterministic_misses_semantic_detects():
    ev = _evidence(candidate_events=[
        CandidateEvent(event="concern_addressing", turn_index=5, evidence_text="the needle is only 4mm",
                        source=SOURCE_SEMANTIC, target_concern="fear of injections"),
    ])
    unified = reconcile_evidence(ev)
    assert unified.candidate_events[0].provenance == PROVENANCE_SEMANTIC


# Test 5: deterministic detects one event, semantic reports a DIFFERENT event
# at the same turn (contradiction, not agreement) -- both entries preserved
# separately, deterministic entry's provenance untouched.
def test_5_contradiction_visible_not_hidden():
    ev = _evidence(candidate_events=[
        CandidateEvent(event="dismissive_response", turn_index=4, evidence_text="don't worry"),
        CandidateEvent(event="empathy_acknowledgement", turn_index=4, evidence_text="i understand",
                        source=SOURCE_SEMANTIC),
    ])
    unified = reconcile_evidence(ev)
    assert len(unified.candidate_events) == 2
    by_event = {e.event: e for e in unified.candidate_events}
    assert by_event["dismissive_response"].provenance == PROVENANCE_DETERMINISTIC
    assert by_event["empathy_acknowledgement"].provenance == PROVENANCE_SEMANTIC


# Test 6: semantic provider failure never appears as a candidate/patient
# event at all (callers only append on success) -- deterministic evidence at
# the same turn is completely unaffected.
def test_6_semantic_provider_failure_leaves_deterministic_intact():
    ev = _evidence(candidate_events=[
        CandidateEvent(event="jargon_used", turn_index=1, evidence_text="cannula"),
    ])
    unified = reconcile_evidence(ev)
    assert len(unified.candidate_events) == 1
    assert unified.candidate_events[0].provenance == PROVENANCE_DETERMINISTIC


# Test 7: same shape as Test 6 for a parse failure -- nothing semantic is
# ever fabricated from a bad response, deterministic entry stands alone.
def test_7_semantic_parse_failure_leaves_deterministic_intact():
    ev = _evidence(patient_events=[
        PatientEvent(event="information_revealed", turn_index=2, evidence_text="I take insulin daily"),
    ])
    unified = reconcile_evidence(ev)
    assert len(unified.patient_events) == 1
    assert unified.patient_events[0].provenance == PROVENANCE_DETERMINISTIC


# Test 8: hidden-info candidate detected + semantic verified_not_revealed -> hybrid.
def test_8_hidden_info_candidate_and_not_revealed_is_hybrid():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="childhood trauma", candidate_detected=True,
                            verification_status="verified_not_revealed", final_status="hidden"),
    ])
    unified = reconcile_evidence(ev)
    outcome = unified.hidden_info_outcomes[0]
    assert outcome.provenance == PROVENANCE_HYBRID
    assert outcome.final_status == "hidden"


# Test 9: hidden-info candidate detected + semantic verified_revealed -> hybrid, final=revealed.
def test_9_hidden_info_candidate_and_revealed_is_hybrid():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="childhood trauma", candidate_detected=True,
                            verification_status="verified_revealed", final_status="revealed"),
    ])
    unified = reconcile_evidence(ev)
    outcome = unified.hidden_info_outcomes[0]
    assert outcome.provenance == PROVENANCE_HYBRID
    assert outcome.final_status == "revealed"


# Test 10: hidden-info candidate never triggered -> semantic never called ->
# deterministic_rule, not hybrid.
def test_10_hidden_info_not_a_candidate_stays_deterministic():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="childhood trauma", candidate_detected=False,
                            verification_status="not_called", final_status="hidden"),
    ])
    unified = reconcile_evidence(ev)
    assert unified.hidden_info_outcomes[0].provenance == PROVENANCE_DETERMINISTIC


# Test 11: concern acknowledged deterministically + explored semantically ->
# merged timeline shows both, official final_status untouched, believed
# status reflects the higher-rank semantic entry.
def test_11_concern_acknowledged_plus_semantic_explored():
    outcome = ConcernOutcome(
        concern="fear of injections", final_status="acknowledged", resolved=False,
        history=[{"status": "raised", "turn_index": 1, "cause_event": None},
                 {"status": "acknowledged", "turn_index": 2, "cause_event": "empathy_acknowledgement"}],
    )
    ev = _evidence(concern_outcomes=[outcome], candidate_events=[
        CandidateEvent(event="concern_exploration", turn_index=4, evidence_text="what worries you most?",
                        source=SOURCE_SEMANTIC, target_concern="fear of injections"),
    ])
    unified = reconcile_evidence(ev)
    uc = unified.concern_outcomes[0]
    assert uc.deterministic_final_status == "acknowledged"
    assert uc.unified_believed_status == "explored"
    statuses = [(e.status, e.provenance) for e in uc.timeline]
    assert ("explored", PROVENANCE_SEMANTIC) in statuses
    assert ("acknowledged", PROVENANCE_DETERMINISTIC) in statuses


# Test 12: resolved -> reopened -> resolved again -- reopened_events/history
# pass through unchanged, reopened flag surfaces on the matching timeline entry.
def test_12_resolved_reopened_resolved_again():
    outcome = ConcernOutcome(
        concern="fear of injections", final_status="resolved", resolved=True,
        history=[
            {"status": "raised", "turn_index": 1, "cause_event": None},
            {"status": "addressed", "turn_index": 2, "cause_event": "concern_addressing"},
            {"status": "resolved", "turn_index": 3, "cause_event": None},
            {"status": "addressed", "turn_index": 5, "cause_event": None},
            {"status": "resolved", "turn_index": 7, "cause_event": None},
        ],
        resolved_at_turns=[3, 7],
        reopened_events=[{"turn_index": 5, "from_status": "resolved", "to_status": "addressed",
                           "reason": "still afraid"}],
    )
    ev = _evidence(concern_outcomes=[outcome])
    unified = reconcile_evidence(ev)
    uc = unified.concern_outcomes[0]
    assert uc.resolved_at_turns == [3, 7]
    reopened_entry = next(e for e in uc.timeline if e.turn_index == 5)
    assert reopened_entry.reopened is True
    assert reopened_entry.reopened_from == "resolved"


# Test 13: state transitions retain cause/turn and are always tagged
# deterministic_rule (Step 9 -- semantic evidence never invents a transition).
def test_13_state_transitions_retain_causes_and_provenance():
    from app.services.speaking_evidence import StateTransition
    ev = _evidence(state_transitions=[
        StateTransition(field="trust", before="moderate", after="high",
                          cause_event="empathy_acknowledgement", turn_index=3),
    ])
    unified = reconcile_evidence(ev)
    t = unified.state_transitions[0]
    assert t.before == "moderate" and t.after == "high"
    assert t.cause_event == "empathy_acknowledgement"
    assert t.provenance == PROVENANCE_DETERMINISTIC


# Test 14: empty/minimal scenario -> reconciliation is a safe no-op, not an error.
def test_14_empty_scenario():
    unified = reconcile_evidence(_evidence())
    assert unified.candidate_events == []
    assert unified.patient_events == []
    assert unified.concern_outcomes == []
    assert unified.hidden_info_outcomes == []
    assert unified.state_transitions == []


# Test 15: session isolation -- reconciling two independent SpeakingEvidence
# objects never lets one session's events leak into the other's output.
def test_15_session_isolation():
    ev_a = _evidence(candidate_events=[
        CandidateEvent(event="jargon_used", turn_index=1, evidence_text="cannula"),
    ])
    ev_b = _evidence(candidate_events=[
        CandidateEvent(event="jargon_used", turn_index=1, evidence_text="dyspnea"),
    ])
    unified_a = reconcile_evidence(ev_a)
    unified_b = reconcile_evidence(ev_b)
    assert unified_a.candidate_events[0].evidence[0]["evidence_text"] == "cannula"
    assert unified_b.candidate_events[0].evidence[0]["evidence_text"] == "dyspnea"


# ── Golden reconciliation cases (Step 17) ────────────────────────────────
# Offline fixture set, no live model call -- each case's expected shape is
# read directly off the reconciliation rules above (Steps 3-6).

# Case A -- false-positive hidden info: candidate detected, semantic says
# NOT_REVEALED -> final stays hidden, provenance hybrid (both layers acted).
def test_golden_case_a_false_positive_hidden_info():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="childhood trauma involving an uncle's painful injections",
                            candidate_detected=True, verification_status="verified_not_revealed",
                            final_status="hidden"),
    ])
    outcome = reconcile_evidence(ev).hidden_info_outcomes[0]
    assert outcome.candidate_detected is True
    assert outcome.verification_status == "verified_not_revealed"
    assert outcome.final_status == "hidden"
    assert outcome.provenance == PROVENANCE_HYBRID


# Case B -- genuine disclosure: candidate detected, semantic says REVEALED ->
# final flips to revealed, provenance hybrid.
def test_golden_case_b_genuine_disclosure():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="childhood trauma involving an uncle's painful injections",
                            candidate_detected=True, verification_status="verified_revealed",
                            final_status="revealed"),
    ])
    outcome = reconcile_evidence(ev).hidden_info_outcomes[0]
    assert outcome.final_status == "revealed"
    assert outcome.provenance == PROVENANCE_HYBRID


# Case C -- paraphrased concern exploration: deterministic never caught it,
# semantic did -> unified candidate event, provenance semantic_model.
def test_golden_case_c_paraphrased_concern_exploration():
    ev = _evidence(candidate_events=[
        CandidateEvent(event="concern_exploration", turn_index=6,
                        evidence_text="What is making you reluctant to have these injections?",
                        source=SOURCE_SEMANTIC, target_concern="fear of injections"),
    ])
    entry = reconcile_evidence(ev).candidate_events[0]
    assert entry.provenance == PROVENANCE_SEMANTIC
    assert entry.target_concern == "fear of injections"


# Case D -- deterministic + semantic agreement (both detect empathy at the
# same turn) -> hybrid.
def test_golden_case_d_agreement_is_hybrid():
    ev = _evidence(candidate_events=[
        CandidateEvent(event="empathy_acknowledgement", turn_index=2, evidence_text="i can understand"),
        CandidateEvent(event="empathy_acknowledgement", turn_index=2, evidence_text="that must be difficult",
                        source=SOURCE_SEMANTIC),
    ])
    entry = reconcile_evidence(ev).candidate_events[0]
    assert entry.provenance == PROVENANCE_HYBRID


# Case E -- semantic failure: no semantic entry is ever appended for a failed
# call (see semantic_evidence's conservative-by-construction contract), so
# deterministic evidence is the whole story, unmarked and unaltered.
def test_golden_case_e_semantic_failure_deterministic_preserved():
    ev = _evidence(candidate_events=[
        CandidateEvent(event="jargon_used", turn_index=3, evidence_text="tachycardia"),
    ])
    entry = reconcile_evidence(ev).candidate_events[0]
    assert entry.provenance == PROVENANCE_DETERMINISTIC
    assert entry.evidence == [{"source": SOURCE_DETERMINISTIC, "evidence_text": "tachycardia"}]


# ── Step 12A Task 10: structured "reason for final status" ──────────────

def test_reason_not_a_candidate():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="x", candidate_detected=False, verification_status="not_called", final_status="hidden"),
    ])
    assert reconcile_evidence(ev).hidden_info_outcomes[0].reason == REASON_NOT_A_CANDIDATE


def test_reason_semantic_verified_revealed():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="x", candidate_detected=True, verification_status="verified_revealed", final_status="revealed"),
    ])
    assert reconcile_evidence(ev).hidden_info_outcomes[0].reason == REASON_SEMANTIC_VERIFIED_REVEALED


def test_reason_semantic_verified_not_revealed():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="x", candidate_detected=True, verification_status="verified_not_revealed", final_status="hidden"),
    ])
    assert reconcile_evidence(ev).hidden_info_outcomes[0].reason == REASON_SEMANTIC_VERIFIED_NOT_REVEALED


# A candidate whose semantic check never produced a usable verdict (any of
# provider_failure/parse_failure/token_limit/malformed_response) is why the
# conservative default stands -- not "verified not revealed" (that would be
# claiming a real verdict that never happened).
@pytest.mark.parametrize("status", ["provider_failure", "parse_failure", "token_limit", "malformed_response"])
def test_reason_semantic_unavailable_conservative_default(status):
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="x", candidate_detected=True, verification_status=status, final_status="hidden"),
    ])
    assert reconcile_evidence(ev).hidden_info_outcomes[0].reason == REASON_SEMANTIC_UNAVAILABLE_CONSERVATIVE_DEFAULT


# ── Step 12A Task 11: evidence integrity checks ──────────────────────────

def test_integrity_clean_evidence_has_no_violations():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="a", candidate_detected=False, verification_status="not_called", final_status="hidden"),
        HiddenInfoOutcome(item="b", candidate_detected=True, verification_status="verified_revealed", final_status="revealed"),
        HiddenInfoOutcome(item="c", candidate_detected=True, verification_status="verified_not_revealed", final_status="hidden"),
    ])
    assert check_integrity(reconcile_evidence(ev)) == []


# Legitimate uncertainty (semantic call failed, candidate stays hidden) must
# NOT be flagged -- Task 11 explicitly warns against overvalidating this.
def test_integrity_provider_failure_is_not_a_violation():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="a", candidate_detected=True, verification_status="provider_failure", final_status="hidden"),
    ])
    assert check_integrity(reconcile_evidence(ev)) == []


def test_integrity_verified_without_candidate_is_flagged():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="a", candidate_detected=False, verification_status="verified_revealed", final_status="revealed"),
    ])
    violations = check_integrity(reconcile_evidence(ev))
    assert len(violations) == 1
    assert violations[0].violation == VIOLATION_VERIFIED_WITHOUT_CANDIDATE
    assert violations[0].item == "a"


def test_integrity_verified_revealed_but_final_hidden_is_flagged():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="a", candidate_detected=True, verification_status="verified_revealed", final_status="hidden"),
    ])
    violations = check_integrity(reconcile_evidence(ev))
    assert len(violations) == 1
    assert violations[0].violation == VIOLATION_VERIFIED_REVEALED_BUT_FINAL_HIDDEN


def test_integrity_verified_not_revealed_but_final_revealed_is_flagged():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="a", candidate_detected=True, verification_status="verified_not_revealed", final_status="revealed"),
    ])
    violations = check_integrity(reconcile_evidence(ev))
    assert len(violations) == 1
    assert violations[0].violation == VIOLATION_VERIFIED_NOT_REVEALED_BUT_FINAL_REVEALED


def test_integrity_multiple_items_only_flags_the_bad_one():
    ev = _evidence(hidden_info_outcomes=[
        HiddenInfoOutcome(item="good", candidate_detected=True, verification_status="verified_revealed", final_status="revealed"),
        HiddenInfoOutcome(item="bad", candidate_detected=True, verification_status="verified_revealed", final_status="hidden"),
    ])
    violations = check_integrity(reconcile_evidence(ev))
    assert len(violations) == 1
    assert violations[0].item == "bad"


# ── Step 12A Task 2: display belief must never become official state ────
# unified_believed_status/UnifiedEvidence is a read model for human review
# only. Structural check: the modules that actually drive the live patient
# prompt / PatientState never import this module at all, so there is no
# code path by which a reconciliation belief could leak into official state.

def test_reconciliation_module_not_imported_by_patient_state_or_live_pipelines():
    import inspect

    import app.services.ai_scoring as ai_scoring
    import app.services.patient_state as patient_state
    import app.routers.speaking_realtime as speaking_realtime

    for module in (patient_state, ai_scoring, speaking_realtime):
        source = inspect.getsource(module)
        assert "evidence_reconciliation" not in source
        assert "unified_believed_status" not in source
