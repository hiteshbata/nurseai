"""E2.4.4: one-off backfill from user_skill_stats into user_skill_bridge.

Source: public.user_skill_stats (skill_graph.py's EMA table) -- read-only,
never mutated here or anywhere in this module. Every distinct (user_id,
skill_tag) pair is resolved through skill_bridge_resolver.resolve_skill_id()
and classified:

  - known:     resolves to a skill_id                       -> upsert into
                                                                 user_skill_bridge
  - unknown:   tag isn't in LEGACY_TAG_TO_CODE at all         -> report only,
                                                                 no insert
  - ambiguous: tag IS in LEGACY_TAG_TO_CODE but its code has
               no matching row in the live skills table
               (registry/data drift)                          -> report only,
                                                                 no insert
  - duplicate: same (user_id, skill_tag) seen twice           -> ignored
               safely -- the source query dedupes in Python,
               and the table's own UNIQUE(user_id, skill_tag)
               plus upsert(on_conflict=...) dedupes again at
               the DB layer.

Not wired into any router or startup path -- run manually, and only after
reviewing the counts run_backfill()/classify_pairs() report.
"""
from typing import Dict, List, Tuple, TypedDict

from app.core.threading import run_sync
from app.services.skill_bridge_resolver import LEGACY_TAG_TO_CODE, resolve_skill_id

Pair = Tuple[str, str]  # (user_id, skill_tag)


class BackfillReport(TypedDict):
    known: List[Pair]
    unknown: List[Pair]
    ambiguous: List[Pair]
    inserted_count: int


def classify_pairs(pairs: List[Pair]) -> Dict[str, List[Pair]]:
    """Pure: classify (user_id, skill_tag) pairs by resolver outcome. Doesn't
    touch user_skill_bridge itself -- only resolve_skill_id()'s own
    in-process skills cache does any I/O, and only reads."""
    known: List[Pair] = []
    unknown: List[Pair] = []
    ambiguous: List[Pair] = []
    for user_id, tag in pairs:
        if resolve_skill_id(tag) is not None:
            known.append((user_id, tag))
        elif tag in LEGACY_TAG_TO_CODE:
            ambiguous.append((user_id, tag))
        else:
            unknown.append((user_id, tag))
    return {"known": known, "unknown": unknown, "ambiguous": ambiguous}


def _distinct_pairs_sync(supabase) -> List[Pair]:
    rows = supabase.table("user_skill_stats").select("user_id, skill_tag").execute().data or []
    return sorted({(r["user_id"], r["skill_tag"]) for r in rows})


def _backfill_sync(supabase) -> BackfillReport:
    pairs = _distinct_pairs_sync(supabase)
    classified = classify_pairs(pairs)

    inserted = 0
    for user_id, tag in classified["known"]:
        skill_id = resolve_skill_id(tag)  # already known non-None from classify_pairs
        row = {"user_id": user_id, "skill_tag": tag, "skill_id": str(skill_id)}
        supabase.table("user_skill_bridge").upsert(row, on_conflict="user_id,skill_tag").execute()
        inserted += 1

    return {
        "known": classified["known"],
        "unknown": classified["unknown"],
        "ambiguous": classified["ambiguous"],
        "inserted_count": inserted,
    }


async def run_backfill(supabase) -> BackfillReport:
    """`supabase` is get_supabase()'s return value (or a fake with the same
    .table().select()/.upsert().execute() shape, for tests). QA only -- never
    call this against production."""
    return await run_sync(_backfill_sync, supabase)


if __name__ == "__main__":
    # ponytail: one runnable check -- classification buckets are exhaustive and disjoint.
    from app.services.skill_bridge_resolver import _reset_cache_for_tests

    _reset_cache_for_tests({"reading.part.a": "11111111-1111-1111-1111-111111111111"})
    result = classify_pairs([
        ("u1", "reading:A"),         # known -- code is in the seeded cache
        ("u1", "listening:A"),       # ambiguous -- in LEGACY_TAG_TO_CODE, code missing from cache
        ("u2", "made:up:tag"),       # unknown -- not in LEGACY_TAG_TO_CODE at all
    ])
    assert result["known"] == [("u1", "reading:A")]
    assert result["ambiguous"] == [("u1", "listening:A")]
    assert result["unknown"] == [("u2", "made:up:tag")]
    _reset_cache_for_tests(None)
    print("OK")
