from pathlib import Path

from app.services.skill_relationship_reconciliation import (
    VALID_RELATIONSHIP_TYPES,
    VALID_SOURCES,
    find_cycles,
    find_parent_cycles,
    find_relationship_issues,
    run_live_reconciliation,
    would_create_cycle,
)

_MIGRATION_SQL = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260822010000_skill_relationships.sql"
).read_text()

_SKILL_REGISTRY_SQL = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260821000000_skill_registry.sql"
).read_text()

_CONTENT_SKILL_MAP_SQL = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260822000000_content_skill_map.sql"
).read_text()

# Comment lines legitimately mention forbidden names while explaining what's
# deliberately excluded -- only executable SQL should be checked.
_MIGRATION_SQL_CODE_ONLY = "\n".join(
    line for line in _MIGRATION_SQL.splitlines() if not line.strip().startswith("--")
)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *a, **k):
        return self

    def execute(self):
        return _FakeResult(self._data)


class _FakeSupabase:
    def __init__(self, tables):
        self._tables = tables
        self.calls = []

    def table(self, name):
        self.calls.append(name)
        return _FakeQuery(self._tables.get(name, []))


# ── schema ─────────────────────────────────────────────────────────────

def test_migration_only_creates_one_new_table():
    assert _MIGRATION_SQL.count("CREATE TABLE") == 1
    assert "CREATE TABLE IF NOT EXISTS public.skill_relationships" in _MIGRATION_SQL


def test_migration_declares_expected_columns():
    assert "id bigserial PRIMARY KEY" in _MIGRATION_SQL
    assert "source_skill_id uuid NOT NULL REFERENCES public.skills(skill_id) ON DELETE RESTRICT" in _MIGRATION_SQL
    assert "target_skill_id uuid NOT NULL REFERENCES public.skills(skill_id) ON DELETE RESTRICT" in _MIGRATION_SQL
    assert "weight real NULL" in _MIGRATION_SQL
    assert "created_by uuid NULL" in _MIGRATION_SQL
    assert "created_at timestamptz NOT NULL DEFAULT now()" in _MIGRATION_SQL


def test_migration_declares_relationship_type_check():
    assert (
        "relationship_type text NOT NULL CHECK (relationship_type IN "
        "('assesses', 'trains_toward', 'rolls_up_into', 'prerequisite_of'))"
    ) in _MIGRATION_SQL


def test_migration_declares_source_check():
    assert "source text NOT NULL CHECK (source IN ('manual', 'heuristic:code_evidence'))" in _MIGRATION_SQL


def test_migration_rejects_source_equals_target():
    assert "CHECK (source_skill_id <> target_skill_id)" in _MIGRATION_SQL


def test_migration_declares_unique_constraint():
    assert "UNIQUE (source_skill_id, target_skill_id, relationship_type)" in _MIGRATION_SQL


def test_migration_declares_both_indexes():
    assert "skill_relationships_source_skill_id_idx ON public.skill_relationships (source_skill_id)" in _MIGRATION_SQL
    assert "skill_relationships_target_skill_id_idx ON public.skill_relationships (target_skill_id)" in _MIGRATION_SQL


def test_migration_enables_rls_with_zero_policies():
    assert "ALTER TABLE public.skill_relationships ENABLE ROW LEVEL SECURITY" in _MIGRATION_SQL
    assert "CREATE POLICY" not in _MIGRATION_SQL


def test_migration_is_idempotent_ddl():
    assert "CREATE TABLE IF NOT EXISTS" in _MIGRATION_SQL
    assert "CREATE INDEX IF NOT EXISTS" in _MIGRATION_SQL
    assert _MIGRATION_SQL.count("ON CONFLICT") == _MIGRATION_SQL.count("INSERT INTO")


def test_migration_has_no_destructive_statements():
    upper = _MIGRATION_SQL.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE"):
        assert forbidden not in upper


def test_migration_does_not_alter_any_existing_table():
    assert "ALTER TABLE public.skills " not in _MIGRATION_SQL
    assert "ALTER TABLE public.content_skill_map" not in _MIGRATION_SQL
    assert "ALTER TABLE public.techniques" not in _MIGRATION_SQL


def test_migration_does_not_touch_learner_state_tables():
    for forbidden in ("user_skill_stats", "skill_observations", "listening_mistake_events"):
        assert forbidden not in _MIGRATION_SQL_CODE_ONLY


