"""E2.4.4: read-only demonstration of the full chain --

    skill_tag -> skill_id (via user_skill_bridge) -> content_skill_map rows

Not wired into any API endpoint. Content Factory / Content Studio wiring for
this is explicitly out of scope for E2.4.4 -- see the phase's own plan doc.
"""
from typing import Dict, List

from app.core.threading import run_sync


def _get_content_for_skill_sync(supabase, user_id: str, skill_tag: str) -> List[Dict]:
    bridge_rows = (
        supabase.table("user_skill_bridge").select("skill_id")
        .eq("user_id", user_id).eq("skill_tag", skill_tag).execute().data or []
    )
    if not bridge_rows:
        return []
    skill_id = bridge_rows[0]["skill_id"]

    content_rows = supabase.table("content_skill_map").select("*").eq("skill_id", skill_id).execute()
    return content_rows.data or []


async def get_content_for_skill(supabase, user_id: str, skill_tag: str) -> List[Dict]:
    """`supabase` is get_supabase()'s return value (or a fake with the same
    .table(...).select(...).eq(...).execute() shape, for tests). Read-only:
    only ever SELECTs, on user_skill_bridge and content_skill_map -- never
    writes, never touches user_skill_stats/skill_observations directly."""
    return await run_sync(_get_content_for_skill_sync, supabase, user_id, skill_tag)
