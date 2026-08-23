"""E2.5: Targeted Practice V1 -- one canonical, deterministic "what should
this learner practice next" service for Listening and Technique, built
entirely on the existing Weakness Graph (skill_graph.get_weakness), the
Knowledge Graph bridge (skill_bridge_resolver.resolve_skill_id), and
content_skill_map. No new mastery/EMA/scoring math, no AI, no writes.

Scope is intentionally Listening + Technique only for v1 -- Reading/
Writing/Speaking have no content_skill_map coverage yet (E2.5 discovery).
Adding a module later means adding one `_xxx_candidates()` builder; the
shared dedup/rank/limit spine in get_targeted_practice does not change.

The launchable unit is never the content_skill_map row's own content_type:
- Listening: a skill maps to listening_section rows (content_skill_map's
  heuristic:part backfill), but a section can't be practiced standalone in
  the exam-format player -- the recommendation resolves each mapped
  section up to its parent listening_test (listening_sections.test_id).
- Technique: a skill maps to a technique row and/or micro_practice rows.
  Either way the recommendation resolves down to one launchable
  micro_practice (the thing practice_attempts actually records against),
  picking the learner's technique_progress.recommended_stage() practice
  when only the technique itself was mapped.

"Recent"/"completed" exclusion for both modules is lifetime existence (any
submission for that test_id / any practice_attempts row for that
micro_practice_id) -- the only recency convention this codebase already
has (has_free_module_attempt, /listening/tests/completed-ids), and the
task instructions are explicit not to invent a new time-window. One
consequence: content that has ever been attempted is filtered out before
ranking, so ranking rules "never attempted first" / "longest time since
attempt" are structurally always-constant for whatever survives -- kept in
the sort key for spec fidelity, not because they currently discriminate.
"""
import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from supabase import Client

from app.core.supabase import get_supabase
from app.core.threading import run_sync
from app.services import skill_graph, technique_progress
from app.services.plan_gating import (
    get_plan_from_profile, has_free_module_attempt, has_listening_access, parse_timestamp,
)
from app.services.skill_bridge_resolver import resolve_skill_id

logger = logging.getLogger(__name__)

APPROVED_MODULES = {"listening", "technique"}

_LISTENING_PART_LABELS = {"A": "Part A", "B": "Part B", "C": "Part C"}

# Relationship types that plausibly mean "practicing this helps that weak
# skill" -- see _relationship_fallback_skill_ids.
_FALLBACK_RELATIONSHIP_TYPES = ("trains_toward", "prerequisite_of")


@dataclass(frozen=True)
class TargetedPracticeItem:
    content_type: str  # "listening_test" | "micro_practice"
    content_id: int
    skill_tag: str  # legacy tag, e.g. "listening:A" / "technique:skimming"
    skill_label: str
    band: float
    match_type: str  # "direct" -- the only value v1 ever produces
    title: str
    part: Optional[str] = None
    difficulty: Optional[str] = None


async def get_targeted_practice(
    user_db: Client, user_id: str, module: str, limit: int = 5,
) -> List[TargetedPracticeItem]:
    """The single entry point every future caller should use instead of
    reimplementing weakness -> content resolution. Plan gating lives here
    (not in a router) so a future caller can't accidentally bypass it."""
    if module not in APPROVED_MODULES:
        raise ValueError(f"unsupported module: {module!r}")

    if module == "listening":
        candidates = await _listening_candidates(user_db, user_id)
    else:
        candidates = await _technique_candidates(user_db, user_id)

    return _dedup_and_rank(candidates)[:limit]


def _dedup_and_rank(candidates: List[Tuple[TargetedPracticeItem, float]]) -> List[TargetedPracticeItem]:
    """candidates arrives in weakest-skill-first order (each builder walks
    get_weakness's own weakest-first list). First occurrence of a
    (content_type, content_id) wins the dedup -- since traversal is
    weakest-first, that's already the weakest/strongest skill context that
    produced it, satisfying the "preserve context" dedup rule for free."""
    seen: Dict[tuple, Tuple[TargetedPracticeItem, float]] = {}
    for item, created_ts in candidates:
        key = (item.content_type, item.content_id)
        if key not in seen:
            seen[key] = (item, created_ts)

    ranked = sorted(
        seen.values(),
        key=lambda pair: (
            pair[0].band,  # 1. weakest skill first
            0 if pair[0].match_type == "direct" else 1,  # 2. direct match first
            -pair[1],  # 5. created_at DESC
            pair[0].content_id,  # 6. content_id ASC
        ),
    )
    return [item for item, _ in ranked]


