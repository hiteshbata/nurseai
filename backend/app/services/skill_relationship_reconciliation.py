"""E2.4.3: read-only reconciliation + cycle validation for
public.skill_relationships.

Same shape as skill_registry_reconciliation.py / content_skill_map_reconciliation.py:
pure functions first (no I/O, unit-testable without a live Supabase project),
a thin run_live_reconciliation() wrapper that only ever SELECTs. Never
mutates data -- this is a report, not wired into any router, startup path,
or DB trigger.

Two separate concerns live here:
  - find_relationship_issues() / find_parent_cycles() -- reconciliation of
    what's actually in the DB right now (orphans, bad types, dupes,
    self-loops, cycles already present).
  - would_create_cycle() -- the pure validator E2.4.3 asks for "for future
    writes": given the edges that already exist, would adding one more edge
    close a cycle? No prerequisite_of rows exist yet and no DB trigger is
    added -- this is here so a future write path (still out of scope) has
    something correct to call before it inserts.
"""
from typing import Dict, Iterable, List, Optional, Set, Tuple, TypedDict

VALID_RELATIONSHIP_TYPES = {"assesses", "trains_toward", "rolls_up_into", "prerequisite_of"}
VALID_SOURCES = {"manual", "heuristic:code_evidence"}


class ReconciliationReport(TypedDict):
    orphaned_source: List[Dict]      # source_skill_id has no matching skills row
    orphaned_target: List[Dict]      # target_skill_id has no matching skills row
    invalid_type: List[Dict]         # relationship_type outside VALID_RELATIONSHIP_TYPES
    self_loops: List[Dict]           # source_skill_id == target_skill_id
    duplicates: List[Dict]           # repeat (source, target, relationship_type)
    prerequisite_cycles: List[List[str]]
    clean_count: int


def find_relationship_issues(relationships: Iterable[Dict], existing_skill_ids: Iterable[str]) -> ReconciliationReport:
    """`relationships`: rows from skill_relationships (dicts with
    source_skill_id, target_skill_id, relationship_type). A row can land in
    more than one bucket (e.g. an invalid type on an orphaned source) --
    each check is independent, `clean_count` only counts rows that trip
    none of them."""
    skill_ids = set(existing_skill_ids)
    orphaned_source, orphaned_target, invalid_type, self_loops, duplicates = [], [], [], [], []
    seen: Set[Tuple[str, str, str]] = set()
    clean = 0

    for row in relationships:
        src, tgt, rtype = row["source_skill_id"], row["target_skill_id"], row["relationship_type"]
        problems = 0

        if src not in skill_ids:
            orphaned_source.append(row)
            problems += 1
        if tgt not in skill_ids:
            orphaned_target.append(row)
            problems += 1
        if rtype not in VALID_RELATIONSHIP_TYPES:
            invalid_type.append(row)
            problems += 1
        if src == tgt:
            self_loops.append(row)
            problems += 1

        key = (src, tgt, rtype)
        if key in seen:
            duplicates.append(row)
            problems += 1
        else:
            seen.add(key)

        if problems == 0:
            clean += 1

    prereq_edges = [(r["source_skill_id"], r["target_skill_id"]) for r in relationships if r["relationship_type"] == "prerequisite_of"]

    return {
        "orphaned_source": orphaned_source,
        "orphaned_target": orphaned_target,
        "invalid_type": invalid_type,
        "self_loops": self_loops,
        "duplicates": duplicates,
        "prerequisite_cycles": find_cycles(prereq_edges),
        "clean_count": clean,
    }


def find_parent_cycles(skill_rows: Iterable[Dict]) -> List[List[str]]:
    """`skill_rows`: rows from public.skills (dicts with skill_id,
    parent_skill_id). Not yet populated for any row (E2.4.1 left it NULL,
    E2.4.3 doesn't touch it either) -- this exists so reconciliation covers
    it the moment something does."""
    edges = [(r["skill_id"], r["parent_skill_id"]) for r in skill_rows if r.get("parent_skill_id")]
    return find_cycles(edges)


