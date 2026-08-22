import asyncio
from pathlib import Path

import pytest

from app.services.content_skill_map import (
    ALLOWED_CONTENT_TYPES,
    ALLOWED_RELATIONSHIP_TYPES,
    ALLOWED_SOURCES,
    add_mapping,
)
from app.services.content_skill_map_reconciliation import find_orphans, run_live_reconciliation

_MIGRATION_SQL = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260822000000_content_skill_map.sql"
).read_text()

# Comment lines (prose explaining what the migration deliberately does NOT
# do) legitimately mention forbidden table/column names -- only the
# executable SQL should be checked against them.
_MIGRATION_SQL_CODE_ONLY = "\n".join(
    line for line in _MIGRATION_SQL.splitlines() if not line.strip().startswith("--")
)


# ── fake supabase (see test_auth_role_preservation.py's upsert-dedup convention) ──

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, rows_by_key):
        self._rows = rows_by_key  # dict[tuple, dict], keyed by the unique constraint

    def upsert(self, row, on_conflict=None):
        key = (row["skill_id"], row["content_type"], row["content_id"], row["relationship_type"])
        self._rows[key] = dict(row)  # ON CONFLICT DO NOTHING/UPDATE -- same key, one row survives
        return _FakeExecute([self._rows[key]])

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        return _FakeResult(list(self._rows.values()))


class _FakeExecute:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _FakeResult(self._data)


class _FakeSupabase:
    def __init__(self):
        self.rows_by_key = {}

    def table(self, _name):
        return _FakeTable(self.rows_by_key)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── schema: unique constraint, FK/RESTRICT, CHECK constraints ────────────

def test_migration_declares_unique_constraint_on_all_four_columns():
    assert "UNIQUE (skill_id, content_type, content_id, relationship_type)" in _MIGRATION_SQL


def test_migration_declares_skill_fk_with_restrict():
    assert "REFERENCES public.skills(skill_id) ON DELETE RESTRICT" in _MIGRATION_SQL


def test_migration_declares_relationship_type_check():
    assert "relationship_type text NOT NULL CHECK (relationship_type IN ('teaches', 'practices'))" in _MIGRATION_SQL


def test_migration_declares_source_check():
    assert "source text NOT NULL CHECK (source IN ('manual', 'heuristic:part'))" in _MIGRATION_SQL


def test_migration_only_creates_one_new_table():
    assert _MIGRATION_SQL.count("CREATE TABLE") == 1
    assert "CREATE TABLE IF NOT EXISTS public.content_skill_map" in _MIGRATION_SQL


def test_migration_is_idempotent_ddl():
    assert "CREATE TABLE IF NOT EXISTS" in _MIGRATION_SQL
    assert "CREATE INDEX IF NOT EXISTS" in _MIGRATION_SQL
    assert _MIGRATION_SQL.count("ON CONFLICT") == _MIGRATION_SQL.count("INSERT INTO")


def test_migration_has_no_destructive_statements():
    upper = _MIGRATION_SQL.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE"):
        assert forbidden not in upper


# ── legacy skill_tag + Coach/Learner Brain untouched ──────────────────────

def test_migration_does_not_alter_any_existing_table():
    assert "ALTER TABLE public.techniques" not in _MIGRATION_SQL
    assert "ALTER TABLE public.micro_practices" not in _MIGRATION_SQL
    assert "ALTER TABLE public.listening_sections" not in _MIGRATION_SQL
    assert "ALTER TABLE public.skills" not in _MIGRATION_SQL


def test_migration_does_not_touch_learner_state_tables():
    for forbidden in ("user_skill_stats", "skill_observations", "listening_mistake_events"):
        assert forbidden not in _MIGRATION_SQL_CODE_ONLY


def test_migration_never_writes_to_skill_tag_column():
    assert "skill_tag =" not in _MIGRATION_SQL
    assert "UPDATE public.techniques" not in _MIGRATION_SQL


# ── backfill logic (static: no live Postgres in this suite, see
# test_skill_registry.py's convention) ────────────────────────────────────

def test_listening_part_backfill_joins_on_lowercased_part_letter():
    assert "'listening.part.' || lower(ls.part)" in _MIGRATION_SQL
    assert "FROM public.listening_sections ls" in _MIGRATION_SQL


def test_technique_backfill_joins_on_skill_tag():
    assert "'technique.' || t.skill_tag" in _MIGRATION_SQL
    assert "FROM public.techniques t" in _MIGRATION_SQL


def test_micro_practice_backfill_inherits_from_technique_mapping_not_skill_tag():
    # Must join through content_skill_map (the technique's own mapping),
    # not recompute a skill_tag lookup directly against techniques -- that
    # would be a second source of truth for the same relationship.
    mp_section = _MIGRATION_SQL.split("micro_practices inherit")[1]
    assert "csm.content_type = 'technique'" in mp_section
    assert "csm.content_id = mp.technique_id" in mp_section
    assert "t.skill_tag" not in mp_section


def test_no_backfill_infers_skill_from_question_type():
    assert "question.type" not in _MIGRATION_SQL_CODE_ONLY
    assert "questions" not in _MIGRATION_SQL_CODE_ONLY  # no auto-tagging touches the questions table at all


