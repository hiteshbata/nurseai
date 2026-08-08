"""Read-only aggregation for the Adaptive Dashboard (RC2). Pure/thin helpers
that sit on top of the Skill Graph (app.services.skill_graph) without adding
to it -- trend and cross-module rollups are a dashboard concern, not a
skill-graph one, so they live here instead.
"""
from typing import Dict, List, Optional

from supabase import Client

from app.core.threading import run_sync
from app.services.skill_graph import get_weakness, WEAKNESS_MIN_ATTEMPTS

TREND_WINDOW = 3
TREND_STABLE_BAND = 0.3

MODULE_SKILL_PREFIXES: Dict[str, str] = {
    "speaking": "speaking:",
    "reading": "reading:skill:",
    "listening": "listening:",
    "writing": "writing:",
}


def compute_trend(scores_oldest_first: List[float]) -> str:
    """Compares the average of the most recent TREND_WINDOW submissions
    against the TREND_WINDOW before that. Needs at least 2 full windows of
    history; anything short of that can't distinguish a trend from noise."""
    if len(scores_oldest_first) < TREND_WINDOW * 2:
        return "insufficient_data"
    recent = scores_oldest_first[-TREND_WINDOW:]
    prior = scores_oldest_first[-2 * TREND_WINDOW:-TREND_WINDOW]
    diff = (sum(recent) / len(recent)) - (sum(prior) / len(prior))
    if diff >= TREND_STABLE_BAND:
        return "improving"
    if diff <= -TREND_STABLE_BAND:
        return "declining"
    return "stable"


async def get_strongest_skill(user_db: Client, user_id: str, tag_prefix: str) -> Optional[Dict]:
    """Same table and min-attempts bar as skill_graph.get_weakness, but picks
    the single highest-band skill instead of the weakest-first list (and
    skips get_weakness's band ceiling -- a strong skill is exactly what
    should surface here)."""
    rows = await run_sync(
        user_db.table("user_skill_stats").select("skill_tag, attempts, ema_score")
        .eq("user_id", user_id).like("skill_tag", f"{tag_prefix}%").execute
    )
    candidates = [r for r in rows.data if r["attempts"] >= WEAKNESS_MIN_ATTEMPTS]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: float(r["ema_score"]))
    skill = best["skill_tag"][len(tag_prefix):]
    return {
        "skill": skill,
        "label": skill.replace("_", " ").replace(":", " ").title(),
        "band": round(float(best["ema_score"]), 1),
        "attempts": best["attempts"],
    }


async def get_skill_insights(user_db: Client, user_id: str, cross_module_limit: int = 5) -> Dict:
    """One pass over the skill graph, reused for two dashboard sections:
    per-module {weakest_skill, strongest_skill} (Module Progress cards) and
    the cross-module weakest-first list (Weak Skills section). Each module's
    get_weakness() is called once and its rows feed both -- avoids calling it
    twice per module for what's ultimately the same read."""
    module_extremes: Dict[str, Dict] = {}
    cross_module: List[Dict] = []
    for module, prefix in MODULE_SKILL_PREFIXES.items():
        weakest_rows = await get_weakness(user_db, user_id, prefix)
        strongest = await get_strongest_skill(user_db, user_id, prefix)
        module_extremes[module] = {
            "weakest_skill": weakest_rows[0] if weakest_rows else None,
            "strongest_skill": strongest,
        }
        for r in weakest_rows:
            cross_module.append({**r, "module": module})
    cross_module.sort(key=lambda x: x["band"])
    return {
        "module_extremes": module_extremes,
        "weak_skills": cross_module[:cross_module_limit],
    }


def pick_weakest_module(module_averages: Dict[str, Dict]) -> Optional[str]:
    """Lowest recent-average module among those the learner has actually
    attempted. None if nothing's been attempted yet (empty-state territory)."""
    attempted = {m: v for m, v in module_averages.items() if v["submission_count"] > 0}
    if not attempted:
        return None
    return min(attempted, key=lambda m: attempted[m]["average"])


if __name__ == "__main__":
    assert compute_trend([]) == "insufficient_data"
    assert compute_trend([3.0, 3.1, 3.0, 3.0, 3.1, 3.0]) == "stable"
    assert compute_trend([2.0, 2.0, 2.0, 3.5, 3.6, 3.5]) == "improving"
    assert compute_trend([4.0, 4.0, 4.0, 2.0, 2.0, 2.0]) == "declining"

    assert pick_weakest_module({
        "speaking": {"average": 4.0, "submission_count": 3},
        "writing": {"average": 2.5, "submission_count": 2},
        "reading": {"average": 5.0, "submission_count": 0},
    }) == "writing"
    assert pick_weakest_module({
        "speaking": {"average": 0, "submission_count": 0},
    }) is None
    print("dashboard_analytics self-check OK")
