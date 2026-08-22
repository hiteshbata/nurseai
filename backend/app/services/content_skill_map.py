"""E2.4.2: content -> skill mapping (public.content_skill_map).

Data-layer helpers for the generic content_skill_map table. The three
"safe" mappings (listening_sections.part, techniques.skill_tag,
micro_practices inheriting their technique) are backfilled directly in
20260822000000_content_skill_map.sql -- this module is for everything that
needs to happen from application code:

  - add_mapping(): the manual/reviewed-mapping path, e.g. for tagging
    individual listening_question rows once someone has actually reviewed
    them (source='manual'). No skill can be safely inferred from
    question.type, so there is no auto-tagging path for questions.
  - list_mappings_for(): read the mappings for one piece of content.

Nothing here is wired into any router yet -- Content Studio UI for this is
explicitly out of scope for E2.4.2.
"""
from typing import Dict, List, Optional

from app.core.threading import run_sync

ALLOWED_CONTENT_TYPES = {"listening_section", "listening_question", "technique", "micro_practice"}
ALLOWED_RELATIONSHIP_TYPES = {"teaches", "practices"}
ALLOWED_SOURCES = {"manual", "heuristic:part"}


def _validate(content_type: str, relationship_type: str, source: str) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"unsupported content_type: {content_type!r}")
    if relationship_type not in ALLOWED_RELATIONSHIP_TYPES:
        raise ValueError(f"unsupported relationship_type: {relationship_type!r}")
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"unsupported source: {source!r}")


def _add_mapping_sync(
    supabase,
    skill_id: str,
    content_type: str,
    content_id: int,
    relationship_type: str,
    source: str,
    created_by: Optional[str],
) -> Dict:
    _validate(content_type, relationship_type, source)
    row = {
        "skill_id": skill_id,
        "content_type": content_type,
        "content_id": content_id,
        "relationship_type": relationship_type,
        "source": source,
        "created_by": created_by,
    }
    result = (
        supabase.table("content_skill_map")
        .upsert(row, on_conflict="skill_id,content_type,content_id,relationship_type")
        .execute()
    )
    return (result.data or [row])[0]


async def add_mapping(
    supabase,
    skill_id: str,
    content_type: str,
    content_id: int,
    relationship_type: str,
    source: str = "manual",
    created_by: Optional[str] = None,
) -> Dict:
    """Reviewed/manual mapping entry point. `supabase` is get_supabase()'s
    return value (or a fake with the same .table().upsert().execute() shape,
    for tests)."""
    return await run_sync(
        _add_mapping_sync, supabase, skill_id, content_type, content_id, relationship_type, source, created_by
    )


def _list_mappings_sync(supabase, content_type: str, content_id: int) -> List[Dict]:
    result = (
        supabase.table("content_skill_map")
        .select("*")
        .eq("content_type", content_type)
        .eq("content_id", content_id)
        .execute()
    )
    return result.data or []


async def list_mappings_for(supabase, content_type: str, content_id: int) -> List[Dict]:
    return await run_sync(_list_mappings_sync, supabase, content_type, content_id)


if __name__ == "__main__":
    # ponytail: one runnable check -- validation rejects what the DB would reject.
    try:
        _validate("listening_question", "teaches", "manual")
    except ValueError:
        raise AssertionError("expected valid combination to pass")
    for bad in [("reading_question", "teaches", "manual"), ("technique", "bad", "manual"), ("technique", "teaches", "bad")]:
        try:
            _validate(*bad)
            raise AssertionError(f"expected {bad} to raise")
        except ValueError:
            pass
    print("OK")