def test_migration_never_populates_parent_skill_id():
    assert "parent_skill_id" not in _MIGRATION_SQL


# ── seed content: exact evidence-backed edges only ────────────────────────

_INSERT_MARKER = "INSERT INTO public.skill_relationships (source_skill_id, target_skill_id, relationship_type, source)"
_INSERT_BLOCKS = _MIGRATION_SQL.split(_INSERT_MARKER)


def test_no_prerequisite_rows_seeded():
    for block in _INSERT_BLOCKS[1:]:
        assert "'prerequisite_of'" not in block


def test_seeds_exactly_three_insert_blocks():
    assert _MIGRATION_SQL.count(_INSERT_MARKER) == 3
    assert len(_INSERT_BLOCKS) == 4  # preamble + 3 insert bodies


def test_reading_part_a_assesses_scanning_and_detail():
    section = _INSERT_BLOCKS[1]
    assert "p.code = 'reading.part.a'" in section
    assert "'reading.skill.scanning', 'reading.skill.detail'" in section


def test_reading_part_b_and_c_assess_five_evidenced_skills_not_scanning():
    section = _INSERT_BLOCKS[2]
    assert "'reading.part.b', 'reading.part.c'" in section
    for code in (
        "reading.skill.detail", "reading.skill.inference", "reading.skill.vocabulary",
        "reading.skill.main_idea", "reading.skill.writer_view",
    ):
        assert code in section
    # scanning is Part-A only in reading_skills.classify_reading_skill() --
    # must not be seeded for B/C without code evidence.
    assert "reading.skill.scanning" not in section


def test_speaking_empathy_rolls_up_into_relationship_building():
    section = _INSERT_BLOCKS[3]
    assert "e.code = 'speaking.criterion.empathy'" in section
    assert "r.code = 'speaking.criterion.relationship_building'" in section
    assert "'rolls_up_into'" in section


def test_no_technique_trains_toward_reading_skill_edges_seeded():
    # No code path links a technique's skill_tag to a reading.skill.* code
    # (technique_skill_tag() only prefixes the technique's own tag) -- a
    # shared English name (e.g. technique.scanning / reading.skill.scanning)
    # is not evidence, so this relationship type must not appear in any seed row.
    for block in _INSERT_BLOCKS[1:]:
        assert "'trains_toward'" not in block


def test_all_seed_sources_are_code_evidence():
    # Every seeded row in this migration is code-derived, never 'manual'.
    for block in _INSERT_BLOCKS[1:]:
        assert "'manual'" not in block


# ── unaffected files stay untouched ────────────────────────────────────────

def test_skill_registry_migration_untouched_by_this_phase():
    assert "skill_relationships" not in _SKILL_REGISTRY_SQL


def test_content_skill_map_migration_untouched_by_this_phase():
    assert "skill_relationships" not in _CONTENT_SKILL_MAP_SQL


def test_skill_graph_module_not_imported_by_reconciliation():
    import app.services.skill_relationship_reconciliation as mod
    import inspect
    source = inspect.getsource(mod)
    assert "skill_graph" not in source


# ── service layer: constants ──────────────────────────────────────────────

def test_relationship_types_match_schema():
    assert VALID_RELATIONSHIP_TYPES == {"assesses", "trains_toward", "rolls_up_into", "prerequisite_of"}


def test_sources_match_schema():
    assert VALID_SOURCES == {"manual", "heuristic:code_evidence"}


# ── reconciliation: orphans / invalid type / self-loop / duplicate ────────

def test_find_relationship_issues_flags_orphaned_source():
    report = find_relationship_issues(
        relationships=[{"source_skill_id": "gone", "target_skill_id": "b", "relationship_type": "assesses"}],
        existing_skill_ids=["b"],
    )
    assert len(report["orphaned_source"]) == 1
    assert report["clean_count"] == 0


def test_find_relationship_issues_flags_orphaned_target():
    report = find_relationship_issues(
        relationships=[{"source_skill_id": "a", "target_skill_id": "gone", "relationship_type": "assesses"}],
        existing_skill_ids=["a"],
    )
    assert len(report["orphaned_target"]) == 1
    assert report["clean_count"] == 0


def test_find_relationship_issues_flags_invalid_type():
    report = find_relationship_issues(
        relationships=[{"source_skill_id": "a", "target_skill_id": "b", "relationship_type": "explains"}],
        existing_skill_ids=["a", "b"],
    )
    assert len(report["invalid_type"]) == 1


