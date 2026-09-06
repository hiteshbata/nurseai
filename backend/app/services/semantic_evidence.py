"""Semantic Evidence Layer (Step 7).

Fixes the two real-world gaps Step 6's live QA session exposed in the
deterministic layer (app.services.patient_state):

  Finding 1 -- false-positive hidden-information reveal: keyword overlap
  ("injections"/"painful") marked a hidden childhood-trauma detail as
  revealed when the patient never actually disclosed it.

  Finding 2 -- false-negative concern exploration/resolution: a genuine
  "why are you frightened of injections?" follow-up, and the patient's
  later "I think I could do that, it's not as scary as I thought", didn't
  match any phrase in the deterministic lists.

Design: this module never touches PatientState directly and never imports
app.services.patient_state.SemanticHints's consumer (patient_state.py
itself has zero dependency on this module -- see SemanticHints's docstring
there). It only does one thing: given short, specific text inputs, ask a
small/fast model a narrowly-scoped question and return a validated,
structured answer -- or None on any failure. Callers (ai_scoring.py,
speaking_realtime.py, speaking_evidence.py) are responsible for deciding
WHEN to call this (selectively -- see each classifier's docstring) and for
assembling the results into a patient_state.SemanticHints.

Every classifier is conservative by construction (Step 7): a None result
(model error, unparseable response, purpose not configured) is always
treated by the caller as the SAFE outcome for that check -- not revealed,
not resolved, no event -- never as "fall back to the old keyword-only
behavior", since that keyword behavior is the exact thing being corrected.

_call_ai is imported lazily inside functions, not at module level: ai_scoring
imports this module (for the hidden-info check in get_patient_response), so
a top-level "from app.services.ai_scoring import _call_ai" here would create
an import cycle. Same shape of problem already solved for jargon detection
in patient_state.py, same fix (defer the import).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from app.services.patient_state import SemanticHints, _hidden_info_candidate

logger = logging.getLogger(__name__)

SEMANTIC_PURPOSE = "speaking_semantic_evidence"
SOURCE_SEMANTIC = "semantic_model"

# Step 16B: gemini-3.5-flash is a reasoning model -- thinking tokens draw from
# the same maxOutputTokens budget as the visible JSON. Visible output here is
# tiny (one bool or a short string, e.g. {"revealed": false}), but the old
# 150-token budget left almost no room for thinking before hitting the cap
# with zero visible tokens (STATUS_TOKEN_LIMIT). Raised for thinking headroom,
# not because the JSON itself got any bigger.
SEMANTIC_MAX_TOKENS = 500

# Task 6: typed outcomes for a semantic call, read off _call_ai's existing
# return shape (provider_failure flag, finish_reason, raw_feedback-only
# fallback) -- no new call, no new provider signal, just naming the failure
# modes that used to all collapse into a single "None" the caller couldn't
# tell apart. STATUS_OK means the model actually answered with the expected
# JSON shape; every other value is a reason it didn't, and every caller
# still treats all of them as the conservative default for that check (see
# module docstring) -- this only adds visibility, it doesn't change what a
# failure causes downstream.
STATUS_OK = "ok"
STATUS_PROVIDER_FAILURE = "provider_failure"  # call never completed / service unavailable
STATUS_PARSE_FAILURE = "parse_failure"  # model responded but not with valid JSON
STATUS_TOKEN_LIMIT = "token_limit"  # response was truncated (finish_reason == "length")
STATUS_MALFORMED = "malformed_response"  # valid JSON, but missing the field this classifier needs

# ponytail: unbounded-but-cleared process-local cache, not a real LRU -- a
# scenario's hidden-info items and utterances are short and few, the size
# cap just stops a long-uptime process from growing this forever. Upgrade
# to a real LRU if a scenario/session count makes 5000 entries too small.
_reveal_cache: Dict[str, bool] = {}
_MAX_CACHE_ENTRIES = 5000


def _cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8", errors="replace")).hexdigest()


def _recent_context(history: List[Dict[str, str]], upto_index: int, n: int = 3) -> str:
    window = history[max(0, upto_index - n):upto_index]
    return "\n".join(
        f"{'Nurse' if t.get('role') == 'nurse' else 'Patient'}: {t.get('content', '')}"
        for t in window
    ) or "(no prior context)"


async def _call_semantic_detailed(
    prompt: str, *, user_id: str = "", session_id: Optional[int] = None,
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Task 6: same call as _call_semantic, but returns (status, data)
    instead of collapsing every non-success case to None -- lets callers
    that want it (hidden_info_hints, for evidence observability) record
    WHY a check didn't produce a usable answer. status is one of this
    module's STATUS_* constants; data is the parsed dict only when
    status == STATUS_OK."""
    from app.services.ai_scoring import _call_ai  # deferred: breaks ai_scoring <-> semantic_evidence cycle

    try:
        result = await _call_ai(
            [{"role": "user", "content": prompt}],
            purpose=SEMANTIC_PURPOSE,
            max_tokens=SEMANTIC_MAX_TOKENS,
            json_mode=True,
            temperature=0.0,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception as e:
        logger.warning("[SEMANTIC_EVIDENCE_CALL_FAILED] %s", str(e)[:200])
        return STATUS_PROVIDER_FAILURE, None

    if result.get("provider_failure"):
        return STATUS_PROVIDER_FAILURE, None
    if "raw_feedback" in result:
        # _call_ai's json_mode path only leaves a bare raw_feedback key when
        # _try_parse_json couldn't parse the response as JSON at all.
        if result.get("finish_reason") == "length":
            return STATUS_TOKEN_LIMIT, None
        return STATUS_PARSE_FAILURE, None
    return STATUS_OK, result


async def _call_semantic(prompt: str, *, user_id: str = "", session_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Single shared call point -- purpose, temperature, and failure handling
    live here once so every classifier below gets identical cost tracking,
    circuit-breaker, and fallback behavior for free (reuses _call_ai
    unchanged, see module docstring for why the import is deferred).
    Thin wrapper over _call_semantic_detailed for callers that only need
    the old None-on-any-failure contract."""
    _, data = await _call_semantic_detailed(prompt, user_id=user_id, session_id=session_id)
    return data


# ── 1. Hidden-information revelation verification (Finding 1) ───────────

async def _verify_hidden_reveal_detailed(
    item: str, statement: str, context: str = "", *, user_id: str = "", session_id: Optional[int] = None,
) -> tuple[str, Optional[bool]]:
    """Task 6: same check as verify_hidden_reveal, returning (status, value)
    so hidden_info_hints can record exactly why an item stayed unconfirmed
    -- a genuine "not revealed" verdict, vs. the call never producing one."""
    key = _cache_key("reveal", item, statement)
    if key in _reveal_cache:
        return STATUS_OK, _reveal_cache[key]

    prompt = f"""You are verifying whether confidential scenario information was disclosed in an OET nursing roleplay.

SCENARIO ITEM (must remain hidden unless genuinely disclosed):
"{item}"

RECENT CONVERSATION CONTEXT:
{context or "(no prior context)"}

PATIENT'S STATEMENT TO CHECK:
"{statement}"

Question: does the patient's statement disclose the SPECIFIC information in the scenario item above -- not just a related or superficially similar topic? Generic word overlap (e.g. sharing one clinical term) does NOT count as disclosure. Only answer true if the substance of the hidden fact itself was stated.

Return ONLY this JSON: {{"revealed": true or false}}"""

    status, result = await _call_semantic_detailed(prompt, user_id=user_id, session_id=session_id)
    if status != STATUS_OK:
        return status, None
    if "revealed" not in result:
        return STATUS_MALFORMED, None

    value = bool(result["revealed"])
    if len(_reveal_cache) > _MAX_CACHE_ENTRIES:
        _reveal_cache.clear()
    _reveal_cache[key] = value
    return STATUS_OK, value


async def verify_hidden_reveal(
    item: str, statement: str, context: str = "", *, user_id: str = "", session_id: Optional[int] = None,
) -> Optional[bool]:
    """Conservative-by-design: only True if the SPECIFIC hidden fact was
    actually disclosed, not merely a related/overlapping topic. Cached on
    (item, statement) since callers may re-verify the same pair repeatedly
    (legacy recomputes PatientState from scratch on every request). Thin
    wrapper over _verify_hidden_reveal_detailed for callers that only need
    the old None-on-any-failure contract."""
    _, value = await _verify_hidden_reveal_detailed(item, statement, context, user_id=user_id, session_id=session_id)
    return value


def _candidate_turns(item: str, history: List[Dict[str, str]]) -> List[tuple[int, str]]:
    """Step 12B (Rule 2/3): every patient turn where `item` is a lexical
    candidate, in transcript order -- not just the first one. Uses the same
    _hidden_info_candidate predicate derive_patient_state itself uses (fixes
    a separate mismatch: this used to check with the plainer _mentioned_in,
    which lacks the possessive/plural normalization _hidden_info_candidate
    has, so a candidate patient_state.py already counted could be missed
    here and never even get a statement to verify)."""
    return [
        (idx, t.get("content", ""))
        for idx, t in enumerate(history)
        if t.get("role") == "patient" and _hidden_info_candidate(item, t.get("content", ""))
    ]


def _aggregate_turn_status(turn_status: Dict[int, str]) -> str:
    """Step 12B: one item can now have many candidate-turn verdicts. Rolls
    them into the single status speaking_evidence/evidence_reconciliation's
    existing (per-item) contract expects, by precedence: a real "revealed"
    verdict wins over everything (hidden_info_hints already stops verifying
    an item's turns once one comes back True, so at most this looks for it);
    otherwise a real "not revealed" verdict wins over an inconclusive
    failure at any other turn (Step 8 -- an uncertain later candidate must
    not overturn a verified earlier negative); otherwise the earliest
    failure status, so the result is deterministic."""
    if not turn_status:
        return "not_called"
    values = set(turn_status.values())
    if "verified_revealed" in values:
        return "verified_revealed"
    if "verified_not_revealed" in values:
        return "verified_not_revealed"
    return turn_status[min(turn_status)]


async def hidden_info_hints(
    interlocutor_card: Dict[str, Any],
    history: List[Dict[str, str]],
    prior: Optional[SemanticHints] = None,
    *, user_id: str = "", session_id: Optional[int] = None,
) -> SemanticHints:
    """Orchestration for Finding 1 (+ Step 12B's Findings 2/3 fix): for every
    hidden-info item, verifies every not-yet-processed candidate turn (see
    _candidate_turns), in transcript order, stopping the moment one comes
    back verified_revealed (Step 11 cost control -- once an item is
    confirmed, its later candidate turns are never checked). Turn-level
    results accumulate in candidate_turn_status across calls via `prior`, so
    a false-positive-shaped early candidate can never block a genuine later
    disclosure from being checked (the exact Step 8/9 QA gap).

    Serves both timing classes with the same code path (Step 10): a live
    caller (ai_scoring.py, speaking_realtime.py) calls this after every
    turn with `prior` carried forward, so there's normally at most one new
    pending candidate turn per item to verify; a post-hoc caller
    (speaking_evidence.build_speaking_evidence_with_semantics) calls it
    once, fresh, over the whole final transcript, so every candidate turn
    ever produced gets verified. The (item, statement)-keyed _reveal_cache
    absorbs the cost of re-scanning turns a previous call already saw."""
    prior = prior or SemanticHints()
    confirmed = set(prior.confirmed_hidden_reveals)
    rejected = set(prior.rejected_hidden_reveals)
    verification_status = dict(prior.verification_status)
    candidate_turn_status: Dict[str, Dict[int, str]] = {k: dict(v) for k, v in prior.candidate_turn_status.items()}
    confirmed_reveal_turn = dict(prior.confirmed_reveal_turn)

    for item in (interlocutor_card or {}).get("information_to_withhold") or []:
        if item in confirmed:
            continue  # Step 11: a verified reveal is final, never re-checked
        turn_status = candidate_turn_status.setdefault(item, {})
        pending = [(idx, text) for idx, text in _candidate_turns(item, history) if idx not in turn_status]
        for idx, text in pending:
            context = _recent_context(history, idx)
            status, value = await _verify_hidden_reveal_detailed(
                item, text, context, user_id=user_id, session_id=session_id,
            )
            if status == STATUS_OK and value is True:
                turn_status[idx] = "verified_revealed"
                confirmed.add(item)
                confirmed_reveal_turn[item] = idx
                break  # Rule 6: earliest verified reveal wins, stop this item
            turn_status[idx] = "verified_not_revealed" if status == STATUS_OK else status

        if item in confirmed:
            verification_status[item] = "verified_revealed"
        elif turn_status:
            rejected.add(item)
            verification_status[item] = _aggregate_turn_status(turn_status)

    return SemanticHints(
        confirmed_hidden_reveals=frozenset(confirmed),
        rejected_hidden_reveals=frozenset(rejected),
        extra_nurse_events=dict(prior.extra_nurse_events),
        resolved_concerns=frozenset(prior.resolved_concerns),
        verification_status=verification_status,
        candidate_turn_status=candidate_turn_status,
        confirmed_reveal_turn=confirmed_reveal_turn,
    )


# ── 2. Concern exploration / addressing classification (Finding 2) ──────

_VALID_CONCERN_EVENTS = {"concern_exploration", "concern_addressing", "none"}


async def classify_nurse_concern_event(
    utterance: str, concerns: List[str], context: str = "", *, user_id: str = "", session_id: Optional[int] = None,
) -> Optional[Dict[str, Optional[str]]]:
    """Only meant to be called when the deterministic phrase lists found
    NOTHING on this turn and a concern is still outstanding -- see Step 3
    Pattern B. Returns {"event": ..., "target_concern": ...} or None on
    failure. target_concern is null whenever the model can't confidently
    map to one of the scenario's own listed concerns (Step 8/10) -- never
    trusts an unlisted string (Test 10)."""
    if not concerns:
        return None

    concern_list = "\n".join(f'- "{c}"' for c in concerns)
    prompt = f"""You are classifying one nurse utterance from an OET nursing roleplay for whether it explores or addresses a specific patient concern.

PATIENT CONCERNS IN THIS SCENARIO:
{concern_list}

RECENT CONVERSATION CONTEXT:
{context or "(no prior context)"}

NURSE'S UTTERANCE TO CLASSIFY:
"{utterance}"

Classify the utterance as exactly one of:
- "concern_exploration": genuinely asks the patient to elaborate on or explain a specific concern (not a generic question)
- "concern_addressing": genuinely explains, reassures, or gives information that responds to a specific concern
- "none": neither

If exploration or addressing, name EXACTLY one concern from the list above it targets, copied verbatim. If you cannot confidently match it to one of the listed concerns, use null.

Return ONLY this JSON: {{"event": "concern_exploration" or "concern_addressing" or "none", "target_concern": "<verbatim concern text>" or null}}"""

    result = await _call_semantic(prompt, user_id=user_id, session_id=session_id)
    if result is None or result.get("event") not in _VALID_CONCERN_EVENTS:
        return None

    event = result["event"]
    if event == "none":
        return {"event": "none", "target_concern": None}

    target = result.get("target_concern")
    # Never trust a target the scenario doesn't actually list (Step 8/10) --
    # exact-match only, no fuzzy guessing.
    if target not in concerns:
        target = None
    return {"event": event, "target_concern": target}


# ── 3. Patient resolution signal (Finding 2, patient side) ──────────────

async def classify_patient_resolution(
    concern: str, nurse_turn: str, patient_turn: str, *, user_id: str = "", session_id: Optional[int] = None,
) -> Optional[bool]:
    """Only meant to be called when a concern just reached "addressed" and
    the very next patient turn follows -- Step 9 (patient-side evidence).
    A neutral acknowledgement ("Oh") or a persistent-worry statement
    ("I'm still very worried") must both come back False, not just an
    absence of negative words -- see Step 15 Tests 5/6."""
    prompt = f"""You are judging whether a patient's reply in an OET nursing roleplay shows genuine resolution of a specific concern the nurse just addressed.

CONCERN: "{concern}"
NURSE'S EXPLANATION: "{nurse_turn}"
PATIENT'S REPLY TO JUDGE: "{patient_turn}"

Does the patient's reply show genuine relief or understanding that resolves this concern? A neutral acknowledgement ("Oh", "I see") is NOT resolution. A statement that the worry persists or has only partially eased is NOT resolution.

Return ONLY this JSON: {{"resolved": true or false}}"""

    result = await _call_semantic(prompt, user_id=user_id, session_id=session_id)
    if result is None or "resolved" not in result:
        return None
    return bool(result["resolved"])
