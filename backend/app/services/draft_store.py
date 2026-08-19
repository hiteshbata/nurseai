"""CRUD over generated_content_drafts (RC3.2) -- the only table AI Draft
Generator is allowed to write to. Deliberately separate from
content_studio.py, which only ever reads production content tables: keeping
the two services apart keeps "drafts never touch production" true at the
code-boundary, not just by convention.

RC3.3 adds the review/publish status machine (see _TRANSITIONS) and a
revision log -- both still write only to this table and
generated_content_draft_revisions, never to production. Actual publishing
(the one place that does touch production) lives in draft_publisher.py.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.supabase import get_supabase

# review/approved <-> draft/review are round-trippable (reject); published
# and archived are terminal for this sprint (no "unarchive", no un-publish
# back to approved -- Unpublish instead flips the production row's
# is_active, see draft_publisher.unpublish). The one other way out of
# 'approved'/'published' is update_content() below dropping straight to
# 'review' when generated_content changes -- not a click-through action, so
# it isn't listed here, but it's the same destination reject() would reach.
_TRANSITIONS: Dict[str, set] = {
    "draft": {"review"},
    "review": {"draft", "approved"},
    "approved": {"review", "published"},
}
_ARCHIVABLE_FROM = {"draft", "review", "approved"}
# An approval (or a publish, which requires one) signs off on specific
# content, not on "whatever this draft becomes later". If generated_content
# actually changes while a draft is approved/published, that sign-off no
# longer applies -- see update_content().
_REVIEW_REQUIRED_ON_CONTENT_EDIT = {"approved", "published"}


class InvalidTransitionError(Exception):
    pass


class DuplicateSlugError(Exception):
    """Raised when the DB's generated_content_drafts_blog_slug_uidx partial
    unique index rejects an insert -- the index stays the sole authority on
    uniqueness (no pre-check SELECT here, that would just reintroduce the
    race it exists to close); this only translates its rejection into an
    application-level error instead of letting the raw DB exception surface."""
    pass


# Blog-only (Module 1 Section 9). Title/body live inside generated_content
# jsonb, not a dedicated column (Section 7A decision) -- so unlike
# slug/excerpt/cover_image_ref (validated as Pydantic fields in the router)
# these need a service-layer check, run from both create_draft and
# update_content so there is exactly one choke point for "does this blog
# draft have a real title" regardless of which endpoint wrote it.
_BLOG_TITLE_MAX_LEN = 300


def _validate_blog_title(generated_content: Dict[str, Any]) -> None:
    title = (generated_content or {}).get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Blog draft requires a non-empty generated_content.title")
    if len(title) > _BLOG_TITLE_MAX_LEN:
        raise ValueError(f"Blog title must be at most {_BLOG_TITLE_MAX_LEN} characters")


def _validate_blog_completeness(draft: Dict[str, Any]) -> None:
    """Gate for entering review/approved (Section 9 Step 10). cover_image_ref
    stays optional even here -- everything else must be real content, not
    just present-but-blank."""
    gc = draft.get("generated_content") or {}
    missing = []
    if not isinstance(gc.get("title"), str) or not gc["title"].strip():
        missing.append("title")
    if not isinstance(gc.get("body"), str) or not gc["body"].strip():
        missing.append("body")
    if not draft.get("slug"):
        missing.append("slug")
    if not draft.get("excerpt"):
        missing.append("excerpt")
    if missing:
        raise InvalidTransitionError(
            f"Blog draft is missing required field(s) before review/approval: {', '.join(missing)}"
        )

COLUMNS = (
    "id, module, draft_name, ai_title, metadata, prompt, generated_content, "
    "validation_warnings, status, model_used, ai_generated, created_by, "
    "created_at, updated_at, reviewed_by, reviewed_at, approved_by, approved_at, "
    "published_by, published_at, slug, excerpt, cover_image_ref"
)
# Same shape minus the (often large) generated_content/prompt blobs -- list
# views don't need the full payload. slug included -- Blog's list view needs
# it (e.g. to link out) without a second round trip; excerpt/cover_image_ref
# don't have that need yet, so they stay out like the other omitted columns.
LIST_COLUMNS = (
    "id, module, draft_name, ai_title, status, model_used, validation_warnings, "
    "created_by, created_at, updated_at, approved_at, published_at, slug"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_draft(
    module: str,
    draft_name: str,
    ai_title: Optional[str],
    metadata: Dict[str, Any],
    prompt: Dict[str, Any],
    generated_content: Dict[str, Any],
    validation_warnings: List[str],
    model_used: Optional[str],
    created_by: str,
    slug: Optional[str] = None,
    excerpt: Optional[str] = None,
    cover_image_ref: Optional[str] = None,
) -> Dict[str, Any]:
    if module == "blog":
        _validate_blog_title(generated_content)
    supabase = get_supabase()
    try:
        row = supabase.table("generated_content_drafts").insert({
            "module": module,
            "draft_name": draft_name,
            "ai_title": ai_title,
            "metadata": metadata,
            "prompt": prompt,
            "generated_content": generated_content,
            "validation_warnings": validation_warnings,
            "model_used": model_used,
            "ai_generated": True,
            "created_by": created_by or None,
            # Blog-only (Module 1 Section 7A); every other module passes None and
            # the columns stay NULL, same as before these fields existed.
            "slug": slug,
            "excerpt": excerpt,
            "cover_image_ref": cover_image_ref,
        }).execute()
    except Exception as e:
        if "generated_content_drafts_blog_slug_uidx" in str(e):
            raise DuplicateSlugError(f"Blog slug \"{slug}\" is already in use") from e
        raise
    return row.data[0]


def list_drafts(module: Optional[str] = None, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    supabase = get_supabase()
    query = supabase.table("generated_content_drafts").select(LIST_COLUMNS, count="exact")
    if module:
        query = query.eq("module", module)
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return {"drafts": result.data, "total": result.count or 0}


def get_draft(draft_id: int) -> Optional[Dict[str, Any]]:
    supabase = get_supabase()
    rows = supabase.table("generated_content_drafts").select(COLUMNS).eq("id", draft_id).execute().data
    return rows[0] if rows else None


def update_content(
    draft_id: int,
    draft_name: Optional[str] = None,
    generated_content: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    slug: Optional[str] = None,
    excerpt: Optional[str] = None,
    cover_image_ref: Optional[str] = None,
    editor_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Rename and/or edit a draft's content (RC3.3 editor autosave; Blog's
    slug/excerpt/cover_image_ref joined the same autosave in Module 1
    Section 7A). Writes a revision iff generated_content, metadata, or any
    of the three Blog fields actually changed -- never on a rename-only save
    and never on a status-only transition (those go through the functions
    below, which don't call this).

    If generated_content itself changes (not just metadata/Blog fields) on a
    draft that was approved/published, that invalidates the prior sign-off:
    status drops to 'review' and approved_by/approved_at are cleared, the
    same place reject() would leave it. This never touches the production
    row a 'published' draft already created -- publishing is a one-time copy
    (see draft_publisher.publish); this only stops the *draft* from still
    claiming to be an approved match for content that has since moved on."""
    draft = get_draft(draft_id)
    if not draft:
        return None

    if draft["module"] == "blog" and generated_content is not None:
        _validate_blog_title(generated_content)

    fields: Dict[str, Any] = {}
    content_changed = False
    generated_content_changed = False
    if draft_name is not None:
        fields["draft_name"] = draft_name
    if generated_content is not None and generated_content != draft["generated_content"]:
        fields["generated_content"] = generated_content
        content_changed = True
        generated_content_changed = True
    if metadata is not None and metadata != draft["metadata"]:
        fields["metadata"] = metadata
        content_changed = True
    if slug is not None and slug != draft.get("slug"):
        # Blog-only (Module 1 Section 15): once a Blog draft has published at
        # least one time, its slug is the live post's URL -- changing it here
        # would silently 404 that URL with nothing to redirect it (no
        # redirect table exists, by design -- see Section 15 scope).
        # published_at is only ever set by mark_published() and never cleared
        # afterward (not even by the review-demote branch below), so
        # "published_at is set" reliably means "has published at least once",
        # independent of the draft's current status.
        if draft["module"] == "blog" and draft.get("published_at"):
            raise ValueError("slug cannot be changed after the post has been published")
        fields["slug"] = slug
        content_changed = True
    if excerpt is not None and excerpt != draft.get("excerpt"):
        fields["excerpt"] = excerpt
        content_changed = True
    if cover_image_ref is not None:
        # "" is the explicit clear sentinel (Module 1 Section 11 Step 15) --
        # router validation lets "" through where it'd otherwise reject an
        # empty ref, and it's normalized to NULL here so cover_image_ref
        # keeps its one meaning (a Sanity asset ref, or nothing).
        normalized_cover_image_ref = cover_image_ref or None
        if normalized_cover_image_ref != draft.get("cover_image_ref"):
            fields["cover_image_ref"] = normalized_cover_image_ref
            content_changed = True

    if not fields:
        return draft

    # Blog-only (Module 1 Section 12D Step 15): slug/excerpt/cover_image_ref
    # feed the published Sanity document exactly like generated_content does
    # (see blog_document_mapper.build_blog_sanity_document), so an edit to
    # any of them after approval/publish invalidates the prior sign-off the
    # same way an edit to generated_content already does -- otherwise a slug
    # change on a published post could sit on the draft with no re-approval
    # gate before the next Publish click pushes it to Sanity. Scoped to Blog
    # only: other modules pass these fields as None (never in `fields`), so
    # their demote condition is unchanged.
    blog_metadata_changed = draft["module"] == "blog" and any(
        key in fields for key in ("slug", "excerpt", "cover_image_ref")
    )
    if (generated_content_changed or blog_metadata_changed) and draft["status"] in _REVIEW_REQUIRED_ON_CONTENT_EDIT:
        fields["status"] = "review"
        fields["approved_by"] = None
        fields["approved_at"] = None

    supabase = get_supabase()
    if content_changed:
        # Backwards-compatible snapshot shape: old revisions with only
        # generated_content/metadata keys still read fine (readers just see
        # slug/excerpt/cover_image_ref absent, not wrong).
        supabase.table("generated_content_draft_revisions").insert({
            "draft_id": draft_id,
            "before": {
                "generated_content": draft["generated_content"], "metadata": draft["metadata"],
                "slug": draft.get("slug"), "excerpt": draft.get("excerpt"),
                "cover_image_ref": draft.get("cover_image_ref"),
            },
            "after": {
                "generated_content": fields.get("generated_content", draft["generated_content"]),
                "metadata": fields.get("metadata", draft["metadata"]),
                "slug": fields.get("slug", draft.get("slug")),
                "excerpt": fields.get("excerpt", draft.get("excerpt")),
                "cover_image_ref": fields.get("cover_image_ref", draft.get("cover_image_ref")),
            },
            "editor": editor_id or None,
        }).execute()

    fields["updated_at"] = _now_iso()
    rows = supabase.table("generated_content_drafts").update(fields).eq("id", draft_id).execute().data
    return rows[0] if rows else None


