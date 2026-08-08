"""Read-only admin endpoints for the AI Content Studio (RC3.1 -- foundation
only: dashboard + library + detail. No generation, no writes, no
migrations). See docs/CONTENT_FOUNDATION.md for the target metadata model
this scaffolds toward, and app/services/content_studio.py for the
aggregation logic.

require_admin only (not require_analyst) -- this exposes unpublished
content across every module, per CTO review.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.routers.admin import require_admin
from app.routers.auth import UserInfo
from app.services import content_studio

router = APIRouter(prefix="/admin/content-studio", tags=["admin"])


@router.get("/summary")
def get_summary(current_user: UserInfo = Depends(require_admin)):
    return content_studio.get_summary()


@router.get("/items")
def list_items(
    module: Optional[str] = None,
    status: Optional[str] = None,
    difficulty: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: UserInfo = Depends(require_admin),
):
    return content_studio.list_items(
        module=module, status=status, difficulty=difficulty,
        search=search, limit=limit, offset=offset,
    )


@router.get("/items/{module}/{item_id}")
def get_item(module: str, item_id: int, current_user: UserInfo = Depends(require_admin)):
    item = content_studio.get_item(module, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    return item
