import asyncio
import logging
from pathlib import Path
from typing import Dict, List
from uuid import UUID

import pytest

from app.services.skill_registry import LEGACY_TAG_TO_CODE, SEED_SKILLS
from app.services.skill_bridge_resolver import (
    CODE_TO_LEGACY_TAG,
    _reset_cache_for_tests,
    code_to_legacy_tag,
    resolve_skill_id,
)
from app.services.user_skill_bridge_backfill import classify_pairs, run_backfill
from app.services.user_skill_bridge_reconciliation import reconcile, run_live_reconciliation
from app.services.user_skill_bridge_content import get_content_for_skill

_MIGRATION_SQL = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260822020000_user_skill_bridge.sql"
).read_text()

_UUID_A = "11111111-1111-1111-1111-111111111111"  # reading.part.a
_UUID_B = "22222222-2222-2222-2222-222222222222"  # technique.scanning
_UUID_C = "33333333-3333-3333-3333-333333333333"  # reading.skill.scanning
_UUID_D = "44444444-4444-4444-4444-444444444444"  # reading.skill.main_idea


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _seeded_resolver_cache():
    _reset_cache_for_tests({
        "reading.part.a": _UUID_A,
        "technique.scanning": _UUID_B,
        "reading.skill.scanning": _UUID_C,
        "reading.skill.main_idea": _UUID_D,
    })
    yield
    _reset_cache_for_tests(None)


# ── fake supabase: select/eq chains + a real dict-backed user_skill_bridge
# table so upsert dedup / write-tracking is observable, same convention as
# test_content_skill_map.py's _FakeSupabase ──────────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeExecuted:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _FakeResult(self._data)


class _FakeTableQuery:
    def __init__(self, supa, name):
        self.supa = supa
        self.name = name
        self.filters = {}

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def in_(self, col, vals):
        self.filters[col] = set(vals)
        return self

    def upsert(self, row, on_conflict=None):
        self.supa.write_calls.append(self.name)
        if self.name != "user_skill_bridge":
            raise AssertionError(f"unexpected write to table {self.name!r} -- only user_skill_bridge may be written")
        key = (row["user_id"], row["skill_tag"])
        self.supa.bridge_rows[key] = dict(row)
        return _FakeExecuted([self.supa.bridge_rows[key]])

    def execute(self):
        if self.name == "user_skill_bridge":
            rows = list(self.supa.bridge_rows.values())
        else:
            rows = list(self.supa.data.get(self.name, []))
        for col, val in self.filters.items():
            if isinstance(val, set):
                rows = [r for r in rows if r.get(col) in val]
            else:
                rows = [r for r in rows if r.get(col) == val]
        return _FakeResult(rows)


class _FakeSupabase:
    def __init__(self, data: Dict[str, List[Dict]] = None):
        self.data = data or {}
        self.bridge_rows = {}
        self.write_calls: List[str] = []

    def table(self, name):
        return _FakeTableQuery(self, name)


# ── 1. all known tag mappings round-trip (superset of the 41 tags observed
# in production -- QA's user_skill_stats is currently empty (0 rows), see
# the E2.4.4 report; testing the full 44-entry registry is strictly more
# thorough than testing whichever subset happened to be observed) ─────────

def test_every_seed_legacy_tag_has_a_deterministic_code():
    assert len(LEGACY_TAG_TO_CODE) == len(SEED_SKILLS) == 44
    for tag, code in LEGACY_TAG_TO_CODE.items():
        assert CODE_TO_LEGACY_TAG[code] == tag


def test_resolver_is_deterministic_for_every_seed_tag_given_a_full_cache():
    full_cache = {s["code"]: f"00000000-0000-0000-0000-{i:012d}" for i, s in enumerate(SEED_SKILLS)}
    _reset_cache_for_tests(full_cache)
    for s in SEED_SKILLS:
        resolved = resolve_skill_id(s["legacy_tag"])
        assert resolved is not None
        assert str(resolved) == full_cache[s["code"]]
        # calling twice must return the exact same value -- pure/deterministic
        assert resolve_skill_id(s["legacy_tag"]) == resolved


# ── 2/3. colon->dot and hyphen->underscore, per the LEGACY_TAG_TO_CODE dict ─

def test_double_colon_tag_maps_to_dotted_code():
    assert LEGACY_TAG_TO_CODE["reading:skill:scanning"] == "reading.skill.scanning"
    assert resolve_skill_id("reading:skill:scanning") == UUID(_UUID_C)


def test_hyphenated_tag_maps_to_underscored_code():
    assert LEGACY_TAG_TO_CODE["reading:skill:main-idea"] == "reading.skill.main_idea"
    assert resolve_skill_id("reading:skill:main-idea") == UUID(_UUID_D)


# ── 4. technique.scanning vs reading.skill.scanning stay distinct ─────────

def test_technique_scanning_and_reading_skill_scanning_are_distinct():
    assert LEGACY_TAG_TO_CODE["technique:scanning"] == "technique.scanning"
    assert LEGACY_TAG_TO_CODE["reading:skill:scanning"] == "reading.skill.scanning"
    assert resolve_skill_id("technique:scanning") == UUID(_UUID_B)
    assert resolve_skill_id("reading:skill:scanning") == UUID(_UUID_C)
    assert resolve_skill_id("technique:scanning") != resolve_skill_id("reading:skill:scanning")


