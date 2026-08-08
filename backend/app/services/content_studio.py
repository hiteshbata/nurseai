"""Read-only aggregation across the content modules for the AI Content
Studio (RC3.1 -- foundation only, no generation, no writes, no migrations).

Normalizes existing `scenarios` (speaking/writing), `reading_tests`, and
`listening_tests` rows into one shape. Grammar and Vocabulary have no
admin-ready content store (see docs/CONTENT_FOUNDATION.md S:1/S:2 --
`vocab_cards` is a per-user SRS deck, not admin content; Grammar has no
table at all) so neither is queried here -- "Coming Soon" is a static
frontend fact, not a fabricated empty dataset.

Reading/listening are grouped: a test (`reading_tests`/`listening_tests`)
holds several passages/sections. The TEST's `is_active` is what gates
student visibility (see reading.py's `list_reading_tests` /
`_load_test_payload`, listening.py equivalent) -- a passage/section's own
`is_active` only toggles whether it's included in its (already-live) test,
it is not a second publish state. So this module reads the test tables,
not the child tables, to match what "Published" means everywhere else in
the app. Standalone passages/sections (`test_id is null`) have no parent
to defer to and aren't test rows, so they're intentionally not
represented here -- they're a legacy/authoring path, not the primary
publishable unit.

Status is a two-value proxy off the existing `is_active` boolean
(Published/Unpublished). Draft/Review/Archived need a real `status` column
-- out of scope for RC3.1, planned for RC3.3.

Content ID is derived, not stored: f"{PREFIX}-{row_id:06d}" is a pure
function of module + primary key, so it's stable across requests without a
migration.
"""
from typing import Any, Dict, List, Optional

from app.core.supabase import get_supabase

ACTIVE_MODULES = ["speaking", "writing", "reading", "listening"]

_PREFIX = {"speaking": "SPK", "writing": "WRT", "reading": "RDG", "listening": "LST"}
_TABLE = {"speaking": "scenarios", "writing": "scenarios", "reading": "reading_tests", "listening": "listening_tests"}
_HAS_DIFFICULTY_AND_UPDATED_AT = ("speaking", "writing")  # reading_tests/listening_tests have neither column


def _content_id(module: str, row_id: int) -> str:
    return f"{_PREFIX[module]}-{row_id:06d}"


def _normalize(module: str, row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "content_id": _content_id(module, row["id"]),
        "id": row["id"],
        "module": module,
        "title": row["title"],
        "status": "Published" if row["is_active"] else "Unpublished",
        "is_active": row["is_active"],
        "difficulty": row.get("difficulty"),
        "created_at": row["created_at"],
        "updated_at": row.get("updated_at") or row["created_at"],
    }


def _fetch(supabase, module: str) -> List[Dict[str, Any]]:
    columns = "id, title, is_active, created_at"
    if module in _HAS_DIFFICULTY_AND_UPDATED_AT:
        columns += ", difficulty, updated_at"
    query = supabase.table(_TABLE[module]).select(columns)
    if module in ("speaking", "writing"):
        query = query.eq("module", module)
    rows = query.order("created_at", desc=True).execute().data
    return [_normalize(module, r) for r in rows]


def get_summary() -> Dict[str, Any]:
    modules: Dict[str, Any] = {}
    supabase = get_supabase()
    for module in ACTIVE_MODULES:
        items = _fetch(supabase, module)
        published = sum(1 for i in items if i["is_active"])
        modules[module] = {"total": len(items), "published": published, "unpublished": len(items) - published}
    return {
        "total": sum(m["total"] for m in modules.values()),
        "published": sum(m["published"] for m in modules.values()),
        "unpublished": sum(m["unpublished"] for m in modules.values()),
        "modules": modules,
    }


def list_items(
    module: Optional[str] = None,
    status: Optional[str] = None,
    difficulty: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    supabase = get_supabase()
    modules_to_query = [module] if module in ACTIVE_MODULES else ACTIVE_MODULES

    items: List[Dict[str, Any]] = []
    for m in modules_to_query:
        items.extend(_fetch(supabase, m))

    if status:
        items = [i for i in items if i["status"] == status]
    if difficulty:
        items = [i for i in items if i["difficulty"] == difficulty]
    if search:
        needle = search.lower().strip()
        items = [i for i in items if needle in i["title"].lower() or needle in i["content_id"].lower()]

    items.sort(key=lambda i: i["created_at"], reverse=True)
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total}


def get_item(module: str, item_id: int) -> Optional[Dict[str, Any]]:
    if module not in ACTIVE_MODULES:
        return None
    supabase = get_supabase()
    query = supabase.table(_TABLE[module]).select("*").eq("id", item_id)
    if module in ("speaking", "writing"):
        query = query.eq("module", module)
    rows = query.execute().data
    if not rows:
        return None
    item = _normalize(module, rows[0])
    item["specialty"] = rows[0].get("specialty")
    return item
