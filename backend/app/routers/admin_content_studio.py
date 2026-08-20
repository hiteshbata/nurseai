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
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.supabase import get_supabase
from app.routers.admin import require_admin, require_analyst, require_owner, _write_audit_log
from app.routers.auth import UserInfo
from app.routers.listening import AUDIO_BUCKET, _upload_to_bucket
from app.services import (
    blog_document_mapper, blog_publisher, content_studio, draft_generator,
    draft_publisher, draft_store, listening_audio, markdown_to_portable_text, sanity_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/content-studio", tags=["admin"])

DRAFT_MODULES = ("speaking", "reading", "listening", "writing", "vocab", "grammar", "blog")
_generate_rate_limiter = SlidingWindowRateLimiter(20, 600, name="content-studio:generate")

# Lowercase hyphen-separated segments only -- rejects spaces, '/', '?', '#',
# '.', and anything else that would give a slug meaning beyond a single URL
# path segment (blocks query/fragment injection and path traversal by
# construction, not by blocklist). The DB partial unique index
# (generated_content_drafts_blog_slug_uidx) is the authoritative uniqueness
# guard -- this only checks shape.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Sanity asset _ref shape (https://www.sanity.io/docs/image-type):
# image-<hex asset id>-<width>x<height>-<format>. Structural only -- no
# upload pipeline, no verification the asset actually exists in Sanity.
_COVER_IMAGE_REF_RE = re.compile(r"^image-[a-f0-9]+-\d+x\d+-[a-z0-9]+$")


def _validate_slug(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not _SLUG_RE.match(value) or len(value) > 200:
        raise ValueError(
            "slug must be lowercase letters, numbers, and hyphens only (no spaces, slashes, or leading/trailing hyphens), max 200 chars"
        )
    return value


def _validate_excerpt(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if len(value) > 200:
        raise ValueError("excerpt must be at most 200 characters")
    return value


def _validate_cover_image_ref(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if value == "":
        # Explicit clear sentinel (Module 1 Section 11 Step 15) -- omitting
        # the field means "no change" (see UpdateDraftRequest), so removing
        # an image needs a value that survives that check while still
        # meaning "no image". draft_store.update_content normalizes this to
        # NULL before it reaches the DB.
        return value
    if not _COVER_IMAGE_REF_RE.match(value) or len(value) > 200:
        raise ValueError("cover_image_ref must be a valid Sanity image asset reference (image-<id>-<w>x<h>-<format>)")
    return value


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
# Listening's dedicated Part A/B/C generator (Phase 3) has no legacy
# "part omitted" fallback the way Reading still does -- every Listening
# generation through this endpoint must pick one of the three locked
# contracts. Existing Listening legacy/PDF workflows (routers/listening.py)
# are separate endpoints and are untouched by this.
_VALID_LISTENING_PARTS = {"A", "B", "C"}


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
        if self.module == "listening" and self.part not in _VALID_LISTENING_PARTS:
            raise ValueError(f"part must be one of {sorted(_VALID_LISTENING_PARTS)} for listening; got '{self.part}'")
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
    # Blog-only (Module 1 Section 7A); every other module leaves these None
    # and the DB columns stay NULL, same as before this field existed.
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    cover_image_ref: Optional[str] = None

    _validate_slug = field_validator("slug")(_validate_slug)
    _validate_excerpt = field_validator("excerpt")(_validate_excerpt)
    _validate_cover_image_ref = field_validator("cover_image_ref")(_validate_cover_image_ref)


@router.post("/drafts")
def save_draft(req: SaveDraftRequest, current_user: UserInfo = Depends(require_admin)):
    """Persist a generated draft to generated_content_drafts. Status is
    always 'draft' -- this never publishes and never touches a production
    content table."""
    if req.module not in DRAFT_MODULES:
        raise HTTPException(status_code=400, detail=f"module must be one of: {DRAFT_MODULES}")
    if not req.generated_content:
        raise HTTPException(status_code=400, detail="generated_content is required")

    try:
        created = draft_store.create_draft(
            module=req.module, draft_name=req.draft_name.strip(), ai_title=req.ai_title,
            metadata=req.metadata, prompt=req.prompt, generated_content=req.generated_content,
            validation_warnings=req.validation_warnings, model_used=req.model_used,
            created_by=current_user.id,
            slug=req.slug, excerpt=req.excerpt, cover_image_ref=req.cover_image_ref,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except draft_store.DuplicateSlugError as e:
        raise HTTPException(status_code=409, detail=str(e))
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
    # Blog-only (Module 1 Section 7A) -- see SaveDraftRequest.
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    cover_image_ref: Optional[str] = None

    _validate_slug = field_validator("slug")(_validate_slug)
    _validate_excerpt = field_validator("excerpt")(_validate_excerpt)
    _validate_cover_image_ref = field_validator("cover_image_ref")(_validate_cover_image_ref)


@router.patch("/drafts/{draft_id}")
def update_draft(draft_id: int, req: UpdateDraftRequest, current_user: UserInfo = Depends(require_analyst)):
    """Rename and/or edit a draft's content (the RC3.3 module-aware editor's
    autosave). Writes only to generated_content_drafts -- see
    draft_store.update_content for the revision-on-change rule."""
    if (
        req.draft_name is None and req.generated_content is None and req.metadata is None
        and req.slug is None and req.excerpt is None and req.cover_image_ref is None
    ):
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        updated = draft_store.update_content(
            draft_id,
            draft_name=req.draft_name.strip() if req.draft_name else None,
            generated_content=req.generated_content,
            metadata=req.metadata,
            slug=req.slug, excerpt=req.excerpt, cover_image_ref=req.cover_image_ref,
            editor_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Draft not found")
    _write_audit_log(
        get_supabase(), current_user, "draft_saved", "generated_content_draft",
        target_id=draft_id, target_label=updated.get("draft_name"),
    )
    return updated


# ── BLOG COVER IMAGE (Module 1 Section 11) ───────────────────────────
# Uploads straight to Sanity's Assets API (see app/services/sanity_client.py
# upload_image_asset) and hands back the resulting asset _ref -- it does NOT
# write cover_image_ref itself. The caller PATCHes that ref onto the draft
# via update_draft above, same as any other Blog field edit, so it rides the
# existing autosave/validation/revision path instead of a second one.
COVER_IMAGE_MAX_BYTES = 5 * 1024 * 1024  # matches reading.py's passage-image limit
COVER_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_cover_image_rate_limiter = SlidingWindowRateLimiter(20, 600, name="content-studio:cover-image")


def _sniff_image_type(contents: bytes) -> Optional[str]:
    """Reads magic bytes rather than trusting the browser-supplied
    Content-Type header (Step 18: MIME spoofing) -- stdlib only, no new
    dependency. Only the three formats this endpoint accepts."""
    if contents[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if contents[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if contents[:4] == b"RIFF" and contents[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/drafts/{draft_id}/cover-image")
async def upload_cover_image(
    draft_id: int,
    image: UploadFile = File(...),
    current_user: UserInfo = Depends(require_analyst),
):
    """Uploads one Blog draft's cover image. Returns {cover_image_ref,
    preview_url} for the frontend to PATCH onto the draft and render
    immediately -- see update_draft's cover_image_ref handling."""
    draft = draft_store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["module"] != "blog":
        raise HTTPException(status_code=400, detail="Cover images are Blog-only")
    if _cover_image_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail="Too many uploads — please slow down.")

    if image.content_type not in COVER_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Use a JPEG, PNG, or WebP image")
    contents = await image.read()
    if len(contents) > COVER_IMAGE_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")
    if _sniff_image_type(contents) != image.content_type:
        raise HTTPException(status_code=400, detail="File contents don't match the declared image type")

    try:
        asset = sanity_client.upload_image_asset(contents, image.content_type)
    except sanity_client.SanityConfigError:
        raise HTTPException(status_code=503, detail="Sanity is not configured")
    except sanity_client.SanityDatasetIsolationError:
        raise HTTPException(status_code=503, detail="Sanity dataset isolation check failed")
    except (
        sanity_client.SanityAuthError, sanity_client.SanityInvalidRequestError,
        sanity_client.SanityRateLimitError, sanity_client.SanityAPIError, sanity_client.SanityNetworkError,
    ) as e:
        raise HTTPException(status_code=502, detail=f"Sanity upload failed: {e}")

    _write_audit_log(
        get_supabase(), current_user, "cover_image_uploaded", "generated_content_draft",
        target_id=draft_id, detail={"cover_image_ref": asset["ref"]},
    )
    return {"cover_image_ref": asset["ref"], "preview_url": asset["url"]}


# ── LISTENING DRAFT AUDIO (Phase 7A) ─────────────────────────────────
# Pre-publish audio for one extract of a locked-contract (Part A/B/C)
# listening draft. Reuses the exact TTS engine and bucket production
# sections use (app/services/listening_audio.py, listening-audio bucket) --
# only the storage path and the write target (one extract inside
# generated_content, via draft_store.update_content) differ from
# listening.py's generate_section_audio.
_draft_audio_rate_limiter = SlidingWindowRateLimiter(15, 600, name="content-studio:generate-audio")


class GenerateDraftAudioRequest(BaseModel):
    extract_index: int = Field(ge=0)
    voices: Optional[Dict[str, str]] = None  # speaker label -> OpenAI voice; auto-assigned if omitted
    model: Optional[str] = None  # None resolves to the "tts_openai" purpose (Admin > AI Models)


@router.post("/drafts/{draft_id}/generate-audio")
async def generate_draft_audio(
    draft_id: int,
    req: GenerateDraftAudioRequest,
    current_user: UserInfo = Depends(require_admin),
):
    """Generate one extract's audio from its own transcript and write the
    result back onto just that extract. Sibling extracts, and any audio they
    already carry, are untouched -- generated_content is rebuilt with only
    extracts[extract_index] replaced, then handed to
    draft_store.update_content() so the normal revision/review-demote
    workflow applies exactly as it would to a manual content edit."""
    if _draft_audio_rate_limiter.is_rate_limited(current_user.id):
        raise HTTPException(status_code=429, detail={"code": "rate_limited", "message": "Too many generations — please slow down."})

    draft = draft_store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found", "message": "Draft not found"})
    if draft["module"] != "listening":
        raise HTTPException(status_code=400, detail={"code": "not_listening_draft", "message": "Audio generation is only for listening drafts"})

    content = draft["generated_content"] or {}
    extracts = content.get("extracts")
    if not isinstance(extracts, list) or not extracts:
        raise HTTPException(status_code=400, detail={"code": "invalid_extract_index", "message": "Draft has no extracts[] to generate audio for"})
    if req.extract_index >= len(extracts):
        raise HTTPException(status_code=400, detail={"code": "invalid_extract_index", "message": f"extract_index must be between 0 and {len(extracts) - 1}"})

    extract = extracts[req.extract_index]
    turns = extract.get("transcript")
    if not isinstance(turns, list) or not turns:
        raise HTTPException(status_code=400, detail={"code": "transcript_missing", "message": "This extract has no transcript to voice"})

    try:
        audio_bytes = await listening_audio.generate_two_speaker_audio(turns, req.voices, req.model)
    except listening_audio.TtsError as e:
        raise HTTPException(status_code=400, detail={"code": "audio_generation_failed", "message": str(e)})
    except Exception as e:
        logger.error("[content-studio audio] draft %s extract %s generation failed: %s", draft_id, req.extract_index, str(e)[:300])
        raise HTTPException(status_code=502, detail={"code": "audio_generation_failed", "message": "Audio generation failed. Try again."})

    duration = await listening_audio.probe_duration_seconds(audio_bytes)
    audio_transcript_hash = listening_audio.transcript_hash(turns)
    path = f"drafts/{draft_id}/extracts/{req.extract_index}/{uuid.uuid4().hex}.mp3"

    try:
        audio_url = await _upload_to_bucket(path, audio_bytes, "audio/mpeg")
    except Exception as e:
        logger.error("[content-studio audio] draft %s extract %s upload failed: %s", draft_id, req.extract_index, str(e)[:300])
        raise HTTPException(status_code=502, detail={"code": "storage_upload_failed", "message": "Audio was generated but could not be stored. Try again."})

    generated_at = datetime.now(timezone.utc).isoformat()
    new_extracts = list(extracts)
    new_extracts[req.extract_index] = {
        **extract,
        "audio_url": audio_url,
        "audio_generated_at": generated_at,
        "audio_duration_seconds": duration,
        "audio_transcript_hash": audio_transcript_hash,
    }
    new_content = {**content, "extracts": new_extracts}

    def _cleanup_orphaned_object():
        try:
            get_supabase().storage.from_(AUDIO_BUCKET).remove([path])
        except Exception:
            logger.exception("[content-studio audio] cleanup of orphaned object %s also failed", path)

    try:
        updated_draft = draft_store.update_content(draft_id, generated_content=new_content, editor_id=current_user.id)
    except Exception:
        logger.exception("[content-studio audio] draft %s extract %s: audio stored but draft update failed", draft_id, req.extract_index)
        _cleanup_orphaned_object()
        raise HTTPException(status_code=502, detail={"code": "audio_generation_failed", "message": "Audio was generated but the draft could not be updated. Try again."})
    if not updated_draft:
        # Draft was deleted between the fetch above and this write.
        _cleanup_orphaned_object()
        raise HTTPException(status_code=404, detail={"code": "draft_not_found", "message": "Draft not found"})

    _write_audit_log(
        get_supabase(), current_user, "draft_audio_generated", "generated_content_draft",
        target_id=draft_id, detail={"extract_index": req.extract_index, "duration_seconds": duration},
    )

    return {
        "extract_index": req.extract_index,
        "audio_url": audio_url,
        "duration_seconds": duration,
        "audio_generated_at": generated_at,
        "audio_transcript_hash": audio_transcript_hash,
    }


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


def _audio_not_ready_detail(e: "draft_publisher.AudioNotReadyError") -> Dict[str, Any]:
    return {
        "error": e.reason,
        "part": e.part,
        "missing_audio_indexes": e.missing_indexes,
        "outdated_audio_indexes": e.outdated_indexes,
        "message": str(e),
    }


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
    except draft_publisher.AudioNotReadyError as e:
        raise HTTPException(status_code=409, detail=_audio_not_ready_detail(e))


def _publish_blog_draft(draft: Dict[str, Any], current_user: UserInfo) -> Dict[str, Any]:
    """Blog's publish path (Module 1 Section 12D). Blog's production system
    is Sanity, not a Supabase table -- draft_publisher has no 'blog' entry
    and must stay that way (see test_blog_publish_still_blocked_not_publishable)
    -- so this drives blog_publisher (12A-12C, untouched) and draft_store
    directly instead. There is no transaction spanning Postgres and Sanity:
    Supabase is only ever flipped to 'published' AFTER Sanity confirms the
    document is live, never before and never speculatively.

    Definite failures (invalid content, Sanity rejection) leave the draft
    'approved' and are safe to retry after the admin fixes the problem.
    Uncertain outcomes (Sanity confirmation failed, or Sanity published but
    the Supabase write then failed) also leave the draft 'approved' -- but
    are NOT safe to retry via a second create+publish, because Sanity may
    already be live. Reconciliation for both is the same action: click
    Publish again. blog_publisher.publish_sanity_draft's own idempotency
    check (it reads the published document back before writing anything)
    means a retry that finds Sanity already published skips straight to the
    Supabase write below instead of writing Sanity a second time.
    """
    draft_id = draft["id"]
    supabase = get_supabase()
    published_id = sanity_client.sanity_blog_document_id(draft_id)

    # Anchors the Sanity publishedAt on republish. Sanity's own document is
    # the source of truth for "when did this post first go live" -- not
    # this draft's own published_at column, which (like every other module)
    # is legitimately re-stamped with "now" on every publish, including
    # republishes; reusing it here would reset a post's publish date on
    # every edit.
    try:
        existing_sanity_doc = sanity_client.get_document(published_id)
    except (
        sanity_client.SanityAuthError, sanity_client.SanityInvalidRequestError,
        sanity_client.SanityRateLimitError, sanity_client.SanityAPIError,
        sanity_client.SanityNetworkError, sanity_client.SanityConfigError,
    ):
        logger.exception("Blog draft %s: could not look up existing Sanity document %s", draft_id, published_id)
        raise HTTPException(status_code=502, detail="Blog was not published. Please correct the issue and retry.")
    existing_published_at = (existing_sanity_doc or {}).get("publishedAt")

    try:
        result = blog_publisher.publish_sanity_draft(
            draft,
            publish_time=datetime.now(timezone.utc).isoformat(),
            existing_published_at=existing_published_at,
        )
    except (
        blog_document_mapper.BlogDocumentValidationError,
        markdown_to_portable_text.UnsupportedImageError,
        markdown_to_portable_text.UnsupportedTableError,
    ) as e:
        _write_audit_log(
            supabase, current_user, "draft_publish_failed", "generated_content_draft",
            target_id=draft_id, detail={"reason": "invalid_content", "error": str(e)},
        )
        raise HTTPException(status_code=400, detail="Blog was not published. Please correct the issue and retry.")
    except blog_publisher.BlogPublicationError as e:
        _write_audit_log(
            supabase, current_user, "draft_publish_failed", "generated_content_draft",
            target_id=draft_id, detail={"reason": "sanity_rejected", "error": str(e)},
        )
        raise HTTPException(status_code=502, detail="Blog was not published. Please correct the issue and retry.")
    except blog_publisher.BlogPublicationUncertainError as e:
        _write_audit_log(
            supabase, current_user, "draft_publish_uncertain", "generated_content_draft",
            target_id=draft_id, detail={"reason": "sanity_confirmation_failed", "sanity_document_id": published_id, "error": str(e)},
        )
        raise HTTPException(
            status_code=502,
            detail="Publication may have succeeded, but the final status could not be confirmed. Reconciliation is required.",
        )

    try:
        draft_store.mark_published(draft_id, current_user.id)
    except draft_store.InvalidTransitionError:
        # Draft is no longer 'approved' -- another request already flipped it
        # to 'published' between this request's status check and this call
        # (Step 14: concurrent Publish clicks). Sanity content is confirmed
        # consistent regardless of which request's write "won", so Supabase
        # is already correct; there is nothing more to write.
        _write_audit_log(
            supabase, current_user, "draft_published", "generated_content_draft",
            target_id=draft_id, detail={**result, "concurrent_publish": True},
        )
        return result
    except Exception:
        # Case D: Sanity published, Supabase update failed. Do not unpublish
        # Sanity, do not fabricate a 'published' Supabase row -- surface the
        # inconsistency and let the same idempotent Publish click reconcile it.
        logger.exception("Blog draft %s: Sanity publish confirmed but Supabase status update failed", draft_id)
        _write_audit_log(
            supabase, current_user, "draft_publish_uncertain", "generated_content_draft",
            target_id=draft_id, detail={"reason": "supabase_update_failed", "sanity_document_id": published_id},
        )
        raise HTTPException(
            status_code=502,
            detail="Publication may have succeeded, but the final status could not be confirmed. Reconciliation is required.",
        )

    _write_audit_log(
        supabase, current_user, "draft_published", "generated_content_draft",
        target_id=draft_id, detail=result,
    )
    return result


@router.post("/drafts/{draft_id}/publish")
def publish_draft(draft_id: int, current_user: UserInfo = Depends(require_owner)):
    """Copies an approved draft into production. The draft row is kept and
    flipped to 'published' -- it is never deleted or moved."""
    draft = draft_store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "approved":
        raise HTTPException(status_code=409, detail="Only approved drafts can be published")

    if draft["module"] == "blog":
        return _publish_blog_draft(draft, current_user)

    try:
        result = draft_publisher.publish(draft, current_user.id)
    except draft_publisher.AudioNotReadyError as e:
        raise HTTPException(status_code=409, detail=_audio_not_ready_detail(e))
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