# ── service layer: validation ─────────────────────────────────────────────

def test_content_types_match_approved_scope():
    assert ALLOWED_CONTENT_TYPES == {"listening_section", "listening_question", "technique", "micro_practice"}


def test_relationship_types_match_schema():
    assert ALLOWED_RELATIONSHIP_TYPES == {"teaches", "practices"}


def test_sources_match_schema():
    assert ALLOWED_SOURCES == {"manual", "heuristic:part"}


def test_add_mapping_rejects_unsupported_content_type():
    fake = _FakeSupabase()
    with pytest.raises(ValueError):
        _run(add_mapping(fake, "skill-1", "reading_question", 1, "teaches", "manual"))


def test_add_mapping_rejects_unsupported_relationship_type():
    fake = _FakeSupabase()
    with pytest.raises(ValueError):
        _run(add_mapping(fake, "skill-1", "listening_question", 1, "explains", "manual"))


def test_add_mapping_rejects_unsupported_source():
    fake = _FakeSupabase()
    with pytest.raises(ValueError):
        _run(add_mapping(fake, "skill-1", "listening_question", 1, "teaches", "guessed"))


# ── many-to-many + no duplicate mapping ───────────────────────────────────

def test_many_to_many_same_content_maps_to_multiple_skills():
    fake = _FakeSupabase()
    _run(add_mapping(fake, "skill-a", "listening_question", 7, "teaches", "manual"))
    _run(add_mapping(fake, "skill-b", "listening_question", 7, "teaches", "manual"))
    assert len(fake.rows_by_key) == 2


def test_many_to_many_same_skill_maps_to_multiple_content_rows():
    fake = _FakeSupabase()
    _run(add_mapping(fake, "skill-a", "listening_question", 7, "teaches", "manual"))
    _run(add_mapping(fake, "skill-a", "listening_question", 8, "teaches", "manual"))
    assert len(fake.rows_by_key) == 2


def test_duplicate_mapping_does_not_create_a_second_row():
    fake = _FakeSupabase()
    _run(add_mapping(fake, "skill-a", "listening_question", 7, "teaches", "manual"))
    _run(add_mapping(fake, "skill-a", "listening_question", 7, "teaches", "manual"))
    assert len(fake.rows_by_key) == 1


def test_same_content_same_skill_different_relationship_type_is_a_distinct_row():
    # e.g. a technique's own row could plausibly be both taught and practiced --
    # relationship_type is part of the uniqueness key on purpose.
    fake = _FakeSupabase()
    _run(add_mapping(fake, "skill-a", "technique", 3, "teaches", "manual"))
    _run(add_mapping(fake, "skill-a", "technique", 3, "practices", "manual"))
    assert len(fake.rows_by_key) == 2


# ── orphan detection ───────────────────────────────────────────────────────

def test_find_orphans_flags_dangling_skill_id():
    report = find_orphans(
        mappings=[{"skill_id": "gone", "content_type": "technique", "content_id": 1}],
        existing_skill_ids=["s1"],
        existing_content_ids={"technique": {1}},
    )
    assert len(report["orphaned_skill"]) == 1
    assert report["orphaned_content"] == []
    assert report["clean_count"] == 0


def test_find_orphans_flags_dangling_content_id():
    report = find_orphans(
        mappings=[{"skill_id": "s1", "content_type": "technique", "content_id": 999}],
        existing_skill_ids=["s1"],
        existing_content_ids={"technique": {1}},
    )
    assert report["orphaned_skill"] == []
    assert len(report["orphaned_content"]) == 1
    assert report["clean_count"] == 0


def test_find_orphans_leaves_clean_mappings_alone():
    report = find_orphans(
        mappings=[{"skill_id": "s1", "content_type": "technique", "content_id": 1}],
        existing_skill_ids=["s1"],
        existing_content_ids={"technique": {1}},
    )
    assert report["orphaned_skill"] == []
    assert report["orphaned_content"] == []
    assert report["clean_count"] == 1


def test_find_orphans_is_pure_no_supabase_argument():
    import inspect
    params = list(inspect.signature(find_orphans).parameters)
    assert params == ["mappings", "existing_skill_ids", "existing_content_ids"]


def test_run_live_reconciliation_queries_content_skill_map_and_skills_and_content_tables():
    class _Query:
        def __init__(self, data):
            self._data = data

        def select(self, *a, **k):
            return self

        def execute(self):
            return _FakeResult(self._data)

    class _Supa:
        def __init__(self):
            self.calls = []

        def table(self, name):
            self.calls.append(name)
            if name == "content_skill_map":
                return _Query([{"skill_id": "s1", "content_type": "technique", "content_id": 1}])
            if name == "skills":
                return _Query([{"skill_id": "s1"}])
            if name == "techniques":
                return _Query([{"id": 1}])
            return _Query([])

    supa = _Supa()
    report = run_live_reconciliation(supa)
    assert report["clean_count"] == 1
    assert "content_skill_map" in supa.calls
    assert "skills" in supa.calls
    assert "techniques" in supa.calls