# ── 5. unknown AI-generated speaking key (AI-key safety) ──────────────────

def test_unknown_ai_generated_speaking_key_resolves_to_none_and_logs(caplog):
    with caplog.at_level(logging.WARNING):
        result = resolve_skill_id("speaking:some_new_ai_criterion_key")
    assert result is None
    assert any("unknown legacy skill_tag" in r.message for r in caplog.records)
    # must never create a registry row as a side effect
    assert "speaking:some_new_ai_criterion_key" not in LEGACY_TAG_TO_CODE


def test_unknown_speaking_key_does_not_raise_or_break_backfill_classification():
    result = classify_pairs([("u1", "speaking:brand_new_ai_key")])
    assert result["unknown"] == [("u1", "speaking:brand_new_ai_key")]
    assert result["known"] == []
    assert result["ambiguous"] == []


# ── 6. ambiguous mapping rejection: no fuzzy/prefix matching, and the
# backfill's own "ambiguous" bucket (known tag, code missing from cache) ──

def test_resolver_never_fuzzy_or_prefix_matches():
    # near-misses of real tags must not resolve just because they share a prefix
    assert resolve_skill_id("reading:skill:scanningx") is None
    assert resolve_skill_id("reading:skill:scan") is None
    assert resolve_skill_id("technique:scan") is None
    assert resolve_skill_id("Reading:A") is None  # case must match exactly too


def test_backfill_classifies_registry_drift_as_ambiguous_not_unknown():
    _reset_cache_for_tests({"reading.part.a": _UUID_A})  # listening.part.a deliberately absent
    result = classify_pairs([("u1", "listening:A")])
    assert result["ambiguous"] == [("u1", "listening:A")]
    assert result["unknown"] == []
    assert result["known"] == []


# ── 7. reverse round-trip ──────────────────────────────────────────────────

def test_code_to_legacy_tag_round_trips_for_every_seed_row():
    for s in SEED_SKILLS:
        assert code_to_legacy_tag(s["code"]) == s["legacy_tag"]


def test_code_to_legacy_tag_unknown_code_returns_none():
    assert code_to_legacy_tag("not.a.real.code") is None


# ── 8. user isolation ──────────────────────────────────────────────────────

def test_backfill_keeps_pairs_isolated_per_user():
    result = classify_pairs([("user-a", "reading:A"), ("user-b", "reading:A")])
    assert ("user-a", "reading:A") in result["known"]
    assert ("user-b", "reading:A") in result["known"]
    assert len(result["known"]) == 2


def test_reconcile_missing_pairs_are_per_user_not_global():
    report = reconcile(
        source_pairs=[("user-a", "reading:A"), ("user-b", "reading:A")],
        bridge_rows=[{"user_id": "user-a", "skill_tag": "reading:A", "skill_id": _UUID_A}],
        existing_user_ids=["user-a", "user-b"],
        existing_skill_ids=[_UUID_A],
    )
    assert ("user-b", "reading:A") in report["missing_bridge_pairs"]
    assert ("user-a", "reading:A") not in report["missing_bridge_pairs"]


# ── 9. unique(user_id, skill_tag) ──────────────────────────────────────────

def test_migration_declares_unique_user_skill_tag():
    assert "UNIQUE (user_id, skill_tag)" in _MIGRATION_SQL


def test_backfill_upsert_deduplicates_same_user_and_tag():
    fake = _FakeSupabase({"user_skill_stats": [
        {"user_id": "u1", "skill_tag": "reading:A"},
        {"user_id": "u1", "skill_tag": "reading:A"},  # exact duplicate row in source
    ]})
    report = _run(run_backfill(fake))
    assert report["inserted_count"] == 1
    assert len(fake.bridge_rows) == 1


# ── 10. orphan detection (user + skill) ────────────────────────────────────

def test_reconcile_flags_orphan_bridge_user_id():
    report = reconcile(
        source_pairs=[],
        bridge_rows=[{"user_id": "ghost-user", "skill_tag": "reading:A", "skill_id": _UUID_A}],
        existing_user_ids=["some-other-user"],
        existing_skill_ids=[_UUID_A],
    )
    assert report["orphan_bridge_user_ids"] == ["ghost-user"]


def test_reconcile_flags_orphan_bridge_skill_id():
    report = reconcile(
        source_pairs=[],
        bridge_rows=[{"user_id": "u1", "skill_tag": "reading:A", "skill_id": "deleted-skill-id"}],
        existing_user_ids=["u1"],
        existing_skill_ids=[_UUID_A],
    )
    assert report["orphan_bridge_skill_ids"] == ["deleted-skill-id"]


# ── 11. missing bridge detection ───────────────────────────────────────────