def _epoch(ts) -> float:
    dt = parse_timestamp(ts)
    return dt.timestamp() if dt else 0.0


# ── Listening ──────────────────────────────────────────────────────────

async def _listening_plan_allows(user_db: Client, user_id: str) -> bool:
    """Mirrors listening.py's _require_listening_plan (minus the
    mock-pinned-test bypass, which is per-test_id and has no meaning for a
    recommendation list): paid plans always pass; a free-plan learner
    passes only if their one lifetime free attempt is unspent."""
    profile = await run_sync(
        user_db.table("user_profiles").select("plan, plan_expires_at").eq("user_id", user_id).execute
    )
    plan = get_plan_from_profile(profile.data[0] if profile.data else {})
    if has_listening_access(plan):
        return True
    return plan == "free" and has_free_module_attempt(user_db, user_id, "listening")


async def _attempted_listening_test_ids(user_db: Client, user_id: str) -> Set[int]:
    """test_id lives inside submissions.feedback's JSON blob, not a column
    -- same robust str/dict parsing listening.py itself uses in three
    places (get_test/recommend/completed-ids)."""
    subs = await run_sync(
        user_db.table("submissions").select("feedback").eq("user_id", user_id).eq("module", "listening").execute
    )
    test_ids: Set[int] = set()
    for s in subs.data:
        try:
            fb = json.loads(s["feedback"]) if isinstance(s["feedback"], str) else (s["feedback"] or {})
        except (json.JSONDecodeError, TypeError):
            continue
        if fb.get("test_id") is not None:
            test_ids.add(fb["test_id"])
    return test_ids


async def _listening_candidates(user_db: Client, user_id: str) -> List[Tuple[TargetedPracticeItem, float]]:
    if not await _listening_plan_allows(user_db, user_id):
        return []

    weak = await skill_graph.get_weakness(
        user_db, user_id, "listening:", lambda s: _LISTENING_PART_LABELS.get(s, s)
    )
    if not weak:
        return []

    attempted_test_ids = await _attempted_listening_test_ids(user_db, user_id)

    supabase = get_supabase()
    out: List[Tuple[TargetedPracticeItem, float]] = []
    for w in weak:
        tag = f"listening:{w['skill']}"
        skill_id = resolve_skill_id(tag)
        if skill_id is None:
            continue

        mapped = await run_sync(
            supabase.table("content_skill_map").select("content_id")
            .eq("skill_id", str(skill_id)).eq("content_type", "listening_section").execute
        )
        section_ids = [r["content_id"] for r in mapped.data]
        if not section_ids:
            continue

        sections = await run_sync(
            supabase.table("listening_sections").select("id, test_id, part, difficulty")
            .in_("id", section_ids).eq("is_active", True).execute
        )
        # A test is eligible if ANY of its mapped sections survived above;
        # keep the lowest-id section per test as the part/difficulty source
        # so a multi-match stays deterministic.
        by_test: Dict[int, dict] = {}
        for s in sorted(sections.data, key=lambda r: r["id"]):
            if s["test_id"] is None or s["test_id"] in by_test:
                continue
            by_test[s["test_id"]] = s

        test_ids = [tid for tid in by_test if tid not in attempted_test_ids]
        if not test_ids:
            continue

        tests = await run_sync(
            supabase.table("listening_tests").select("id, title, created_at")
            .in_("id", test_ids).eq("is_active", True).execute
        )
        for t in sorted(tests.data, key=lambda r: r["id"]):
            section = by_test[t["id"]]
            out.append((
                TargetedPracticeItem(
                    content_type="listening_test",
                    content_id=t["id"],
                    skill_tag=tag,
                    skill_label=w["label"],
                    band=w["band"],
                    match_type="direct",
                    title=t["title"],
                    part=section.get("part"),
                    difficulty=section.get("difficulty"),
                ),
                _epoch(t.get("created_at")),
            ))
    return out


# ── Technique ──────────────────────────────────────────────────────────

async def _attempted_micro_practice_ids(user_db: Client, user_id: str) -> Set[int]:
    rows = await run_sync(
        user_db.table("practice_attempts").select("micro_practice_id").eq("user_id", user_id).execute
    )
    return {r["micro_practice_id"] for r in rows.data if r.get("micro_practice_id") is not None}