def test_find_relationship_issues_flags_self_loop():
    report = find_relationship_issues(
        relationships=[{"source_skill_id": "a", "target_skill_id": "a", "relationship_type": "assesses"}],
        existing_skill_ids=["a"],
    )
    assert len(report["self_loops"]) == 1


def test_find_relationship_issues_flags_duplicates():
    row = {"source_skill_id": "a", "target_skill_id": "b", "relationship_type": "assesses"}
    report = find_relationship_issues(relationships=[row, dict(row)], existing_skill_ids=["a", "b"])
    assert len(report["duplicates"]) == 1
    assert report["clean_count"] == 1


def test_find_relationship_issues_directionality_a_to_b_is_not_b_to_a():
    # Two rows with source/target swapped are NOT duplicates of each other.
    report = find_relationship_issues(
        relationships=[
            {"source_skill_id": "a", "target_skill_id": "b", "relationship_type": "assesses"},
            {"source_skill_id": "b", "target_skill_id": "a", "relationship_type": "assesses"},
        ],
        existing_skill_ids=["a", "b"],
    )
    assert report["duplicates"] == []
    assert report["clean_count"] == 2


def test_find_relationship_issues_clean_state_has_no_findings():
    report = find_relationship_issues(
        relationships=[{"source_skill_id": "a", "target_skill_id": "b", "relationship_type": "assesses"}],
        existing_skill_ids=["a", "b"],
    )
    assert report["orphaned_source"] == []
    assert report["orphaned_target"] == []
    assert report["invalid_type"] == []
    assert report["self_loops"] == []
    assert report["duplicates"] == []
    assert report["prerequisite_cycles"] == []
    assert report["clean_count"] == 1


def test_find_relationship_issues_is_pure_no_supabase_argument():
    import inspect
    params = list(inspect.signature(find_relationship_issues).parameters)
    assert params == ["relationships", "existing_skill_ids"]


# ── prerequisite / parent cycle detection ──────────────────────────────────

def test_find_cycles_detects_a_simple_cycle():
    cycles = find_cycles([("x", "y"), ("y", "x")])
    assert len(cycles) == 1


def test_find_cycles_detects_no_cycle_in_a_dag():
    assert find_cycles([("x", "y"), ("y", "z")]) == []


def test_find_relationship_issues_detects_prerequisite_cycle():
    report = find_relationship_issues(
        relationships=[
            {"source_skill_id": "a", "target_skill_id": "b", "relationship_type": "prerequisite_of"},
            {"source_skill_id": "b", "target_skill_id": "a", "relationship_type": "prerequisite_of"},
        ],
        existing_skill_ids=["a", "b"],
    )
    assert len(report["prerequisite_cycles"]) == 1


def test_find_parent_cycles_detects_a_cycle():
    cycles = find_parent_cycles([
        {"skill_id": "a", "parent_skill_id": "b"},
        {"skill_id": "b", "parent_skill_id": "a"},
    ])
    assert len(cycles) == 1


def test_find_parent_cycles_ignores_rows_without_a_parent():
    assert find_parent_cycles([{"skill_id": "a", "parent_skill_id": None}]) == []


def test_would_create_cycle_true_when_a_path_back_already_exists():
    assert would_create_cycle([("x", "y"), ("y", "z")], ("z", "x")) is True


def test_would_create_cycle_false_when_no_path_back():
    assert would_create_cycle([("x", "y")], ("y", "z")) is False


def test_would_create_cycle_true_for_self_edge():
    assert would_create_cycle([], ("x", "x")) is True


# ── live reconciliation wrapper ────────────────────────────────────────────

def test_run_live_reconciliation_queries_skill_relationships_and_skills():
    supa = _FakeSupabase({
        "skill_relationships": [{"source_skill_id": "a", "target_skill_id": "b", "relationship_type": "assesses"}],
        "skills": [{"skill_id": "a"}, {"skill_id": "b"}],
    })
    report = run_live_reconciliation(supa)
    assert report["clean_count"] == 1
    assert "skill_relationships" in supa.calls
    assert "skills" in supa.calls


def test_run_live_reconciliation_is_read_only():
    supa = _FakeSupabase({"skill_relationships": [], "skills": []})
    assert not hasattr(supa, "insert")
    assert not hasattr(supa, "upsert")
    run_live_reconciliation(supa)
