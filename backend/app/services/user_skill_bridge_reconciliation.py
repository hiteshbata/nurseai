"""E2.4.4: read-only reconciliation between user_skill_stats (source of
truth), the skills registry, and public.user_skill_bridge (the derived
bridge). Never mutates data -- this is a report, not wired into any router
or startup path. `reconcile()` is pure (no I/O) so it's unit-testable
without a live Supabase project; `run_live_reconciliation()` does the actual
querying, same split as skill_registry_reconciliation.py /
content_skill_map_reconciliation.py.

"orphan bridge user_ids" is checked against public.users (the auth.users
mirror -- see 20260718000800_users_mirror.sql and
assessment_versioning.py's identical use of it), since a service-role
Supabase client has no ordinary table access to the auth schema. The mirror
is lazily/best-effort synced, so a user who has never made an authenticated
request since it was introduced can show up as a false-positive orphan --
this report is advisory, not authoritative, for that one field.
"""
from typing import Dict, Iterable, List, Tuple, TypedDict

from app.services.skill_bridge_resolver import LEGACY_TAG_TO_CODE, resolve_skill_id

Pair = Tuple[str, str]  # (user_id, skill_tag)


class BridgeReconciliationReport(TypedDict):
    source_pairs: List[Pair]
    resolved_bridge_pairs: List[Pair]
    missing_bridge_pairs: List[Pair]
    orphan_bridge_user_ids: List[str]
    orphan_bridge_skill_ids: List[str]
    unknown_legacy_tags: List[str]
    duplicate_bridge_rows: List[Pair]
    mismatched_tag_skill_resolution: List[Tuple[str, str, str, str]]  # (user_id, tag, stored_skill_id, resolved_skill_id_or_"")


def reconcile(
    source_pairs: Iterable[Pair],
    bridge_rows: Iterable[Dict],
    existing_user_ids: Iterable[str],
    existing_skill_ids: Iterable[str],
) -> BridgeReconciliationReport:
    """`bridge_rows`: dicts with user_id, skill_tag, skill_id (as stored in
    user_skill_bridge). `existing_user_ids`/`existing_skill_ids`: live ids
    from public.users and public.skills respectively."""
    source_pairs = sorted(set(source_pairs))
    bridge_rows = list(bridge_rows)
    user_ids = set(existing_user_ids)
    skill_ids = set(existing_skill_ids)

    resolved_bridge_pairs = [(r["user_id"], r["skill_tag"]) for r in bridge_rows]
    bridge_pair_set = set(resolved_bridge_pairs)

    missing_bridge_pairs = [
        (user_id, tag) for user_id, tag in source_pairs
        if (user_id, tag) not in bridge_pair_set and resolve_skill_id(tag) is not None
    ]

    orphan_bridge_user_ids = sorted({r["user_id"] for r in bridge_rows if r["user_id"] not in user_ids})
    orphan_bridge_skill_ids = sorted({r["skill_id"] for r in bridge_rows if r["skill_id"] not in skill_ids})

    unknown_legacy_tags = sorted({tag for _, tag in source_pairs if tag not in LEGACY_TAG_TO_CODE})

    seen: set = set()
    duplicate_bridge_rows: List[Pair] = []
    for pair in resolved_bridge_pairs:
        if pair in seen:
            duplicate_bridge_rows.append(pair)
        seen.add(pair)

    mismatched_tag_skill_resolution = []
    for r in bridge_rows:
        resolved = resolve_skill_id(r["skill_tag"])
        resolved_str = str(resolved) if resolved is not None else ""
        if resolved_str != r["skill_id"]:
            mismatched_tag_skill_resolution.append((r["user_id"], r["skill_tag"], r["skill_id"], resolved_str))

    return {
        "source_pairs": source_pairs,
        "resolved_bridge_pairs": resolved_bridge_pairs,
        "missing_bridge_pairs": missing_bridge_pairs,
        "orphan_bridge_user_ids": orphan_bridge_user_ids,
        "orphan_bridge_skill_ids": orphan_bridge_skill_ids,
        "unknown_legacy_tags": unknown_legacy_tags,
        "duplicate_bridge_rows": duplicate_bridge_rows,
        "mismatched_tag_skill_resolution": mismatched_tag_skill_resolution,
    }


def run_live_reconciliation(supabase) -> BridgeReconciliationReport:
    """`supabase` is get_supabase()'s return value (or a fake with the same
    .table(...).select(...).execute() shape, for tests). Read-only: only
    ever SELECTs."""
    stats_rows = supabase.table("user_skill_stats").select("user_id, skill_tag").execute().data or []
    source_pairs = {(r["user_id"], r["skill_tag"]) for r in stats_rows}

    bridge_rows = supabase.table("user_skill_bridge").select("user_id, skill_tag, skill_id").execute().data or []
    user_rows = supabase.table("users").select("id").execute().data or []
    skill_rows = supabase.table("skills").select("skill_id").execute().data or []

    return reconcile(
        source_pairs,
        bridge_rows,
        existing_user_ids=[r["id"] for r in user_rows],
        existing_skill_ids=[r["skill_id"] for r in skill_rows],
    )


if __name__ == "__main__":
    # ponytail: one runnable check -- each report bucket catches its own scenario.
    from app.services.skill_bridge_resolver import _reset_cache_for_tests

    _reset_cache_for_tests({"reading.part.a": "11111111-1111-1111-1111-111111111111"})
    report = reconcile(
        source_pairs=[("u1", "reading:A"), ("u1", "made:up"), ("u2", "reading:A")],
        bridge_rows=[
            {"user_id": "u1", "skill_tag": "reading:A", "skill_id": "11111111-1111-1111-1111-111111111111"},
            {"user_id": "gone", "skill_tag": "reading:A", "skill_id": "11111111-1111-1111-1111-111111111111"},
            {"user_id": "u1", "skill_tag": "reading:A", "skill_id": "99999999-9999-9999-9999-999999999999"},
        ],
        existing_user_ids=["u1", "u2"],
        existing_skill_ids=["11111111-1111-1111-1111-111111111111"],
    )
    assert ("u2", "reading:A") in report["missing_bridge_pairs"]
    assert "gone" in report["orphan_bridge_user_ids"]
    assert "99999999-9999-9999-9999-999999999999" in report["orphan_bridge_skill_ids"]
    assert "made:up" in report["unknown_legacy_tags"]
    assert ("u1", "reading:A") in report["duplicate_bridge_rows"]
    _reset_cache_for_tests(None)
    print("OK")
