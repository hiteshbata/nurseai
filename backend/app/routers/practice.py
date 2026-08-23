"""E2.5.3: thin authenticated HTTP surface over targeted_practice
(app/services/targeted_practice.py). That service already owns weakness
resolution, content-skill mapping, dedup/rank, and plan gating -- this
router only authenticates the caller, validates `module`, and serializes
the result. No writes, no AI calls, no gating logic duplicated here.

Ships Listening only (E2.5.3 scope); Technique stays unexposed until its
own ticket."""
import logging
from dataclasses import asdict
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from app.routers.auth import UserInfo, get_current_user, get_user_supabase
from app.services.targeted_practice import get_targeted_practice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/practice", tags=["practice"])

_SUPPORTED_MODULES = {"listening"}


class RecommendedPracticeItem(BaseModel):
    content_type: str
    content_id: int
    skill_tag: str
    skill_label: str
    band: float
    match_type: str
    title: str
    part: Optional[str] = None
    difficulty: Optional[str] = None


@router.get("/recommended", response_model=List[RecommendedPracticeItem])
async def get_recommended_practice(
    module: str = Query(...),
    current_user: UserInfo = Depends(get_current_user),
    user_db: Client = Depends(get_user_supabase),
):
    if module not in _SUPPORTED_MODULES:
        raise HTTPException(status_code=400, detail=f"unsupported module: {module!r}")

    try:
        items = await get_targeted_practice(user_db, current_user.id, module, limit=3)
    except Exception as e:
        logger.warning("[PRACTICE_RECOMMENDED_FAILED] user_id=%s module=%s error=%s", current_user.id, module, str(e)[:300])
        return []

    return [asdict(i) for i in items]
