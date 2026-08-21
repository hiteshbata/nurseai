"""E2.4.1: read-only reconciliation between the legacy colon-tag strings
still written by skill_graph.py / technique_progress.py and the canonical
`skills` registry (skill_registry.SEED_SKILLS).

This never mutates data -- it's a report, run manually or from a test, not
wired into any router or startup path. `reconcile()` is pure (no I/O) so it
can be unit-tested without a live Supabase project; `run_live_reconciliation`
does the actual querying when someone wants a real report."""
from typing import Dict, Iterable, List, TypedDict

from app.services.skill_registry import LEGACY_TAG_TO_CODE, SEED_SKILLS


class ReconciliationReport(TypedDict):
    known: List[str]            # observed legacy tags that map to a registered code
    missing: List[str]          # observed legacy tags with no matching registry entry
    unused: List[str]           # registry codes never observed in any source table


def reconcile(observed_tags: Iterable[str]) -> ReconciliationReport:
    """`observed_tags`: distinct skill_tag values pulled from user_skill_stats,
    skill_observations, listening_mistake_events, and techniques (the last one
    needs technique_progress.technique_skill_tag() applied first, since that
    table stores the bare tag, not the "technique:" prefixed one)."""
    observed = set(observed_tags)
    registry_codes = {s["code"] for s in SEED_SKILLS}

    known, missing = [], []
    for tag in sorted(observed):
        if LEGACY_TAG_TO_CODE.get(tag) in registry_codes:
            known.append(tag)
        else:
            missing.append(tag)

    mapped_codes = {LEGACY_TAG_TO_CODE[t] for t in observed if t in LEGACY_TAG_TO_CODE}
    unused = sorted(registry_codes - mapped_codes)

    return {"known": known, "missing": missing, "unused": unused}


def _distinct(rows: List[Dict], column: str = "skill_tag") -> List[str]:
    return sorted({r[column] for r in rows if r.get(column)})


def run_live_reconciliation(supabase) -> ReconciliationReport:
    """Queries the 4 source tables named in E2.4.1 for their distinct
    skill_tag values and reconciles them against the registry. Read-only:
    only ever SELECTs. `supabase` is whatever get_supabase() returns (or a
    fake with the same .table(...).select(...).execute() shape, for tests)."""
    observed: List[str] = []

    for table in ("user_skill_stats", "skill_observations", "listening_mistake_events"):
        rows = supabase.table(table).select("skill_tag").execute().data or []
        observed.extend(_distinct(rows))

    technique_rows = supabase.table("techniques").select("skill_tag").execute().data or []
    observed.extend(f"technique:{tag}" for tag in _distinct(technique_rows))

    return reconcile(observed)


if __name__ == "__main__":
    # ponytail: one runnable check -- reconcile() catches both directions.
    report = reconcile(["reading:A", "reading:not_a_real_tag"])
    assert report["known"] == ["reading:A"]
    assert report["missing"] == ["reading:not_a_real_tag"]
    assert len(report["unused"]) == len(SEED_SKILLS) - 1
    print("OK")
