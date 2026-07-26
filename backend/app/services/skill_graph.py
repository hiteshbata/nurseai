"""The Weakness Graph: a per-user, per-skill exponential moving average on
the same 0-6 OET band scale everything else already uses (reading/listening
band, speaking overall_band, writing per-criterion score), so any module's
signal is directly comparable to any other's. Every module tags its own
observations (e.g. "reading:B", "speaking:fluency", "listening:accent:UK")
and calls record_skill_observations after grading -- this is the shared spine
the Study Hub, revision queue, and (later) predicted grade all read from."""
import logging
from typing import Dict

from app.core.supabase import get_supabase
from app.core.threading import run_sync

logger = logging.getLogger(__name__)

EMA_ALPHA = 0.3  # weight on the newest observation; higher = more reactive to recent attempts


def update_ema(old_ema: float, attempts: int, new_score: float, alpha: float = EMA_ALPHA) -> float:
    """Pure. The first-ever observation for a skill IS the ema (nothing to
    blend with yet)."""
    if attempts == 0:
        return round(new_score, 2)
    return round(alpha * new_score + (1 - alpha) * old_ema, 2)


def _record_sync(user_id: str, tag_scores: Dict[str, float]) -> None:
    supabase = get_supabase()
    tags = list(tag_scores.keys())
    existing = (
        supabase.table("user_skill_stats").select("skill_tag, attempts, ema_score")
        .eq("user_id", user_id).in_("skill_tag", tags).execute()
    )
    existing_by_tag = {row["skill_tag"]: row for row in existing.data}

    rows = []
    for tag, score in tag_scores.items():
        prev = existing_by_tag.get(tag)
        attempts = prev["attempts"] if prev else 0
        old_ema = float(prev["ema_score"]) if prev else 0.0
        rows.append({
            "user_id": user_id,
            "skill_tag": tag,
            "attempts": attempts + 1,
            "ema_score": update_ema(old_ema, attempts, float(score)),
        })
    supabase.table("user_skill_stats").upsert(rows, on_conflict="user_id,skill_tag").execute()


async def record_skill_observations(user_id: str, tag_scores: Dict[str, float]) -> None:
    """Best-effort: a bookkeeping failure here must never break the module's
    own scoring/submission flow, so every caller fires this after its own
    submission is already saved and just logs on failure."""
    if not tag_scores:
        return
    try:
        await run_sync(_record_sync, user_id, tag_scores)
    except Exception as e:
        logger.warning("[SKILL_GRAPH_RECORD_FAILED] user_id=%s error=%s", user_id, str(e)[:300])
