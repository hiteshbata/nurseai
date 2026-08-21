"""E2.3 -- Listening AI Coach v1.

Interprets the weakness + mistake signal two other services already own and
turns it into one AI-generated "explain my mistakes / what to practice next"
answer. This module owns none of the underlying signal:

- skill_graph.get_weakness is still the only place "what is weak" is computed.
- listening_mistake_intelligence.get_mistake_profile is still the only place
  "why / what pattern" is computed.

This file only builds a small sanitized context from those two reads (plus a
completed-attempt count), prompts the AI, and validates its answer against a
fixed contract -- falling back to a deterministic same-shape answer whenever
there isn't enough history yet, the AI call fails, or its output doesn't
match the contract. No raw listening_mistake_events rows, question content,
or answer keys ever reach the prompt.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from supabase import Client

from app.core.threading import run_sync
from app.services.ai_scoring import _call_ai
from app.services.listening_mistake_intelligence import get_mistake_profile
from app.services.skill_graph import get_weakness

logger = logging.getLogger(__name__)

AI_PURPOSE = "listening_coach"
# gemini-flash-latest is a reasoning model: thinking tokens count against the
# completion budget, so 700 starved the visible JSON and it arrived truncated
# (finish_reason=MAX_TOKENS), always falling back to deterministic_fallback.
AI_MAX_TOKENS = 1200
AI_TEMPERATURE = 0.0
AI_CALL_TIMEOUT_SECONDS = 15

# "At least 2 completed Listening attempts" (E2.3 spec) -- one submission per
# attempt, so this is a plain count of past `submissions` rows, not a new
# weakness/mistake calculation.
MIN_LISTENING_ATTEMPTS = 2

PARTS = ("A", "B", "C")
PART_LABELS = {"A": "Part A", "B": "Part B", "C": "Part C"}


async def _count_listening_attempts(user_db: Client, user_id: str) -> int:
    """Same shape as plan_gating.has_free_module_attempt's count query --
    a plain count of past listening submissions, nothing computed."""
    result = await run_sync(
        user_db.table("submissions").select("id", count="exact")
        .eq("user_id", user_id).eq("module", "listening").execute
    )
    return result.count or 0


def classify_confidence(mistake_profile: Dict[str, Any]) -> str:
    """Pure. Confidence-aware hedging tier -- never claim a "persistent" or
    "recurring" pattern the evidence doesn't actually show."""
    if mistake_profile.get("persistent_mistakes"):
        return "persistent pattern"
    if mistake_profile.get("repeated_mistakes"):
        return "recurring pattern"
    return "recent/limited evidence"


def build_coach_context(
    weakness: List[Dict[str, Any]],
    mistake_profile: Dict[str, Any],
    attempt_count: int,
) -> Dict[str, Any]:
    """Pure. The ONLY thing the AI prompt (and the deterministic fallbacks)
    are built from -- top 1-2 weakest parts, aggregate mistake-pattern
    counts, and the attempt count. No raw event rows, no question ids, no
    answer text."""
    weak_parts = [
        {"part": w["skill"], "label": w["label"], "band": w["band"], "attempts": w["attempts"]}
        for w in weakness[:2]
    ]
    return {
        "weak_parts": weak_parts,
        "attempt_count": attempt_count,
        "sufficient_history": attempt_count >= MIN_LISTENING_ATTEMPTS,
        "confidence": classify_confidence(mistake_profile),
        "persistent_count": len(mistake_profile.get("persistent_mistakes", [])),
        "repeated_count": len(mistake_profile.get("repeated_mistakes", [])),
        "corrected_count": len(mistake_profile.get("corrected_mistakes", [])),
        "recent_wrong_count": len(mistake_profile.get("recent_mistakes", [])),
        "part_patterns": mistake_profile.get("part_patterns", {}),
        "frequency": mistake_profile.get("frequency", {}),
    }


async def prepare_coach_context(user_db: Client, user_id: str) -> Dict[str, Any]:
    """The context-build step, plus the history-sufficiency signal the
    endpoint gates on before ever touching the rate limiter or the AI."""
    weakness = await get_weakness(user_db, user_id, "listening:", lambda s: PART_LABELS.get(s, s))
    mistake_profile = await get_mistake_profile(user_db, user_id)
    attempt_count = await _count_listening_attempts(user_db, user_id)
    return build_coach_context(weakness, mistake_profile, attempt_count)


def _pick_practice_part(context: Dict[str, Any]) -> Dict[str, str]:
    """Pure. Deterministic Part A/B/C recommendation for the fallback paths --
    weakest known part first, else the part with the highest mistake rate
    this session, else a plain default."""
    weak_parts = context["weak_parts"]
    if weak_parts:
        w = weak_parts[0]
        return {"part": w["part"], "reason": f"{w['label']} is your weakest area right now (band {w['band']})."}

    part_patterns = context["part_patterns"]
    if part_patterns:
        worst_part, stats = max(part_patterns.items(), key=lambda kv: kv[1]["rate"])
        return {"part": worst_part, "reason": f"Part {worst_part} has your highest mistake rate so far."}

    return {"part": "B", "reason": "Keep practicing across all three parts to build a clearer picture."}


