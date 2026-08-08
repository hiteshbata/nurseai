"""Admin endpoints for the AI Content Studio.

RC3.1 (dashboard + library + detail) is read-only. RC3.2 adds the AI Draft
Generator: /generate calls the AI and returns unpersisted draft(s); /drafts
persists them to generated_content_drafts ONLY -- never to a production
content table (scenarios/reading_passages/listening_sections). No
publishing, review workflow, or version history here; see
app/services/draft_generator.py and app/services/draft_store.py.

See docs/CONTENT_FOUNDATION.md for the target metadata model RC3.1 scaffolds
toward, and app/services/content_studio.py for the read-side aggregation.

require_admin only (not require_analyst) -- this exposes unpublished
content across every module, per CTO review.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.supabase import get_supabase
from app.routers.admin import require_admin, _write_audit_log
from app.routers.auth import UserInfo
from app.services import content_studio, draft_generator, draft_store

router = APIRouter(prefix="/admin/content-studio", tags=["admin"])

DRAFT_MODULES = ("speaking", "reading", "listening", "writing", "vocab", "grammar")
_generate_rate_limiter = SlidingWindowRateLimiter(20, 600, name="content-studio:generate")


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


# ── AI DRAFT GENERATOR (RC3.2) ────────────────────────────────────────

class GenerateDraftsRequest(BaseModel):
    module: str
    difficulty: str = Field(min_length=1, max_length=50)
    specialty: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=300)
    objectives: Optional[str] = Field(default=None, max_length=1000)
    instructions: Optional[str] = Field(default=None, max_length=1000)
    count: int = Field(default=1, ge=1, le=3)


@router.post("/generate")
async def generate_drafts(req: GenerateDraftsRequest, current_user: UserInfo = Depends(require_admin)):
    """Generate up to 3 draft(s) for one module. Returns them unpersisted --
    nothing is written anywhere. Regeneration is just calling this again."""
    if req.module not in DRAFT_MODULES:
        raise HTTPException(status_code=400, detail=f"module must be one of: {DRAFT_MODULES}")
    if _generate_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many generations -- please slow down.")

    supabase = get_supabase()
    results: List[Dict[str, Any]] = []
    for _ in range(req.count):
        try:
            draft = await draft_generator.generate_draft(
                module=req.module, difficulty=req.difficulty, specialty=req.specialty,
                topic=req.topic, objectives=req.objectives, instructions=req.instructions,
                admin_user_id=current_user.id,
            )
            results.append({"success": True, **draft})
        except draft_generator.DraftGenerationError as e:
            results.append({"success": False, "error": str(e)})

    _write_audit_log(
        supabase, current_user, "draft_generated", "generated_content_draft",
        target_label=req.topic,
        detail={"module": req.module, "count": req.count, "difficulty": req.difficulty, "specialty": req.specialty},
    )
    return {"results": results}


class SaveDraftRequest(BaseModel):
    module: str
    draft_name: str = Field(min_length=1, max_length=200)
    ai_title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    prompt: Dict[str, Any] = Field(default_factory=dict)
    generated_content: Dict[str, Any]
    validation_warnings: List[str] = Field(default_factory=list)
    model_used: Optional[str] = None


@router.post("/drafts")
def save_draft(req: SaveDraftRequest, current_user: UserInfo = Depends(require_admin)):
    """Persist a generated draft to generated_content_drafts. Status is
    always 'draft' -- this never publishes and never touches a production
    content table."""
    if req.module not in DRAFT_MODULES:
        raise HTTPException(status_code=400, detail=f"module must be one of: {DRAFT_MODULES}")
    if not req.generated_content:
        raise HTTPException(status_code=400, detail="generated_content is required")

    created = draft_store.create_draft(
        module=req.module, draft_name=req.draft_name.strip(), ai_title=req.ai_title,
        metadata=req.metadata, prompt=req.prompt, generated_content=req.generated_content,
        validation_warnings=req.validation_warnings, model_used=req.model_used,
        created_by=current_user.id,
    )
    _write_audit_log(
        get_supabase(), current_user, "draft_saved", "generated_content_draft",
        target_id=created["id"], target_label=req.draft_name,
        detail={"module": req.module},
    )
    return created


@router.get("/drafts")
def list_drafts(
    module: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: UserInfo = Depends(require_admin),
):
    return draft_store.list_drafts(module=module, status=status, limit=limit, offset=offset)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int, current_user: UserInfo = Depends(require_admin)):
    draft = draft_store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


class RenameDraftRequest(BaseModel):
    draft_name: str = Field(min_length=1, max_length=200)


@router.patch("/drafts/{draft_id}")
def rename_draft(draft_id: int, req: RenameDraftRequest, current_user: UserInfo = Depends(require_admin)):
    updated = draft_store.rename_draft(draft_id, req.draft_name.strip())
    if not updated:
        raise HTTPException(status_code=404, detail="Draft not found")
    _write_audit_log(
        get_supabase(), current_user, "draft_renamed", "generated_content_draft",
        target_id=draft_id, target_label=req.draft_name,
    )
    return updated


@router.delete("/drafts/{draft_id}")
def delete_draft(draft_id: int, current_user: UserInfo = Depends(require_admin)):
    if not draft_store.delete_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    _write_audit_log(
        get_supabase(), current_user, "draft_deleted", "generated_content_draft", target_id=draft_id,
    )
    return {"success": True}
