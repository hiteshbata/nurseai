import sys
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import seed_techniques
from app.services.seed_techniques import TECHNIQUES

VALID_MODULES = {"reading", "listening", "writing", "speaking"}
VALID_SCORING_TYPES = {"rule_based", "ai"}  # micro_practices only, but slugs/tags below apply to techniques


def test_mvp_catalog_is_the_approved_14():
    assert len(TECHNIQUES) == 14


def test_every_technique_has_a_valid_module():
    assert {t["module"] for t in TECHNIQUES} <= VALID_MODULES


def test_module_distribution_matches_approved_scope():
    counts = Counter(t["module"] for t in TECHNIQUES)
    assert counts == {"reading": 4, "listening": 4, "writing": 3, "speaking": 3}


def test_slugs_are_unique():
    slugs = [t["slug"] for t in TECHNIQUES]
    assert len(slugs) == len(set(slugs))


def test_skill_tags_are_unique():
    tags = [t["skill_tag"] for t in TECHNIQUES]
    assert len(tags) == len(set(tags))


def test_every_technique_has_practical_lesson_content_fields():
    required_keys = {"what", "why", "when", "how", "common_mistakes", "example"}
    for t in TECHNIQUES:
        assert required_keys <= set(t["lesson_content"].keys()), t["slug"]


def _fake_supabase(existing_slugs):
    supabase = MagicMock()

    def table(name):
        m = MagicMock()

        def select(*_a, **_kw):
            sel = MagicMock()

            def eq(_col, value):
                eqm = MagicMock()
                eqm.execute.return_value.data = [{"id": 1}] if value in existing_slugs else []
                return eqm

            sel.eq.side_effect = eq
            return sel

        m.select.side_effect = select
        m.insert.return_value.execute.return_value = MagicMock()
        return m

    supabase.table.side_effect = table
    return supabase


def test_seed_skips_techniques_that_already_exist_by_slug():
    existing = {TECHNIQUES[0]["slug"]}
    fake = _fake_supabase(existing)
    with patch.object(seed_techniques, "get_supabase", return_value=fake):
        inserted = seed_techniques.seed_techniques()
    assert inserted == len(TECHNIQUES) - 1


def test_seed_is_a_full_no_op_when_every_slug_already_exists():
    existing = {t["slug"] for t in TECHNIQUES}
    fake = _fake_supabase(existing)
    with patch.object(seed_techniques, "get_supabase", return_value=fake):
        inserted = seed_techniques.seed_techniques()
    assert inserted == 0
