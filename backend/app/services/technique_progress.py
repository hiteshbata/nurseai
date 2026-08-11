"""Thin integration layer: turn a graded micro-practice attempt into a
"technique:<skill_tag>" observation on the existing Weakness Graph
(skill_graph.py) instead of a separate progress system. This is deliberately
NOT the Learner Brain -- no weakness detection, confidence modeling, score
prediction, or adaptive recommendations here. Those are Phase 1B."""
import logging
from typing import Optional

from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.services import skill_graph

logger = logging.getLogger(__name__)

MIN_SCORE = 0
MAX_SCORE = 6

# Mirrors skill_graph.WEAKNESS_MIN_ATTEMPTS / WEAKNESS_BAND_CEILING -- same
# "don't brand a skill off one lucky attempt" reasoning, applied to the
# learner-facing mastery bucket instead of the weakness list.
MASTERY_MIN_ATTEMPTS = 2
MASTERY_STRONG_BAND_FLOOR = 5.0
MASTERY_IMPROVING_BAND_FLOOR = 3.0


def technique_skill_tag(skill_tag: str) -> str:
    return f"technique:{skill_tag}"


def mastery_level(attempts: int, ema_score: Optional[float]) -> str:
    """Pure. Not Started -> Practicing -> Improving -> Strong, bucketed off
    the same user_skill_stats attempts/ema_score skill_graph already tracks
    -- no new progress table, just a read of the existing numbers."""
    if attempts <= 0 or ema_score is None:
        return "not_started"
    if attempts < MASTERY_MIN_ATTEMPTS:
        return "practicing"
    if ema_score >= MASTERY_STRONG_BAND_FLOOR:
        return "strong"
    if ema_score >= MASTERY_IMPROVING_BAND_FLOOR:
        return "improving"
    return "practicing"


def _log_observation_sync(user_id: str, tag: str, score: float) -> None:
    get_supabase().table("skill_observations").insert({
        "user_id": user_id,
        "skill_tag": tag,
        "score": score,
        "source_module": "technique_practice",
    }).execute()


async def record_technique_progress(user_id: str, skill_tag: str, score: Optional[float]) -> None:
    """Best-effort, same contract as skill_graph.record_skill_observations --
    a bookkeeping failure here must never break the caller's own attempt
    submission. Silently no-ops on a missing, non-numeric, or out-of-range
    score (e.g. an AI grading provider_failure, or a model that returned its
    score as a JSON string despite instructions) rather than polluting the
    skill graph with a fake 0 or raising into the caller's request."""
    if isinstance(score, bool):  # bool is an int subclass -- True/False must not silently become 1.0/0.0
        return
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        return
    if not (MIN_SCORE <= score_value <= MAX_SCORE):
        return
    score = score_value
    tag = technique_skill_tag(skill_tag)
    await skill_graph.record_skill_observations(user_id, {tag: score})

    # ponytail: skill_observations (migration 20260808020000) is not yet
    # applied to production as of 2026-08-10 (verified directly against the
    # live schema) -- best-effort so that pending-migration gap can never
    # break technique grading. Starts logging for real the moment that
    # migration ships; drop this try/except once it's confirmed live.
    try:
        await run_sync(_log_observation_sync, user_id, tag, score)
    except Exception as e:
        logger.warning(
            "[TECHNIQUE_OBSERVATION_LOG_FAILED] user_id=%s tag=%s error=%s",
            user_id, tag, str(e)[:300],
        )
