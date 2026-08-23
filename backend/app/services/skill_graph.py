"""The Weakness Graph: a per-user, per-skill exponential moving average on
the same 0-6 OET band scale everything else already uses (reading/listening
band, speaking overall_band, writing per-criterion score), so any module's
signal is directly comparable to any other's. Every module tags its own
observations (e.g. "reading:B", "speaking:fluency", "listening:accent:UK")
and calls record_skill_observations after grading -- this is the shared spine
the Study Hub, revision queue, and (later) predicted grade all read from."""
import logging
from typing import Callable, Dict, List, Optional

from app.core.supabase import get_supabase
from app.core.threading import run_sync
from supabase import Client

logger = logging.getLogger(__name__)

EMA_ALPHA = 0.3  # weight on the newest observation; higher = more reactive to recent attempts

PRODUCT = "OET"  # only exam product today; see 20260808010000_learner_brain_product_column.sql

# Ignore a skill until the student has attempted it a couple of times, so one
# unlucky question doesn't brand a whole skill as a weakness.
WEAKNESS_MIN_ATTEMPTS = 2
# Bands at/above this read as "solid" -- only surface genuine weak spots.
WEAKNESS_BAND_CEILING = 5.0


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
        .eq("user_id", user_id).eq("product", PRODUCT).in_("skill_tag", tags).execute()
    )
    existing_by_tag = {row["skill_tag"]: row for row in existing.data}

    rows = []
    for tag, score in tag_scores.items():
        prev = existing_by_tag.get(tag)
        attempts = prev["attempts"] if prev else 0
        old_ema = float(prev["ema_score"]) if prev else 0.0
        rows.append({
            "user_id": user_id,
            "product": PRODUCT,
            "skill_tag": tag,
            "attempts": attempts + 1,
            "ema_score": update_ema(old_ema, attempts, float(score)),
        })
    supabase.table("user_skill_stats").upsert(rows, on_conflict="user_id,product,skill_tag").execute()


async def record_skill_observations(user_id: str, tag_scores: Dict[str, float]) -> None:
    """Best-effort: a bookkeeping failure here must never break the module's
    own scoring/submission flow, so every caller fires this after its own
    submission is already saved and just logs on failure. Callers are
    expected to have already validated tag_scores (see
    app/services/observation_service.py) -- this function only aggregates."""
    if not tag_scores:
        return
    try:
        await run_sync(_record_sync, user_id, tag_scores)
    except Exception as e:
        logger.warning("[SKILL_GRAPH_RECORD_FAILED] user_id=%s error=%s", user_id, str(e)[:300])


async def get_weakness(
    user_db: Client,
    user_id: str,
    tag_prefix: str,
    label_fn: Optional[Callable[[str], str]] = None,
) -> List[Dict]:
    """The student's weakest skills under `tag_prefix` (e.g. "reading:skill:",
    "speaking:", "writing:", "listening:"), weakest first, off the shared EMA
    every module's grading already feeds. Read-only, no AI. Returns [] until
    there's enough signal. One implementation shared by every module's
    /weakness endpoint instead of four near-identical copies."""
    rows = await run_sync(
        user_db.table("user_skill_stats").select("skill_tag, attempts, ema_score")
        .eq("user_id", user_id).like("skill_tag", f"{tag_prefix}%").execute
    )
    out = []
    for r in rows.data:
        if r["attempts"] < WEAKNESS_MIN_ATTEMPTS:
            continue
        band = float(r["ema_score"])
        if band >= WEAKNESS_BAND_CEILING:
            continue
        skill = r["skill_tag"][len(tag_prefix):]
        label = label_fn(skill) if label_fn else skill.replace("_", " ").replace(":", " ").title()
        out.append({"skill": skill, "label": label, "band": round(band, 1), "attempts": r["attempts"]})
    out.sort(key=lambda x: x["band"])
    return out