def insufficient_history_response(context: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic, no AI call. Returned when the student hasn't completed
    enough Listening attempts yet for a reliable pattern."""
    attempt_count = context["attempt_count"]
    return {
        "summary": "Keep practicing a little more before we can pinpoint a clear pattern in your Listening mistakes.",
        "key_issue": "Not enough Listening attempts yet to identify a reliable weak spot.",
        "why_it_happens": (
            f"You've completed {attempt_count} Listening attempt{'s' if attempt_count != 1 else ''} so far -- "
            f"a couple more give us enough evidence to spot a real pattern instead of one-off mistakes."
        ),
        "next_action": "Complete at least one more full Listening test, then check back here.",
        "recommended_practice": _pick_practice_part(context),
    }


def deterministic_fallback(context: Dict[str, Any]) -> Dict[str, Any]:
    """Same-shape fallback for a provider failure or malformed AI output,
    once history sufficiency has already been confirmed. Never returns raw
    model text."""
    weak_parts = context["weak_parts"]
    if weak_parts:
        w = weak_parts[0]
        summary = f"{w['label']} is your area to focus on next."
        key_issue = f"Your {w['label']} band is currently {w['band']}, based on {context['confidence']}."
        why_it_happens = "This part is scoring lower than the rest across your recent Listening practice."
    else:
        summary = "Your Listening performance looks solid across all three parts right now."
        key_issue = "No single weak part stands out."
        why_it_happens = "Your recent attempts are fairly even across Part A, B, and C."
    return {
        "summary": summary,
        "key_issue": key_issue,
        "why_it_happens": why_it_happens,
        "next_action": "Keep practicing regularly, and check the Wrong-Answer Notebook for specific questions to review.",
        "recommended_practice": _pick_practice_part(context),
    }


def validate_coach_response(data: Any) -> Optional[Dict[str, Any]]:
    """Pure. Strict shape check against the E2.3 contract. Returns a
    normalized dict on success, None on anything malformed -- callers fall
    back to deterministic_fallback rather than ever surfacing raw model
    text or a partial shape to the client."""
    if not isinstance(data, dict):
        return None
    for key in ("summary", "key_issue", "why_it_happens", "next_action"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
    practice = data.get("recommended_practice")
    if not isinstance(practice, dict):
        return None
    part = practice.get("part")
    if part not in PARTS:
        return None
    reason = practice.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None
    return {
        "summary": data["summary"].strip(),
        "key_issue": data["key_issue"].strip(),
        "why_it_happens": data["why_it_happens"].strip(),
        "next_action": data["next_action"].strip(),
        "recommended_practice": {"part": part, "reason": reason.strip()},
    }


def _build_prompt(context: Dict[str, Any]) -> str:
    weak_lines = "\n".join(
        f"- {w['label']}: band {w['band']} (seen across {w['attempts']} scored attempts)"
        for w in context["weak_parts"]
    ) or "- No single weak part -- performance is fairly even across A/B/C"

    return f"""You are an OET Listening coach. Explain this nursing student's Listening mistakes and tell them what to practice next.

EVIDENCE (already analyzed -- do not invent anything beyond this):
- Completed Listening attempts: {context['attempt_count']}
- Confidence in this pattern: {context['confidence']}
- Weakest part(s):
{weak_lines}
- Persistent mistakes (wrong 3+ times, still wrong): {context['persistent_count']}
- Repeated mistakes (wrong 2+ times): {context['repeated_count']}
- Corrected mistakes (were wrong, now right): {context['corrected_count']}
- Recent wrong answers (most recent attempt): {context['recent_wrong_count']}
- Per-part mistake rates: {context['part_patterns']}

Use confidence-aware language: only call something a "recurring pattern" or "persistent pattern" when the evidence above actually shows repeated/persistent mistakes; otherwise say it's based on recent/limited evidence. Never say "you always...".

Return ONLY this JSON:
{{
  "summary": "<1 sentence: the headline takeaway>",
  "key_issue": "<1 sentence: the single biggest issue>",
  "why_it_happens": "<1-2 sentences: why this is likely happening>",
  "next_action": "<1 concrete action for their next practice session>",
  "recommended_practice": {{"part": "A" | "B" | "C", "reason": "<1 sentence why this part>"}}
}}

Be concrete -- reference the actual evidence above. Do NOT use generic filler like "keep practicing" or "you're doing great"."""


async def generate_coach_response(context: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """AI call + validation, assuming history sufficiency has already been
    checked by the caller. Always returns the same fixed shape."""
    prompt = _build_prompt(context)
    try:
        result = await asyncio.wait_for(
            _call_ai(
                [{"role": "user", "content": prompt}],
                purpose=AI_PURPOSE,
                max_tokens=AI_MAX_TOKENS,
                json_mode=True,
                temperature=AI_TEMPERATURE,
                user_id=user_id,
            ),
            timeout=AI_CALL_TIMEOUT_SECONDS,
        )
    except Exception as e:
        logger.warning("[LISTENING_COACH_AI_FAILURE] user_id=%s error=%s", user_id, str(e)[:300])
        return deterministic_fallback(context)

    validated = validate_coach_response(result)
    if validated is None:
        logger.warning("[LISTENING_COACH_MALFORMED] user_id=%s result=%s", user_id, str(result)[:300])
        return deterministic_fallback(context)
    return validated
