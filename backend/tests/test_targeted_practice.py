import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import targeted_practice as tp
from app.services.skill_bridge_resolver import _reset_cache_for_tests

BACKEND_DIR = Path(__file__).resolve().parents[1]

LISTEN_A = "11111111-1111-1111-1111-111111111111"
LISTEN_B = "22222222-2222-2222-2222-222222222222"
TECH_SKIMMING = "33333333-3333-3333-3333-333333333333"

_SKILLS_CACHE_SEED = {
    "listening.part.a": LISTEN_A,
    "listening.part.b": LISTEN_B,
    "technique.skimming": TECH_SKIMMING,
}


@pytest.fixture(autouse=True)
def _seeded_bridge_cache():
    _reset_cache_for_tests(dict(_SKILLS_CACHE_SEED))
    yield
    _reset_cache_for_tests(None)


def _run(coro):
    return asyncio.run(coro)


# ── fake supabase (see test_technique_router.py's FakeQuery convention) ──

class FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []
        self._columns = None
        self._limit = None
        self._count = False

    def select(self, columns="*", count=None, **_k):
        self._columns = [c.strip() for c in columns.split(",")] if columns and columns != "*" else None
        self._count = count is not None
        return self

    def eq(self, col, val):
        self._filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def in_(self, col, values):
        values = set(values)
        self._filters.append(lambda r, c=col, v=values: r.get(c) in v)
        return self

    def like(self, col, pattern):
        prefix = pattern[:-1] if pattern.endswith("%") else pattern
        self._filters.append(lambda r, c=col, p=prefix: str(r.get(c, "")).startswith(p))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = [r for r in self._rows if all(f(r) for f in self._filters)]
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._columns:
            rows = [{c: r.get(c) for c in self._columns} for r in rows]
        return SimpleNamespace(data=rows, count=len(rows) if self._count else None)


class FakeSupabase:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return FakeQuery(list(self._tables.get(name, [])))


def _tables(**overrides):
    base = {
        "user_skill_stats": [], "content_skill_map": [], "listening_sections": [],
        "listening_tests": [], "submissions": [], "user_profiles": [],
        "techniques": [], "micro_practices": [], "practice_attempts": [],
        "skill_relationships": [],
    }
    base.update(overrides)
    return base


def _fake(**overrides):
    return FakeSupabase(_tables(**overrides))


def _paid_profile(user_id="user-1", plan="pro"):
    return {"user_id": user_id, "plan": plan, "plan_expires_at": "2030-01-01T00:00:00+00:00"}


def _weak(tag, band, attempts=3, user_id="user-1"):
    return {"user_id": user_id, "skill_tag": tag, "attempts": attempts, "ema_score": band}


def _get(module, supa, user_id="user-1", limit=5):
    with patch.object(tp, "get_supabase", return_value=supa):
        return _run(tp.get_targeted_practice(supa, user_id, module, limit=limit))


# ── 1. weak skill selection ───────────────────────────────────────────────