def list_revisions(draft_id: int) -> List[Dict[str, Any]]:
    supabase = get_supabase()
    return supabase.table("generated_content_draft_revisions").select(
        "id, before, after, editor, created_at"
    ).eq("draft_id", draft_id).order("created_at", desc=True).execute().data


def _set_status(draft_id: int, status: str, extra: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    supabase = get_supabase()
    fields = {"status": status, "updated_at": _now_iso()}
    if extra:
        fields.update(extra)
    rows = supabase.table("generated_content_drafts").update(fields).eq("id", draft_id).execute().data
    return rows[0] if rows else None


def submit_for_review(draft_id: int) -> Optional[Dict[str, Any]]:
    draft = get_draft(draft_id)
    if not draft:
        return None
    if "review" not in _TRANSITIONS.get(draft["status"], set()):
        raise InvalidTransitionError(f"Cannot submit for review from status '{draft['status']}'")
    if draft["module"] == "blog":
        _validate_blog_completeness(draft)
    return _set_status(draft_id, "review")


def approve(draft_id: int, admin_id: str) -> Optional[Dict[str, Any]]:
    draft = get_draft(draft_id)
    if not draft:
        return None
    if "approved" not in _TRANSITIONS.get(draft["status"], set()):
        raise InvalidTransitionError(f"Cannot approve from status '{draft['status']}'")
    if draft["module"] == "blog":
        _validate_blog_completeness(draft)
    now = _now_iso()
    return _set_status(draft_id, "approved", {
        "reviewed_by": admin_id, "reviewed_at": now,
        "approved_by": admin_id, "approved_at": now,
    })


def reject(draft_id: int, admin_id: str) -> Optional[Dict[str, Any]]:
    """Sends a draft back one stage: review->draft, or approved->review."""
    draft = get_draft(draft_id)
    if not draft:
        return None
    target = {"review": "draft", "approved": "review"}.get(draft["status"])
    if not target:
        raise InvalidTransitionError(f"Cannot reject from status '{draft['status']}'")
    return _set_status(draft_id, target, {"reviewed_by": admin_id, "reviewed_at": _now_iso()})


def archive(draft_id: int) -> Optional[Dict[str, Any]]:
    draft = get_draft(draft_id)
    if not draft:
        return None
    if draft["status"] not in _ARCHIVABLE_FROM:
        raise InvalidTransitionError(f"Cannot archive from status '{draft['status']}'")
    return _set_status(draft_id, "archived")


def mark_published(draft_id: int, owner_id: str) -> Optional[Dict[str, Any]]:
    """Compare-and-set on status (Module 1 Section 12E Step 5/7): the old
    get_draft()-then-update() here had a TOCTOU gap where two concurrent
    Publish requests for the same draft could both read status 'approved'
    before either wrote, so both would update -- silently, with no
    InvalidTransitionError for either caller. Filtering the update itself on
    .eq("status", "approved") makes Postgres's own row-update atomicity do
    the exclusion: exactly one concurrent call's UPDATE can match and write,
    the other affects zero rows and falls through to the same
    InvalidTransitionError every other caller of this function already
    expects (see admin_content_studio._publish_blog_draft's concurrent-publish
    handling, which relies on that exception, not on which request "wins")."""
    supabase = get_supabase()
    now = _now_iso()
    rows = supabase.table("generated_content_drafts").update({
        "status": "published", "published_by": owner_id, "published_at": now, "updated_at": now,
    }).eq("id", draft_id).eq("status", "approved").execute().data
    if rows:
        return rows[0]
    draft = get_draft(draft_id)
    if not draft:
        return None
    raise InvalidTransitionError(f"Cannot publish from status '{draft['status']}'")


def delete_draft(draft_id: int) -> bool:
    supabase = get_supabase()
    existing = supabase.table("generated_content_drafts").select("id").eq("id", draft_id).execute().data
    if not existing:
        return False
    supabase.table("generated_content_drafts").delete().eq("id", draft_id).execute()
    return True
