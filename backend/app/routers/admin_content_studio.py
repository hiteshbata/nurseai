"""Admin endpoints for the AI Content Studio.

RC3.1 (dashboard + library + detail) is read-only. RC3.2 added the AI Draft
Generator: /generate calls the AI and returns unpersisted draft(s); /drafts
persists them to generated_content_drafts ONLY. RC3.3 adds the human
review/publish workflow on top -- see app/services/draft_store.py for the
status machine and app/services/draft_publisher.py for the one place that
actually writes to a production content table (scenarios/reading_passages/
listening_sections), always by copying a draft, never moving it.

See docs/CONTENT_FOUNDATION.md for the target metadata model RC3.1 scaffolds
toward, and app/services/content_studio.py for the read-side aggregation.

Permission tiers (CTO decision, RC3.3): analyst can view/edit drafts, admin
can review/approve/reject/archive, owner can publish/unpublish. Generating
new drafts (AI cost) and hard-deleting a draft stay admin-only, unchanged
from RC3.2. RC3.1's read-only production-content endpoints below are
untouched, still admin-only.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.supabase import get_supabase
from app.routers.admin import require_admin, require_analyst, require_owner, _write_audit_log
from app.routers.auth import UserInfo
from app.services import content_studio, draft_generator, draft_publisher, draft_store

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

# "A", "B", and "C" are wired to real prompt branches/validators (Phase
# 3B-5, 4A, 4C-3) -- reject anything else rather than silently dropping or
# coercing it.
_VALID_READING_PARTS = {"A", "B", "C"}


class GenerateDraftsRequest(BaseModel):
    module: str
    difficulty: str = Field(min_length=1, max_length=50)
    specialty: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=300)
    objectives: Optional[str] = Field(default=None, max_length=1000)
    instructions: Optional[str] = Field(default=None, max_length=1000)
    count: int = Field(default=1, ge=1, le=3)
    part: Optional[str] = Field(default=None, max_length=1)

    @model_validator(mode="after")
    def _validate_reading_part(self):
        if self.module == "reading" and self.part is not None and self.part not in _VALID_READING_PARTS:
            raise ValueError(f"part must be one of {sorted(_VALID_READING_PARTS)} for reading; got '{self.part}'")
        return self


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
                admin_user_id=current_user.id, part=req.part,
            )
            results.append({"success": True, **draft})
        except draft_generator.DraftGenerationError as e:
            results.append({"success": False, "error": str(e)})

    _write_audit_log(
        supabase, current_user, "draft_generated", "generated_content_draft",
        target_label=req.topic,
        detail={"module": req.module, "count": req.count, "difficulty": req.difficulty, "specialty": req.specialty, "part": req.part},
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
    current_user: UserInfo = Depends(require_analyst),
):
    return draft_store.list_drafts(module=module, status=status, limit=limit, offset=offset)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int, current_user: UserInfo = Depends(require_analyst)):
    draft = draft_store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


class UpdateDraftRequest(BaseModel):
    draft_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    generated_content: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


@router.patch("/drafts/{draft_id}")
def update_draft(draft_id: int, req: UpdateDraftRequest, current_user: UserInfo = Depends(require_analyst)):
    """Rename and/or edit a draft's content (the RC3.3 module-aware editor's
    autosave). Writes only to generated_content_drafts -- see
    draft_store.update_content for the revision-on-change rule."""
    if req.draft_name is None and req.generated_content is None and req.metadata is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    updated = draft_store.update_content(
        draft_id,
        draft_name=req.draft_name.strip() if req.draft_name else None,
        generated_content=req.generated_content,
        metadata=req.metadata,
        editor_id=current_user.id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Draft not found")
    _write_audit_log(
        get_supabase(), current_user, "draft_saved", "generated_content_draft",
        target_id=draft_id, target_label=updated.get("draft_name"),
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


# ── REVIEW / APPROVAL / PUBLISH WORKFLOW (RC3.3) ─────────────────────

@router.get("/drafts/{draft_id}/revisions")
def get_draft_revisions(draft_id: int, current_user: UserInfo = Depends(require_analyst)):
    if not draft_store.get_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft_store.list_revisions(draft_id)


@router.post("/drafts/{draft_id}/submit-review")
def submit_draft_for_review(draft_id: int, current_user: UserInfo = Depends(require_analyst)):
    try:
        updated = draft_store.submit_for_review(draft_id)
    except draft_store.InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Draft not found")
    _write_audit_log(
        get_supabase(), current_user, "draft_reviewed", "generated_content_draft",
        target_id=draft_id, detail={"transition": "draft->review"},
    )
    return updated


@router.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, current_user: UserInfo = Depends(require_admin)):
    try:
        updated = draft_store.approve(draft_id, current_user.id)
    except draft_store.InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Draft not found")
    _write_audit_log(
        get_supabase(), current_user, "draft_approved", "generated_content_draft", target_id=draft_id,
    )
    return updated


@router.post("/drafts/{draft_id}/reject")
def reject_draft(draft_id: int, current_user: UserInfo = Depends(require_admin)):
    """Sends a draft back one stage: review->draft, or approved->review."""
    try:
        updated = draft_store.reject(draft_id, current_user.id)
    except draft_store.InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Draft not found")
    _write_audit_log(
        get_supabase(), current_user, "draft_reviewed", "generated_content_draft",
        target_id=draft_id, detail={"transition": f"->{updated['status']}", "action": "reject"},
    )
    return updated


@router.post("/drafts/{draft_id}/archive")
def archive_draft(draft_id: int, current_user: UserInfo = Depends(require_admin)):
    try:
        updated = draft_store.archive(draft_id)
    except draft_store.InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Draft not found")
    _write_audit_log(
        get_supabase(), current_user, "draft_archived", "generated_content_draft", target_id=draft_id,
    )
    return updated


@router.get("/drafts/{draft_id}/publish-preview")
def get_publish_preview(draft_id: int, current_user: UserInfo = Depends(require_owner)):
    """Dry run for the Publish Preview dialog -- returns exactly which
    production record(s) Publish would create, without writing anything."""
    draft = draft_store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "approved":
        raise HTTPException(status_code=409, detail="Only approved drafts can be published")
    try:
        return draft_publisher.build_preview(draft)
    except (draft_publisher.NotPublishableError, draft_publisher.InvalidPartError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/drafts/{draft_id}/publish")
def publish_draft(draft_id: int, current_user: UserInfo = Depends(require_owner)):
    """Copies an approved draft into production. The draft row is kept and
    flipped to 'published' -- it is never deleted or moved."""
    draft = draft_store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "approved":
        raise HTTPException(status_code=409, detail="Only approved drafts can be published")
    try:
        result = draft_publisher.publish(draft, current_user.id)
    except (draft_publisher.NotPublishableError, draft_publisher.InvalidPartError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (draft_publisher.DuplicateTitleError, draft_publisher.AlreadyPublishedError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    draft_store.mark_published(draft_id, current_user.id)
    _write_audit_log(
        get_supabase(), current_user, "draft_published", "generated_content_draft",
        target_id=draft_id, detail=result,
    )
    return result


@router.post("/drafts/{draft_id}/unpublish")
def unpublish_draft(draft_id: int, current_user: UserInfo = Depends(require_owner)):
    """Sets is_active=false on the production row this draft published --
    no manual DB access required. Draft status stays 'published' (the
    production row's own visibility is what changed, not the draft)."""
    draft = draft_store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "published":
        raise HTTPException(status_code=409, detail="Only published drafts can be unpublished")
    try:
        result = draft_publisher.unpublish(draft)
    except draft_publisher.NotPublishableError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    _write_audit_log(
        get_supabase(), current_user, "draft_unpublished", "generated_content_draft",
        target_id=draft_id, detail=result,
    )
    return result