def test_weak_skill_selection_skips_strong_and_low_attempt_skills():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[
            _weak("listening:A", 2.0),           # weak: eligible
            _weak("listening:B", 5.5),            # too strong (>= ceiling)
            {"user_id": "user-1", "skill_tag": "listening:C", "attempts": 1, "ema_score": 1.0},  # too few attempts
        ],
        content_skill_map=[
            {"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10},
        ],
        listening_sections=[{"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True}],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}],
    )
    result = _get("listening", supa)
    assert [r.skill_tag for r in result] == ["listening:A"]
    assert result[0].band == 2.0


# ── 2. skill_tag -> skill_id resolution ──────────────────────────────────

def test_skill_tag_resolves_via_bridge_resolver():
    from uuid import UUID
    from app.services.skill_bridge_resolver import resolve_skill_id
    assert resolve_skill_id("listening:A") == UUID(LISTEN_A)


# ── 3. Listening section -> parent listening_test resolution ────────────

def test_listening_section_resolves_to_parent_test():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("listening:A", 2.0)],
        content_skill_map=[{"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10}],
        listening_sections=[{"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True}],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}],
    )
    result = _get("listening", supa)
    assert len(result) == 1
    assert result[0].content_type == "listening_test"
    assert result[0].content_id == 100
    assert result[0].part == "A"
    assert result[0].difficulty == "easy"


# ── 4. Listening test dedup (two sections, one test, same skill) ────────

def test_listening_test_deduplicated_across_its_own_sections():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("listening:A", 2.0)],
        content_skill_map=[
            {"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10},
            {"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 11},
        ],
        listening_sections=[
            {"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True},
            {"id": 11, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True},
        ],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}],
    )
    result = _get("listening", supa)
    assert len(result) == 1
    assert result[0].content_id == 100


# ── 5. completed Listening test exclusion ────────────────────────────────

def test_completed_listening_test_excluded():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("listening:A", 2.0)],
        content_skill_map=[{"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10}],
        listening_sections=[{"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True}],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}],
        submissions=[{"user_id": "user-1", "module": "listening", "feedback": '{"test_id": 100}'}],
    )
    assert _get("listening", supa) == []


# ── 6. recent Listening test exclusion (lifetime, no time window) ───────

def test_old_listening_submission_still_excludes_the_test():
    # No recency cutoff exists anywhere in this codebase (see module
    # docstring) -- a submission from any point in the past still excludes.
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("listening:A", 2.0)],
        content_skill_map=[{"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10}],
        listening_sections=[{"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True}],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2020-01-01T00:00:00Z"}],
        submissions=[{
            "user_id": "user-1", "module": "listening",
            "feedback": '{"test_id": 100}',
        }],
    )
    assert _get("listening", supa) == []


# ── 7. inactive Listening test exclusion ─────────────────────────────────

def test_inactive_listening_test_excluded():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("listening:A", 2.0)],
        content_skill_map=[{"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10}],
        listening_sections=[{"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True}],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": False, "created_at": "2026-01-01T00:00:00Z"}],
    )
    assert _get("listening", supa) == []


# ── 8. technique active filtering (technique-mapped path) ───────────────

def test_inactive_technique_excludes_its_mapped_recommendation():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("technique:skimming", 2.0)],
        content_skill_map=[{"skill_id": TECH_SKIMMING, "content_type": "technique", "content_id": 1}],
        techniques=[{"id": 1, "active": False}],
        micro_practices=[{"id": 50, "technique_id": 1, "active": True, "title": "Skim it",
                           "difficulty": "easy", "stage": "guided", "created_at": "2026-01-01T00:00:00Z"}],
    )
    assert _get("technique", supa) == []


# ── 9. micro-practice active filtering (direct-mapped path) ─────────────

def test_inactive_micro_practice_excluded():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("technique:skimming", 2.0)],
        content_skill_map=[{"skill_id": TECH_SKIMMING, "content_type": "micro_practice", "content_id": 50}],
        techniques=[{"id": 1, "active": True}],
        micro_practices=[{"id": 50, "technique_id": 1, "active": False, "title": "Skim it",
                           "difficulty": "easy", "created_at": "2026-01-01T00:00:00Z"}],
    )
    assert _get("technique", supa) == []


# ── 10. inactive parent technique exclusion (direct-mapped path) ────────

def test_direct_micro_practice_excluded_when_parent_technique_inactive():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("technique:skimming", 2.0)],
        content_skill_map=[{"skill_id": TECH_SKIMMING, "content_type": "micro_practice", "content_id": 50}],
        techniques=[{"id": 1, "active": False}],
        micro_practices=[{"id": 50, "technique_id": 1, "active": True, "title": "Skim it",
                           "difficulty": "easy", "created_at": "2026-01-01T00:00:00Z"}],
    )
    assert _get("technique", supa) == []


# ── 11. technique attempt filtering ──────────────────────────────────────

def test_already_attempted_micro_practice_excluded():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("technique:skimming", 2.0)],
        content_skill_map=[{"skill_id": TECH_SKIMMING, "content_type": "micro_practice", "content_id": 50}],
        techniques=[{"id": 1, "active": True}],
        micro_practices=[{"id": 50, "technique_id": 1, "active": True, "title": "Skim it",
                           "difficulty": "easy", "created_at": "2026-01-01T00:00:00Z"}],
        practice_attempts=[{"user_id": "user-1", "micro_practice_id": 50, "technique_id": 1,
                             "score": 5, "completed_at": "2026-01-01T00:00:00Z"}],
    )
    assert _get("technique", supa) == []


# ── 12. weakest skill precedence ─────────────────────────────────────────

