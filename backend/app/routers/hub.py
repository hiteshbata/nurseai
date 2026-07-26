"""Study Hub: the daily landing surface that turns four separate practice
tools into one coach. Reads the Weakness Graph (app/services/skill_graph.py)
that every module already writes to -- this router has no scoring logic of
its own, it only summarizes what's already there.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.routers.auth import get_current_user, UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hub", tags=["hub"])

STREAK_LOOKBACK_DAYS = 60
PLAN_SIZE = 3
REVISION_QUEUE_LIMIT = 10
MODULES = ["speaking", "writing", "reading", "listening"]


# ── PURE HELPERS (testable) ───────────────────────────────────────────

def describe_skill_tag(tag: str) -> Dict[str, str]:
    """"reading:B" -> Reading Part B / /practice/reading
    "listening:accent:UK" -> Listening — UK accent / /practice/listening
    "speaking:fluency" -> Speaking — Fluency / /practice/speaking"""
    parts = tag.split(":")
    module = parts[0]
    href = f"/practice/{module}" if module in MODULES else "/dashboard"

    if module in ("reading", "listening") and len(parts) == 2 and parts[1] in ("A", "B", "C"):
        label = f"{module.title()} Part {parts[1]}"
    elif module == "listening" and len(parts) == 3 and parts[1] == "accent":
        label = f"Listening — {parts[2]} accent"
    elif len(parts) >= 2:
        label = f"{module.title()} — {parts[1].replace('_', ' ').title()}"
    else:
        label = module.title()

    return {"skill_tag": tag, "label": label, "href": href}


def compute_streak(activity_dates: set, today: date) -> int:
    """Pure. Consecutive days of activity ending today or yesterday (a
    streak someone hasn't broken yet by the time they check today)."""
    if today in activity_dates:
        cursor = today
    elif (today - timedelta(days=1)) in activity_dates:
        cursor = today - timedelta(days=1)
    else:
        return 0

    streak = 0
    while cursor in activity_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def build_daily_plan(weakest: List[dict], attempted_modules: set) -> List[dict]:
    """Pure. Worst PLAN_SIZE skills first; a brand-new user with no skill
    history yet gets a "try each module once" starter plan instead of an
    empty page."""
    if weakest:
        return [describe_skill_tag(row["skill_tag"]) for row in weakest[:PLAN_SIZE]]
    return [
        {"skill_tag": f"{m}:intro", "label": f"Try {m.title()} practice", "href": f"/practice/{m}"}
        for m in MODULES if m not in attempted_modules
    ][:PLAN_SIZE]


# ── ROUTES ─────────────────────────────────────────────────────────────

@router.get("/today")
async def get_today(current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()
    today = datetime.now(timezone.utc).date()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=STREAK_LOOKBACK_DAYS)).isoformat()

    subs = await run_sync(
        supabase.table("submissions").select("created_at, module")
        .eq("user_id", current_user.id).gte("created_at", cutoff).execute
    )
    activity_dates = {
        datetime.fromisoformat(s["created_at"]).date() for s in subs.data if s.get("created_at")
    }
    attempted_modules = {s["module"] for s in subs.data if s.get("module") in MODULES}
    streak = compute_streak(activity_dates, today)

    skills = await run_sync(
        supabase.table("user_skill_stats").select("skill_tag, ema_score, attempts")
        .eq("user_id", current_user.id).order("ema_score").execute
    )
    plan = build_daily_plan(skills.data, attempted_modules)

    completions = await run_sync(
        supabase.table("daily_goal_completions").select("task_key")
        .eq("user_id", current_user.id).eq("goal_date", today.isoformat()).execute
    )
    completed_keys = {c["task_key"] for c in completions.data}
    for item in plan:
        item["completed"] = item["skill_tag"] in completed_keys

    vocab_due = await run_sync(
        supabase.table("vocab_cards").select("id", count="exact")
        .eq("user_id", current_user.id).lte("due_at", datetime.now(timezone.utc).isoformat()).execute
    )

    return {
        "streak": streak,
        "plan": plan,
        "vocab_due": vocab_due.count or 0,
    }


@router.get("/revision-queue")
async def get_revision_queue(current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()
    skills = await run_sync(
        supabase.table("user_skill_stats").select("skill_tag, ema_score, attempts")
        .eq("user_id", current_user.id).order("ema_score").limit(REVISION_QUEUE_LIMIT).execute
    )
    return [{**describe_skill_tag(row["skill_tag"]), "ema_score": row["ema_score"], "attempts": row["attempts"]} for row in skills.data]


class GoalCompleteRequest(BaseModel):
    task_key: str


@router.post("/goal-complete")
async def mark_goal_complete(req: GoalCompleteRequest, current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()
    today = datetime.now(timezone.utc).date().isoformat()
    await run_sync(
        supabase.table("daily_goal_completions").upsert({
            "user_id": current_user.id,
            "goal_date": today,
            "task_key": req.task_key,
        }, on_conflict="user_id,goal_date,task_key", ignore_duplicates=True).execute
    )
    return {"success": True}