def test_reconcile_flags_missing_bridge_pair_for_resolvable_tag():
    report = reconcile(
        source_pairs=[("u1", "reading:A")],
        bridge_rows=[],
        existing_user_ids=["u1"],
        existing_skill_ids=[_UUID_A],
    )
    assert report["missing_bridge_pairs"] == [("u1", "reading:A")]


def test_reconcile_does_not_flag_missing_for_unresolvable_tag():
    # an unknown tag was never supposed to get a bridge row -- not "missing"
    report = reconcile(
        source_pairs=[("u1", "made:up:tag")],
        bridge_rows=[],
        existing_user_ids=["u1"],
        existing_skill_ids=[],
    )
    assert report["missing_bridge_pairs"] == []
    assert report["unknown_legacy_tags"] == ["made:up:tag"]


# ── 12/13. skill_id FK integrity + RESTRICT (skill) vs CASCADE (user) ─────

def test_migration_declares_skill_fk_with_restrict():
    assert "skill_id uuid NOT NULL REFERENCES public.skills(skill_id) ON DELETE RESTRICT" in _MIGRATION_SQL


def test_migration_declares_user_fk_with_cascade():
    assert "user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE" in _MIGRATION_SQL


def test_migration_is_additive_only():
    upper = _MIGRATION_SQL.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE"):
        assert forbidden not in upper
    # the only ALTER TABLE allowed is this table's own RLS enable
    assert _MIGRATION_SQL.count("ALTER TABLE") == 1
    assert "ALTER TABLE public.user_skill_bridge ENABLE ROW LEVEL SECURITY" in _MIGRATION_SQL
    assert "CREATE TABLE IF NOT EXISTS public.user_skill_bridge" in _MIGRATION_SQL


def test_migration_enables_rls_with_no_policies():
    assert "ENABLE ROW LEVEL SECURITY" in _MIGRATION_SQL
    assert "CREATE POLICY" not in _MIGRATION_SQL


# ── 14. skill_graph / Coach / routers stay byte-for-byte untouched ────────

_FORBIDDEN_TOUCH_FILES = [
    "app/services/skill_graph.py",
    "app/services/listening_coach.py",
    "app/services/coach.py",
    "app/services/skill_registry.py",
    "app/services/content_skill_map.py",
]


def test_skill_graph_and_coach_files_do_not_reference_the_new_bridge():
    backend_root = Path(__file__).resolve().parents[1]
    for rel_path in _FORBIDDEN_TOUCH_FILES:
        path = backend_root / rel_path
        if not path.exists():
            continue
        text = path.read_text()
        assert "user_skill_bridge" not in text, f"{rel_path} must not reference user_skill_bridge"
        assert "skill_bridge_resolver" not in text, f"{rel_path} must not reference skill_bridge_resolver"


def test_skill_graph_update_ema_behavior_is_unchanged():
    from app.services.skill_graph import update_ema
    assert update_ema(0.0, 0, 4.0) == 4.0
    assert update_ema(4.0, 1, 5.0) == round(0.3 * 5.0 + 0.7 * 4.0, 2)


# ── 15. content lookup by skill_id (skill_tag -> skill_id -> content_skill_map) ─

def test_get_content_for_skill_walks_bridge_then_content_map():
    fake = _FakeSupabase({
        "content_skill_map": [
            {"skill_id": _UUID_A, "content_type": "listening_section", "content_id": 1},
            {"skill_id": _UUID_B, "content_type": "technique", "content_id": 2},
        ],
    })
    fake.bridge_rows[("u1", "reading:A")] = {"user_id": "u1", "skill_tag": "reading:A", "skill_id": _UUID_A}

    rows = _run(get_content_for_skill(fake, "u1", "reading:A"))
    assert len(rows) == 1
    assert rows[0]["content_id"] == 1


def test_get_content_for_skill_returns_empty_when_user_has_no_bridge_row():
    fake = _FakeSupabase({"content_skill_map": [{"skill_id": _UUID_A, "content_type": "x", "content_id": 1}]})
    rows = _run(get_content_for_skill(fake, "u1", "reading:A"))
    assert rows == []


# ── 16. no writes outside the bridge table ─────────────────────────────────

def test_backfill_never_writes_to_any_table_but_the_bridge():
    fake = _FakeSupabase({"user_skill_stats": [{"user_id": "u1", "skill_tag": "reading:A"}]})
    _run(run_backfill(fake))
    assert set(fake.write_calls) <= {"user_skill_bridge"}


def test_reconciliation_never_writes_anything():
    fake = _FakeSupabase({
        "user_skill_stats": [{"user_id": "u1", "skill_tag": "reading:A"}],
        "users": [{"id": "u1"}],
        "skills": [{"skill_id": _UUID_A}],
    })
    run_live_reconciliation(fake)
    assert fake.write_calls == []


def test_content_lookup_never_writes_anything():
    fake = _FakeSupabase({"content_skill_map": [{"skill_id": _UUID_A, "content_type": "x", "content_id": 1}]})
    fake.bridge_rows[("u1", "reading:A")] = {"user_id": "u1", "skill_tag": "reading:A", "skill_id": _UUID_A}
    _run(get_content_for_skill(fake, "u1", "reading:A"))
    assert fake.write_calls == []
