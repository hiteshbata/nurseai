"""CRUD over generated_content_drafts (RC3.2) -- the only table AI Draft
Generator is allowed to write to. Deliberately separate from
content_studio.py, which only ever reads production content tables: keeping
the two services apart keeps "drafts never touch production" true at the
code-boundary, not just by convention.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.supabase import get_supabase

COLUMNS = (
    "id, module, draft_name, ai_title, metadata, prompt, generated_content, "
    "validation_warnings, status, model_used, ai_generated, created_by, "
    "created_at, updated_at"
)
# Same shape minus the (often large) generated_content/prompt blobs -- list
# views don't need the full payload.
LIST_COLUMNS = (
    "id, module, draft_name, ai_title, status, model_used, validation_warnings, "
    "created_by, created_at, updated_at"
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


def rename_draft(draft_id: int, draft_name: str) -> Optional[Dict[str, Any]]:
    supabase = get_supabase()
    rows = supabase.table("generated_content_drafts").update({
        "draft_name": draft_name,
        "updated_at": _now_iso(),
    }).eq("id", draft_id).execute().data
    return rows[0] if rows else None


def delete_draft(draft_id: int) -> bool:
    supabase = get_supabase()
    existing = supabase.table("generated_content_drafts").select("id").eq("id", draft_id).execute().data
    if not existing:
        return False
    supabase.table("generated_content_drafts").delete().eq("id", draft_id).execute()
    return True