def find_cycles(edges: Iterable[Tuple[str, str]]) -> List[List[str]]:
    """Pure DFS cycle detection over a directed edge list. Returns each
    distinct cycle found, as the node sequence that closes it."""
    graph: Dict[str, List[str]] = {}
    for src, tgt in edges:
        graph.setdefault(src, []).append(tgt)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {}
    cycles: List[List[str]] = []

    def visit(node: str, path: List[str]) -> None:
        color[node] = GRAY
        path.append(node)
        for neighbor in graph.get(node, []):
            if color.get(neighbor, WHITE) == WHITE:
                visit(neighbor, path)
            elif color.get(neighbor) == GRAY:
                start = path.index(neighbor)
                cycles.append(path[start:] + [neighbor])
        path.pop()
        color[node] = BLACK

    for node in list(graph.keys()):
        if color.get(node, WHITE) == WHITE:
            visit(node, [])

    return cycles


def would_create_cycle(existing_edges: Iterable[Tuple[str, str]], new_edge: Tuple[str, str]) -> bool:
    """Pure validator for a future write path (not wired in anywhere yet):
    given the (source, target) edges that already exist for one
    relationship_type (or the parent_skill_id graph), would adding
    `new_edge` close a cycle? A path already exists from new_edge's target
    back to its source iff appending new_edge would create one."""
    src, tgt = new_edge
    if src == tgt:
        return True
    graph: Dict[str, List[str]] = {}
    for a, b in existing_edges:
        graph.setdefault(a, []).append(b)

    seen: Set[str] = set()
    stack = [tgt]
    while stack:
        node = stack.pop()
        if node == src:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, []))
    return False


def run_live_reconciliation(supabase) -> ReconciliationReport:
    """`supabase` is whatever get_supabase() returns (or a fake with the
    same .table(...).select(...).execute() shape, for tests)."""
    relationships = supabase.table("skill_relationships").select(
        "source_skill_id, target_skill_id, relationship_type"
    ).execute().data or []
    skill_rows = supabase.table("skills").select("skill_id").execute().data or []
    existing_skill_ids = {r["skill_id"] for r in skill_rows}

    return find_relationship_issues(relationships, existing_skill_ids)


if __name__ == "__main__":
    # ponytail: one runnable check per concern -- orphan/dup/self-loop/cycle
    # detection, plus the future-write cycle guard.
    report = find_relationship_issues(
        relationships=[
            {"source_skill_id": "a", "target_skill_id": "b", "relationship_type": "assesses"},
            {"source_skill_id": "a", "target_skill_id": "b", "relationship_type": "assesses"},  # duplicate
            {"source_skill_id": "gone", "target_skill_id": "b", "relationship_type": "assesses"},  # orphaned source
            {"source_skill_id": "a", "target_skill_id": "gone", "relationship_type": "assesses"},  # orphaned target
            {"source_skill_id": "a", "target_skill_id": "a", "relationship_type": "assesses"},  # self-loop
            {"source_skill_id": "a", "target_skill_id": "b", "relationship_type": "not_a_type"},  # invalid type
        ],
        existing_skill_ids=["a", "b"],
    )
    assert len(report["duplicates"]) == 1
    assert len(report["orphaned_source"]) == 1
    assert len(report["orphaned_target"]) == 1
    assert len(report["self_loops"]) == 1
    assert len(report["invalid_type"]) == 1
    assert report["clean_count"] == 1

    cycles = find_cycles([("x", "y"), ("y", "z"), ("z", "x")])
    assert len(cycles) == 1 and set(cycles[0]) == {"x", "y", "z"}
    assert find_cycles([("x", "y"), ("y", "z")]) == []

    assert would_create_cycle([("x", "y"), ("y", "z")], ("z", "x")) is True
    assert would_create_cycle([("x", "y")], ("y", "z")) is False
    assert would_create_cycle([], ("x", "x")) is True

    print("OK")
