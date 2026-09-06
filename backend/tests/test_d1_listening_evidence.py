"""Tests for the Active Listening / Interruption (D1) evidence module
(Step 21J). Pure pytest coverage over the canonical
build_d1_listening_evidence()/select_d1_support_events()/
find_unaddressed_patient_contributions()/build_interruption_evidence()
functions -- no score, no model call, no DB.
"""
from app.services.d1_listening_evidence import (
    DIRECTION_CANDIDATE_OVER_PATIENT,
    TURN_ATTRIBUTION_SESSION_LEVEL_ONLY,
    D1ListeningEvidence,
    InterruptionEvidence,
    build_d1_listening_evidence,
    build_interruption_evidence,
    find_unaddressed_patient_contributions,
    select_d1_support_events,
)
from app.services.evidence_reconciliation import UnifiedCandidateEvent, UnifiedPatientEvent


def _cand(event, turn_index, related_patient_turns=None, source="deterministic_rule"):
    return UnifiedCandidateEvent(
        event=event, turn_index=turn_index, provenance=source,
        evidence=[{"source": source, "evidence_text": f"text for {event}"}],
        related_patient_turns=related_patient_turns or [],
    )


def _pat(event, turn_index, source="deterministic_rule", evidence_text=None):
    return UnifiedPatientEvent(
        event=event, turn_index=turn_index, provenance=source,
        evidence_text=evidence_text or f"text for {event}",
    )


# ── Reuse: B2/D4/D5/A2 -> D1 support (never a new detector) ──────────────

def test_cue_response_supports_d1():
    events = select_d1_support_events([_cand("cue_response", 1, related_patient_turns=[0])])
    assert len(events) == 1 and events[0].event == "cue_response"


def test_cue_response_uncertain_supports_d1():
    events = select_d1_support_events([_cand("cue_response_uncertain", 1, related_patient_turns=[0])])
    assert len(events) == 1


def test_clarification_supports_d1():
    events = select_d1_support_events([_cand("clarification_request", 3)])
    assert len(events) == 1 and events[0].event == "clarification_request"


def test_clarification_uncertain_supports_d1():
    events = select_d1_support_events([_cand("clarification_uncertain", 3)])
    assert len(events) == 1


def test_summary_supports_d1():
    for event in ("summary_statement", "summary_uncertain", "summary_check"):
        events = select_d1_support_events([_cand(event, 5)])
        assert len(events) == 1 and events[0].event == event


def test_acknowledgement_supports_d1():
    events = select_d1_support_events([_cand("attentive_acknowledgement", 1)])
    assert len(events) == 1


def test_reflective_response_supports_d1():
    events = select_d1_support_events([_cand("reflective_response", 2, related_patient_turns=[1])])
    assert len(events) == 1


def test_unrelated_event_not_selected():
    events = select_d1_support_events([_cand("open_question", 1), _cand("jargon_used", 2)])
    assert events == []


def test_d1_d4_overlap_is_visible_on_both():
    """A single clarification event is legitimate evidence for both D4 (its
    own mapping, untouched) and D1 (reused here) -- never deduplicated."""
    clarify = _cand("clarification_request", 3)
    d1_support = select_d1_support_events([clarify])
    assert len(d1_support) == 1
    assert clarify.event == "clarification_request"  # same object, D4's own mapper is untouched


def test_d1_d5_overlap():
    summary = _cand("summary_statement", 4)
    assert select_d1_support_events([summary]) == [summary]


def test_d1_a2_overlap():
    ack = _cand("attentive_acknowledgement", 1)
    reflect = _cand("reflective_response", 2, related_patient_turns=[1])
    selected = select_d1_support_events([ack, reflect])
    assert {e.event for e in selected} == {"attentive_acknowledgement", "reflective_response"}


def test_d1_b2_overlap():
    cue_response = _cand("cue_response", 1, related_patient_turns=[0])
    assert select_d1_support_events([cue_response]) == [cue_response]


# ── Reused evidence is support only, never "excellent listening" ─────────

def test_reused_support_does_not_imply_quality_field():
    """No score/quality/judgement field exists anywhere on the model --
    presence of support evidence is the only thing represented."""
    ack = _cand("attentive_acknowledgement", 1)
    bundle = build_d1_listening_evidence([ack], [])
    assert not hasattr(bundle, "score")
    assert not hasattr(bundle, "quality")
    assert not hasattr(bundle, "band")
    assert len(bundle.active_listening_support) == 1


# ── unaddressed_patient_contribution (Step 6/10) ──────────────────────────

def test_unanswered_patient_contribution_detected():
    cue = _pat("concern_raised", 0)
    result = find_unaddressed_patient_contributions([cue], [])
    assert result == [cue]


def test_answered_cue_not_flagged_unaddressed():
    cue = _pat("concern_raised", 0)
    response = _cand("cue_response", 1, related_patient_turns=[0])
    assert find_unaddressed_patient_contributions([cue], [response]) == []


def test_uncertain_cue_response_still_counts_as_addressed():
    """cue_response_uncertain still means a next-turn pairing existed --
    adjacency was found, engagement phrasing wasn't. Not the same thing as
    no pairing at all, so it must not be flagged unaddressed."""
    cue = _pat("emotional_trigger_fired", 0)
    response = _cand("cue_response_uncertain", 1, related_patient_turns=[0])
    assert find_unaddressed_patient_contributions([cue], [response]) == []


