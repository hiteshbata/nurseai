from collections import Counter
from pathlib import Path

from app.services.skill_registry import (
    LEGACY_TAG_TO_CODE,
    SEED_SKILLS,
    VALID_KINDS,
    VALID_MODULES,
)
from app.services.skill_registry_reconciliation import reconcile


def test_exact_seed_row_count_is_44():
    assert len(SEED_SKILLS) == 44


def test_codes_are_unique():
    codes = [s["code"] for s in SEED_SKILLS]
    assert len(codes) == len(set(codes))


def test_legacy_tags_are_unique():
    tags = [s["legacy_tag"] for s in SEED_SKILLS]
    assert len(tags) == len(set(tags))


def test_every_seed_has_a_valid_module():
    assert {s["module"] for s in SEED_SKILLS} <= VALID_MODULES


def test_every_seed_has_a_valid_kind():
    assert {s["kind"] for s in SEED_SKILLS} <= VALID_KINDS


def test_kind_distribution_matches_inventory():
    counts = Counter(s["kind"] for s in SEED_SKILLS)
    assert counts == {
        "part": 6,                  # reading A/B/C + listening A/B/C
        "comprehension_skill": 6,   # reading:skill:*
        "criterion": 18,            # speaking 3-mode (3) + 9-mode (9) + writing (6)
        "technique": 14,            # seed_techniques.TECHNIQUES
    }


def test_parent_skill_id_not_populated_yet():
    # E2.4.3's job, not this phase's -- every seed row must stay unparented.
    assert all("parent_skill_id" not in s for s in SEED_SKILLS)


def test_speaking_3mode_and_9mode_families_are_not_merged():
    speaking_codes = {s["code"] for s in SEED_SKILLS if s["module"] == "speaking" and s["kind"] == "criterion"}
    three_mode = {"speaking.criterion.clinical_communication", "speaking.criterion.linguistic_delivery", "speaking.criterion.relationship_building"}
    nine_mode = {
        "speaking.criterion.empathy", "speaking.criterion.patient_perspective", "speaking.criterion.providing_structure",
        "speaking.criterion.information_gathering", "speaking.criterion.information_giving", "speaking.criterion.intelligibility",
        "speaking.criterion.fluency", "speaking.criterion.appropriateness_of_language", "speaking.criterion.grammar",
    }
    assert three_mode <= speaking_codes
    assert nine_mode <= speaking_codes
    assert three_mode.isdisjoint(nine_mode)
    assert speaking_codes == three_mode | nine_mode


def test_reading_skill_scanning_and_technique_scanning_stay_distinct():
    assert "reading.skill.scanning" in {s["code"] for s in SEED_SKILLS}
    assert "technique.scanning" in {s["code"] for s in SEED_SKILLS}
    assert LEGACY_TAG_TO_CODE["reading:skill:scanning"] != LEGACY_TAG_TO_CODE["technique:scanning"]


def test_legacy_tag_to_code_covers_every_seed_row():
    assert len(LEGACY_TAG_TO_CODE) == len(SEED_SKILLS)


# ── reconciliation ───────────────────────────────────────────────────────

def test_reconciliation_flags_a_known_tag():
    report = reconcile(["reading:A"])
    assert report["known"] == ["reading:A"]
    assert report["missing"] == []


def test_reconciliation_flags_an_unknown_tag_as_missing():
    report = reconcile(["reading:A", "reading:not_a_real_tag"])
    assert "reading:not_a_real_tag" in report["missing"]
    assert "reading:A" not in report["missing"]


def test_reconciliation_flags_unused_registry_entries():
    # Only one tag observed -- every other one of the 44 registered codes is unused.
    report = reconcile(["reading:A"])
    assert len(report["unused"]) == len(SEED_SKILLS) - 1
    assert "reading.part.a" not in report["unused"]


def test_reconciliation_is_read_only_pure_function():
    # No supabase/network argument accepted -- it only ever transforms the
    # tag list it's given.
    import inspect
    params = list(inspect.signature(reconcile).parameters)
    assert params == ["observed_tags"]


# ── migration DDL: no live Postgres in this test suite (see
# test_skill_graph.py's fake-supabase convention), so the schema-level
# guarantees are checked statically against the migration's SQL text. ────

_MIGRATION_SQL = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260821000000_skill_registry.sql"
).read_text()


def test_migration_declares_code_as_unique():
    assert "code text NOT NULL UNIQUE" in _MIGRATION_SQL


def test_migration_declares_parent_skill_id_as_self_referencing_fk():
    assert "parent_skill_id uuid REFERENCES public.skills(skill_id)" in _MIGRATION_SQL


def test_migration_leaves_parent_skill_id_nullable():
    # Nullable means no "NOT NULL" immediately after the column's type.
    assert "parent_skill_id uuid REFERENCES public.skills(skill_id) NOT NULL" not in _MIGRATION_SQL


def test_migration_seeds_no_parent_skill_id_values():
    # E2.4.3's job -- this phase's INSERT must never populate the column.
    assert "parent_skill_id" not in _MIGRATION_SQL.split("INSERT INTO", 1)[1]


def test_migration_does_not_alter_existing_learner_state_tables():
    for forbidden in ("ALTER TABLE public.user_skill_stats", "ALTER TABLE public.skill_observations",
                       "ALTER TABLE public.listening_mistake_events", "ALTER TABLE public.techniques"):
        assert forbidden not in _MIGRATION_SQL


def test_migration_has_no_destructive_statements():
    upper = _MIGRATION_SQL.upper()
    assert "DROP TABLE" not in upper
    assert "DROP COLUMN" not in upper
    assert "DELETE FROM" not in upper
    assert "TRUNCATE" not in upper
