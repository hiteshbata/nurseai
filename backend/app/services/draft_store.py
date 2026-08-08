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

COLUMNS = (
    "id, module, draft_name, ai_title, metadata, prompt, generated_content, "
    "validation_warnings, status, model_used, ai_generated, created_by, "
    "created_at, updated_at, reviewed_by, reviewed_at, approved_by, approved_at, "
    "published_by, published_at"
)
# Same shape minus the (often large) generated_content/prompt blobs -- list
# views don't need the full payload.
LIST_COLUMNS = (
    "id, module, draft_name, ai_title, status, model_used, validation_warnings, "
    "created_by, created_at, updated_at, approved_at, published_at"
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
) -> Dict[str, Any]:
    supabase = get_supabase()
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
    }).execute()
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
    editor_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Rename and/or edit a draft's content (RC3.3 editor autosave).
    Writes a revision iff generated_content or metadata actually changed --
    never on a rename-only save and never on a status-only transition (those
    go through the functions below, which don't call this).

    If generated_content itself changes (not just metadata) on a draft that
    was approved/published, that invalidates the prior sign-off: status
    drops to 'review' and approved_by/approved_at are cleared, the same
    place reject() would leave it. A metadata-only edit doesn't touch what
    would be published, so it doesn't force re-review. This never touches
    the production row a 'published' draft already created -- publishing is
    a one-time copy (see draft_publisher.publish); this only stops the
    *draft* from still claiming to be an approved match for content that
    has since moved on."""
    draft = get_draft(draft_id)
    if not draft:
        return None

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

    if not fields:
        return draft

    if generated_content_changed and draft["status"] in _REVIEW_REQUIRED_ON_CONTENT_EDIT:
        fields["status"] = "review"
        fields["approved_by"] = None
        fields["approved_at"] = None

    supabase = get_supabase()
    if content_changed:
        supabase.table("generated_content_draft_revisions").insert({
            "draft_id": draft_id,
            "before": {"generated_content": draft["generated_content"], "metadata": draft["metadata"]},
            "after": {
                "generated_content": fields.get("generated_content", draft["generated_content"]),
                "metadata": fields.get("metadata", draft["metadata"]),
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
    return _set_status(draft_id, "review")


def approve(draft_id: int, admin_id: str) -> Optional[Dict[str, Any]]:
    draft = get_draft(draft_id)
    if not draft:
        return None
    if "approved" not in _TRANSITIONS.get(draft["status"], set()):
        raise InvalidTransitionError(f"Cannot approve from status '{draft['status']}'")
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
    draft = get_draft(draft_id)
    if not draft:
        return None
    if draft["status"] != "approved":
        raise InvalidTransitionError(f"Cannot publish from status '{draft['status']}'")
    return _set_status(draft_id, "published", {"published_by": owner_id, "published_at": _now_iso()})


def delete_draft(draft_id: int) -> bool:
    supabase = get_supabase()
    existing = supabase.table("generated_content_drafts").select("id").eq("id", draft_id).execute().data
    if not existing:
        return False
    supabase.table("generated_content_drafts").delete().eq("id", draft_id).execute()
    return True