def test_weakest_skill_content_ranked_first():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("listening:A", 1.5), _weak("listening:B", 3.5)],
        content_skill_map=[
            {"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10},
            {"skill_id": LISTEN_B, "content_type": "listening_section", "content_id": 20},
        ],
        listening_sections=[
            {"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True},
            {"id": 20, "test_id": 200, "part": "B", "difficulty": "easy", "is_active": True},
        ],
        listening_tests=[
            {"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"},
            {"id": 200, "title": "Test 200", "is_active": True, "created_at": "2026-01-01T00:00:00Z"},
        ],
    )
    result = _get("listening", supa)
    assert [r.content_id for r in result] == [100, 200]


# ── 13. deterministic ordering (tie-break by content_id) ────────────────

def test_tied_band_breaks_ties_by_content_id_ascending():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("listening:A", 2.0)],
        content_skill_map=[
            {"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 30},
            {"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 31},
        ],
        listening_sections=[
            {"id": 30, "test_id": 300, "part": "A", "difficulty": "easy", "is_active": True},
            {"id": 31, "test_id": 200, "part": "A", "difficulty": "easy", "is_active": True},
        ],
        listening_tests=[
            {"id": 300, "title": "Test 300", "is_active": True, "created_at": "2026-01-01T00:00:00Z"},
            {"id": 200, "title": "Test 200", "is_active": True, "created_at": "2026-01-01T00:00:00Z"},
        ],
    )
    result1 = _get("listening", supa)
    result2 = _get("listening", supa)
    assert [r.content_id for r in result1] == [200, 300]
    assert [r.content_id for r in result1] == [r.content_id for r in result2]


# ── 14. duplicate content across skills ──────────────────────────────────

def test_same_test_reachable_via_two_skills_kept_once_with_weakest_context():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("listening:A", 2.0), _weak("listening:B", 4.0)],
        content_skill_map=[
            {"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10},
            {"skill_id": LISTEN_B, "content_type": "listening_section", "content_id": 20},
        ],
        listening_sections=[
            {"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True},
            {"id": 20, "test_id": 100, "part": "B", "difficulty": "easy", "is_active": True},
        ],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}],
    )
    result = _get("listening", supa)
    assert len(result) == 1
    assert result[0].skill_tag == "listening:A"  # weakest-first traversal wins the dedup


# ── 15. module isolation ─────────────────────────────────────────────────

