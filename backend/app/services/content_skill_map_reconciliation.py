"""E2.4.2: read-only orphan reconciliation for public.content_skill_map.

content_skill_map.content_type/content_id is a polymorphic reference with
no DB-level FK (content lives across several tables), so a mapping can go
stale two ways: its skill_id row gets deleted (blocked by ON DELETE
RESTRICT today, but checked anyway for defense-in-depth / future schema
changes), or its content row gets deleted (listening_sections/techniques/
micro_practices/questions all CASCADE or otherwise remove rows).

`find_orphans()` is pure (no I/O) so it's unit-testable without a live
Supabase project; `run_live_reconciliation()` does the actual querying.
Never mutates data -- this is a report, not wired into any router or
startup path."""
from typing import Dict, Iterable, List, Set, TypedDict

CONTENT_TABLES = {
    "listening_section": "listening_sections",
    "listening_question": "questions",
    "technique": "techniques",
    "micro_practice": "micro_practices",
}


class OrphanReport(TypedDict):
    orphaned_skill: List[Dict]      # mappings whose skill_id no longer exists
    orphaned_content: List[Dict]    # mappings whose content_type/content_id no longer exists
    clean_count: int                # mappings that resolved fine


def find_orphans(
    mappings: Iterable[Dict],
    existing_skill_ids: Iterable[str],
    existing_content_ids: Dict[str, Set[int]],
) -> OrphanReport:
    """`mappings`: rows from content_skill_map (dicts with skill_id,
    content_type, content_id). `existing_content_ids`: {content_type: set of
    live ids in that content's table}."""
    skill_ids = set(existing_skill_ids)
    orphaned_skill, orphaned_content = [], []
    clean = 0

    for row in mappings:
        if row["skill_id"] not in skill_ids:
            orphaned_skill.append(row)
            continue
        live_ids = existing_content_ids.get(row["content_type"], set())
        if row["content_id"] not in live_ids:
            orphaned_content.append(row)
            continue
        clean += 1

    return {"orphaned_skill": orphaned_skill, "orphaned_content": orphaned_content, "clean_count": clean}


def run_live_reconciliation(supabase) -> OrphanReport:
    """`supabase` is whatever get_supabase() returns (or a fake with the
    same .table(...).select(...).execute() shape, for tests)."""
    mappings = supabase.table("content_skill_map").select("skill_id, content_type, content_id").execute().data or []
    skill_rows = supabase.table("skills").select("skill_id").execute().data or []
    existing_skill_ids = {r["skill_id"] for r in skill_rows}

    existing_content_ids: Dict[str, Set[int]] = {}
    for content_type in {m["content_type"] for m in mappings}:
        table = CONTENT_TABLES.get(content_type)
        if table is None:
            existing_content_ids[content_type] = set()
            continue
        rows = supabase.table(table).select("id").execute().data or []
        existing_content_ids[content_type] = {r["id"] for r in rows}

    return find_orphans(mappings, existing_skill_ids, existing_content_ids)


if __name__ == "__main__":
    # ponytail: one runnable check -- both orphan directions caught, clean rows counted.
    report = find_orphans(
        mappings=[
            {"skill_id": "s1", "content_type": "technique", "content_id": 1},
            {"skill_id": "gone", "content_type": "technique", "content_id": 1},
            {"skill_id": "s1", "content_type": "technique", "content_id": 999},
        ],
        existing_skill_ids=["s1"],
        existing_content_ids={"technique": {1}},
    )
    assert len(report["orphaned_skill"]) == 1
    assert len(report["orphaned_content"]) == 1
    assert report["clean_count"] == 1
    print("OK")