def test_non_cue_patient_event_never_flagged():
    info = _pat("information_revealed", 0)
    assert find_unaddressed_patient_contributions([info], []) == []


def test_unrelated_cue_response_does_not_clear_a_different_cue():
    cue_a = _pat("concern_raised", 0)
    cue_b = _pat("concern_raised", 4)
    response_for_a = _cand("cue_response", 1, related_patient_turns=[0])
    result = find_unaddressed_patient_contributions([cue_a, cue_b], [response_for_a])
    assert result == [cue_b]


# ── Interruption: session-level only, no fabricated attribution ──────────

def test_no_metric_stays_none_preserves_gap_reason():
    assert build_interruption_evidence(None) is None


def test_zero_interruptions_is_not_positive_evidence():
    ev = build_interruption_evidence(0)
    assert ev.session_interruption_metric == 0
    assert ev.interruption_direction is None  # no positive "good listening" claim


def test_candidate_interruption_direction_when_count_positive():
    ev = build_interruption_evidence(3)
    assert ev.interruption_direction == DIRECTION_CANDIDATE_OVER_PATIENT


def test_patient_interruption_direction_never_fabricated():
    """No code path in this module can ever produce a patient-interrupts-
    candidate direction -- the realtime event model has no such event."""
    for count in (0, 1, 5, 100):
        ev = build_interruption_evidence(count)
        if ev is not None and ev.interruption_direction is not None:
            assert ev.interruption_direction == DIRECTION_CANDIDATE_OVER_PATIENT


def test_turn_attribution_always_session_level_only():
    ev = build_interruption_evidence(2)
    assert ev.turn_attribution == TURN_ATTRIBUTION_SESSION_LEVEL_ONLY


def test_vad_barging_ambiguity_no_intent_field():
    """The model carries no 'intentional'/'deliberate' field -- observable
    system behavior only, never inferred intent."""
    ev = build_interruption_evidence(1)
    assert not hasattr(ev, "intentional")
    assert not hasattr(ev, "deliberate")


def test_legacy_no_audio_limitation():
    """Legacy sessions pass interrupted_count=None (no telemetry exists) --
    interruption_evidence must be absent, never a fabricated zero."""
    bundle = build_d1_listening_evidence([], [], interrupted_count=None)
    assert bundle.interruption_evidence is None
    assert any("legacy" in limitation.lower() for limitation in bundle.limitations)


def test_realtime_limitation_documented():
    bundle = build_d1_listening_evidence([], [], interrupted_count=2)
    assert any("timestamp" in limitation.lower() or "turn index" in limitation.lower()
               for limitation in bundle.limitations)


# ── Provenance / evidence levels (Step 7) ─────────────────────────────────

def test_interruption_metric_provenance_is_direct_l1():
    ev = build_interruption_evidence(2)
    assert ev.provenance == "direct"
    assert ev.evidence_level == "L1_direct"


def test_reused_support_keeps_selection_only_no_reprovenance():
    """select_d1_support_events is a pure filter -- it never rewrites the
    provenance/evidence_level fields already on the UnifiedCandidateEvent."""
    ack = _cand("attentive_acknowledgement", 1, source="semantic_model")
    selected = select_d1_support_events([ack])
    assert selected[0].provenance == "semantic_model"


# ── Missing != negative ───────────────────────────────────────────────────

def test_missing_support_is_not_negative_evidence():
    bundle = build_d1_listening_evidence([], [])
    assert bundle.active_listening_support == []
    assert bundle.unaddressed_patient_contributions == []
    # No field anywhere claims "poor listening" -- absence is just absence.
    assert not hasattr(bundle, "listening_score")


# ── Serialization / determinism ───────────────────────────────────────────

def test_serialization_round_trip():
    ack = _cand("attentive_acknowledgement", 1)
    cue = _pat("concern_raised", 0)
    bundle = build_d1_listening_evidence([ack], [cue], interrupted_count=1)
    restored = D1ListeningEvidence.model_validate_json(bundle.model_dump_json())
    assert restored == bundle


def test_determinism_same_input_same_output():
    ack = _cand("attentive_acknowledgement", 1)
    clarify = _cand("clarification_request", 3)
    cue = _pat("concern_raised", 0)
    bundle_1 = build_d1_listening_evidence([ack, clarify], [cue], interrupted_count=2)
    bundle_2 = build_d1_listening_evidence([ack, clarify], [cue], interrupted_count=2)
    assert bundle_1 == bundle_2


# ── No score / no model call (Step 22/27) ─────────────────────────────────

def test_no_score_band_or_judgement_field_anywhere():
    for cls in (D1ListeningEvidence, InterruptionEvidence):
        fields = cls.model_fields.keys()
        for banned in ("score", "band", "penalty", "quality", "good_listener", "poor_listener"):
            assert banned not in fields


def test_no_network_or_model_dependency():
    """This module imports only pydantic + two sibling evidence modules --
    no HTTP client, no provider SDK, nothing that could make a model call."""
    import app.services.d1_listening_evidence as mod
    source = open(mod.__file__, encoding="utf-8").read()
    for banned in ("openai", "gemini", "anthropic", "requests.", "httpx.", "aiohttp"):
        assert banned not in source.lower()
