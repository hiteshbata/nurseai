"""Vocab SRS deck (SM-2). Cards are auto-added when a student looks up an
unfamiliar term via the Reading/Listening dictionary lookup (see
reading.py's get_definition/_lookup_definition) -- this router only handles
reviewing the deck, not adding to it."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.routers.auth import get_current_user, UserInfo
from app.services.srs import sm2_review, SRSState

router = APIRouter(prefix="/vocab", tags=["vocab"])

DUE_CARDS_LIMIT = 30


@router.get("/due")
async def list_due_cards(current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    data = await run_sync(
        supabase.table("vocab_cards").select("id, term, definition, source_module")
        .eq("user_id", current_user.id).lte("due_at", now)
        .order("due_at").limit(DUE_CARDS_LIMIT).execute
    )
    return data.data


@router.get("/count")
async def due_count(current_user: UserInfo = Depends(get_current_user)):
    """Lightweight badge count for the Study Hub / nav."""
    supabase = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    data = await run_sync(
        supabase.table("vocab_cards").select("id", count="exact")
        .eq("user_id", current_user.id).lte("due_at", now).execute
    )
    return {"due": data.count or 0}


class ReviewRequest(BaseModel):
    card_id: int
    quality: int  # 0-5 SM-2 scale -- frontend offers "Again" (2) / "Good" (4)


@router.post("/review")
async def review_card(req: ReviewRequest, current_user: UserInfo = Depends(get_current_user)):
    supabase = get_supabase()
    card = await run_sync(
        supabase.table("vocab_cards").select("id, ease, interval_days, reps")
        .eq("id", req.card_id).eq("user_id", current_user.id).execute
    )
    if not card.data:
        raise HTTPException(status_code=404, detail="Card not found")
    row = card.data[0]

    state = SRSState(ease=float(row["ease"]), interval_days=row["interval_days"], reps=row["reps"])
    next_state = sm2_review(state, req.quality)
    due_at = datetime.now(timezone.utc) + timedelta(days=next_state.interval_days)

    await run_sync(
        supabase.table("vocab_cards").update({
            "ease": next_state.ease,
            "interval_days": next_state.interval_days,
            "reps": next_state.reps,
            "due_at": due_at.isoformat(),
        }).eq("id", req.card_id).execute
    )
    return {"success": True, "due_at": due_at.isoformat(), "interval_days": next_state.interval_days}