async def _technique_candidates(user_db: Client, user_id: str) -> List[Tuple[TargetedPracticeItem, float]]:
    """Free for every authenticated user -- no plan gating call here, on
    purpose (matches technique.py's own router)."""
    weak = await skill_graph.get_weakness(user_db, user_id, "technique:")
    if not weak:
        return []

    attempted_ids = await _attempted_micro_practice_ids(user_db, user_id)

    supabase = get_supabase()
    out: List[Tuple[TargetedPracticeItem, float]] = []
    for w in weak:
        tag = f"technique:{w['skill']}"
        skill_id = resolve_skill_id(tag)
        if skill_id is None:
            continue

        mapped = await run_sync(
            supabase.table("content_skill_map").select("content_id, content_type")
            .eq("skill_id", str(skill_id)).in_("content_type", ["technique", "micro_practice"]).execute
        )
        if not mapped.data:
            continue

        practice_ids_direct = sorted({r["content_id"] for r in mapped.data if r["content_type"] == "micro_practice"})
        technique_ids = sorted({r["content_id"] for r in mapped.data if r["content_type"] == "technique"})

        resolved: Dict[int, dict] = {}  # micro_practice_id -> micro_practices row

        # Path 1: skill mapped straight to a micro_practice. Its own active
        # flag AND its parent technique's active flag both gate it.
        if practice_ids_direct:
            direct = await run_sync(
                supabase.table("micro_practices").select("id, technique_id, title, difficulty, created_at")
                .in_("id", practice_ids_direct).eq("active", True).execute
            )
            parent_ids = sorted({mp["technique_id"] for mp in direct.data})
            active_parents: Set[int] = set()
            if parent_ids:
                parents = await run_sync(
                    supabase.table("techniques").select("id").in_("id", parent_ids).eq("active", True).execute
                )
                active_parents = {t["id"] for t in parents.data}
            for mp in direct.data:
                if mp["technique_id"] in active_parents:
                    resolved[mp["id"]] = mp

        # Path 2: skill mapped to the technique itself -- resolve down to
        # the one micro_practice matching the learner's recommended stage
        # (reusing this weak skill's own attempts/band -- technique's own
        # skill_tag weakness IS its mastery input, no second calc).
        if technique_ids:
            techs = await run_sync(
                supabase.table("techniques").select("id").in_("id", technique_ids).eq("active", True).execute
            )
            active_technique_ids = [t["id"] for t in techs.data]
            if active_technique_ids:
                practices = await run_sync(
                    supabase.table("micro_practices").select("id, technique_id, title, difficulty, stage, created_at")
                    .in_("technique_id", active_technique_ids).eq("active", True)
                    .order("sort_order").order("id").execute
                )
                by_technique: Dict[int, list] = {}
                for p in practices.data:
                    by_technique.setdefault(p["technique_id"], []).append(p)
                stage = technique_progress.recommended_stage(w["attempts"], w["band"])
                for tid in active_technique_ids:
                    pool = by_technique.get(tid, [])
                    if not pool:
                        continue
                    pick = next((p for p in pool if p["stage"] == stage), pool[0])
                    resolved.setdefault(pick["id"], pick)

        for pid in sorted(resolved):
            if pid in attempted_ids:
                continue
            mp = resolved[pid]
            out.append((
                TargetedPracticeItem(
                    content_type="micro_practice",
                    content_id=pid,
                    skill_tag=tag,
                    skill_label=w["label"],
                    band=w["band"],
                    match_type="direct",
                    title=mp["title"],
                    part=None,
                    difficulty=mp.get("difficulty"),
                ),
                _epoch(mp.get("created_at")),
            ))
    return out


# ── Relationship fallback (built, not wired -- see module docstring) ────

def _relationship_fallback_skill_ids(skill_id: UUID) -> List[UUID]:
    """Optional, deterministic fallback: skills this weak skill "trains
    toward" or is a "prerequisite_of", so a skill with zero direct content
    mappings could still surface a related practice. Not called from
    get_targeted_practice in v1 -- both relationship types are currently
    unseeded for every listening.* / technique.* skill (see
    20260822010000_skill_relationships.sql's header notes: only Reading
    Part A/B/C "assesses" edges and one Speaking "rolls_up_into" edge
    exist), so wiring it in today would add a code path with zero live
    effect. Kept as a standalone, tested building block for when that data
    exists -- never fabricates a relationship that isn't in the graph."""
    rows = get_supabase().table("skill_relationships").select("target_skill_id").eq(
        "source_skill_id", str(skill_id)
    ).in_("relationship_type", list(_FALLBACK_RELATIONSHIP_TYPES)).execute()
    return [UUID(r["target_skill_id"]) for r in rows.data]