def test_module_isolation_and_unsupported_module_rejected():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("listening:A", 2.0), _weak("technique:skimming", 2.0)],
        content_skill_map=[
            {"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10},
            {"skill_id": TECH_SKIMMING, "content_type": "micro_practice", "content_id": 50},
        ],
        listening_sections=[{"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True}],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}],
        techniques=[{"id": 1, "active": True}],
        micro_practices=[{"id": 50, "technique_id": 1, "active": True, "title": "Skim it",
                           "difficulty": "easy", "created_at": "2026-01-01T00:00:00Z"}],
    )
    listening_result = _get("listening", supa)
    technique_result = _get("technique", supa)
    assert {r.content_type for r in listening_result} == {"listening_test"}
    assert {r.content_type for r in technique_result} == {"micro_practice"}

    with pytest.raises(ValueError):
        _run(tp.get_targeted_practice(supa, "user-1", "reading"))


# ── 16. user isolation ───────────────────────────────────────────────────

def test_other_users_data_never_leaks_in():
    supa = _fake(
        user_profiles=[_paid_profile("user-1"), _paid_profile("user-2")],
        user_skill_stats=[
            _weak("listening:A", 2.0, user_id="user-1"),
            _weak("listening:A", 1.0, user_id="user-2"),  # different user's weaker signal
        ],
        content_skill_map=[{"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10}],
        listening_sections=[{"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True}],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}],
        submissions=[{"user_id": "user-2", "module": "listening", "feedback": '{"test_id": 100}'}],
    )
    result = _get("listening", supa, user_id="user-1")
    assert len(result) == 1
    assert result[0].band == 2.0  # user-1's own band, not user-2's


# ── 17. Listening plan restriction ───────────────────────────────────────

def test_free_plan_with_spent_free_attempt_blocked_from_listening():
    supa = _fake(
        user_profiles=[{"user_id": "user-1", "plan": "free", "plan_expires_at": None}],
        user_skill_stats=[_weak("listening:A", 2.0)],
        content_skill_map=[{"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10}],
        listening_sections=[{"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True}],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}],
        submissions=[{"user_id": "user-1", "module": "listening", "feedback": '{"test_id": 999}'}],
    )
    assert _get("listening", supa) == []


def test_free_plan_with_unspent_free_attempt_allowed():
    supa = _fake(
        user_profiles=[{"user_id": "user-1", "plan": "free", "plan_expires_at": None}],
        user_skill_stats=[_weak("listening:A", 2.0)],
        content_skill_map=[{"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10}],
        listening_sections=[{"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True}],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}],
    )
    result = _get("listening", supa)
    assert len(result) == 1


# ── 18. Technique remains accessible without plan gating ────────────────

def test_technique_ignores_plan_entirely():
    supa = _fake(
        user_profiles=[{"user_id": "user-1", "plan": "free", "plan_expires_at": None}],
        user_skill_stats=[_weak("technique:skimming", 2.0)],
        content_skill_map=[{"skill_id": TECH_SKIMMING, "content_type": "micro_practice", "content_id": 50}],
        techniques=[{"id": 1, "active": True}],
        micro_practices=[{"id": 50, "technique_id": 1, "active": True, "title": "Skim it",
                           "difficulty": "easy", "created_at": "2026-01-01T00:00:00Z"}],
        # no user_profiles row at all -- must not matter for technique.
    )
    result = _get("technique", supa)
    assert len(result) == 1


# ── 19. empty weakness result ────────────────────────────────────────────

def test_empty_weakness_returns_empty_list():
    supa = _fake(user_profiles=[_paid_profile()])
    assert _get("listening", supa) == []
    assert _get("technique", supa) == []


# ── 20. empty content mapping ────────────────────────────────────────────

def test_weak_skill_with_no_content_mapping_returns_empty():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[_weak("listening:A", 2.0)],
    )
    assert _get("listening", supa) == []


# ── 21. unknown skill resolution fails safely ────────────────────────────

def test_unresolvable_skill_tag_skipped_not_raised():
    supa = _fake(
        user_profiles=[_paid_profile()],
        user_skill_stats=[
            _weak("listening:Z", 2.0),  # "Z" has no registry entry at all
            _weak("listening:A", 2.5),
        ],
        content_skill_map=[{"skill_id": LISTEN_A, "content_type": "listening_section", "content_id": 10}],
        listening_sections=[{"id": 10, "test_id": 100, "part": "A", "difficulty": "easy", "is_active": True}],
        listening_tests=[{"id": 100, "title": "Test 100", "is_active": True, "created_at": "2026-01-01T00:00:00Z"}],
    )
    result = _get("listening", supa)  # must not raise
    assert [r.skill_tag for r in result] == ["listening:A"]


# ── 22. relationship fallback returns empty when no usable content exists ─

def test_relationship_fallback_empty_when_graph_has_no_edges():
    from uuid import UUID
    supa = _fake(skill_relationships=[])
    with patch.object(tp, "get_supabase", return_value=supa):
        assert tp._relationship_fallback_skill_ids(UUID(LISTEN_A)) == []


# ── 23. no AI calls ───────────────────────────────────────────────────────

def test_module_source_makes_no_ai_calls():
    source = (BACKEND_DIR / "app" / "services" / "targeted_practice.py").read_text()
    for forbidden in ("_call_ai", "openai", "ai_scoring", "ai_registry", "await generate"):
        assert forbidden not in source


# ── 24. no writes ──────────────────────────────────────────────────────────

def test_module_source_performs_no_writes():
    source = (BACKEND_DIR / "app" / "services" / "targeted_practice.py").read_text()
    for forbidden in (".insert(", ".upsert(", ".update(", ".delete("):
        assert forbidden not in source


# ── 25. existing recommendation services remain untouched ────────────────

def test_no_existing_recommender_imports_targeted_practice():
    untouched = [
        "app/routers/listening.py", "app/routers/reading.py", "app/routers/speaking.py",
        "app/routers/writing.py", "app/routers/technique.py", "app/services/listening_coach.py",
        "app/services/coach.py", "app/services/skill_graph.py",
    ]
    for rel in untouched:
        source = (BACKEND_DIR / rel).read_text()
        assert "targeted_practice" not in source
