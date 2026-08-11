import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import seed_micro_practices
from app.services.seed_micro_practices import MICRO_PRACTICES
from app.services.technique_grading import grade_rule_based

_READING_SKILL_TAGS = {"skimming", "scanning", "elimination", "textual_verification"}


def test_covers_exactly_the_four_reading_techniques():
    assert {mp["technique_skill_tag"] for mp in MICRO_PRACTICES} == _READING_SKILL_TAGS


def test_every_micro_practice_is_rule_based():
    assert all(mp["scoring_type"] == "rule_based" for mp in MICRO_PRACTICES)


def test_every_correct_answer_is_one_of_its_own_options():
    # Regression guard: a correct_answer not present in options would make
    # grade_rule_based's exact-match comparator never grade this exercise
    # correct, no matter what the learner picks.
    for mp in MICRO_PRACTICES:
        options = mp["content"]["options"]
        correct = mp["expected_response"]["correct_answer"]
        assert correct in options, mp["title"]


def test_selecting_the_correct_answer_actually_grades_correct():
    for mp in MICRO_PRACTICES:
        result = grade_rule_based(mp["expected_response"], {"answer": mp["expected_response"]["correct_answer"]})
        assert result["feedback"]["is_correct"] is True, mp["title"]
        assert result["score"] == 6.0


def test_selecting_a_wrong_option_grades_incorrect():
    for mp in MICRO_PRACTICES:
        wrong = next(o for o in mp["content"]["options"] if o != mp["expected_response"]["correct_answer"])
        result = grade_rule_based(mp["expected_response"], {"answer": wrong})
        assert result["feedback"]["is_correct"] is False, mp["title"]


class _FakeQuery:
    def __init__(self, rows, on_insert=None):
        self._rows = rows
        self._filters = []
        self._on_insert = on_insert

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def insert(self, row):
        if self._on_insert:
            self._on_insert(row)
        return self

    def execute(self):
        return MagicMock(data=[r for r in self._rows if all(f(r) for f in self._filters)])


def _fake_supabase(techniques, existing_micro_practices, inserted):
    def table(name):
        if name == "techniques":
            return _FakeQuery(techniques)
        if name == "micro_practices":
            return _FakeQuery(existing_micro_practices, on_insert=inserted.append)
        raise AssertionError(f"unexpected table {name!r}")

    supabase = MagicMock()
    supabase.table.side_effect = table
    return supabase


def test_seed_inserts_one_row_per_technique_when_none_exist():
    techniques = [{"id": i + 1, "skill_tag": tag} for i, tag in enumerate(sorted(_READING_SKILL_TAGS))]
    inserted = []
    with patch.object(seed_micro_practices, "get_supabase", return_value=_fake_supabase(techniques, [], inserted)):
        count = seed_micro_practices.seed_micro_practices()
    assert count == len(MICRO_PRACTICES)
    assert len(inserted) == len(MICRO_PRACTICES)


def test_seed_skips_a_title_that_already_exists_for_its_technique():
    techniques = [{"id": i + 1, "skill_tag": tag} for i, tag in enumerate(sorted(_READING_SKILL_TAGS))]
    first = MICRO_PRACTICES[0]
    technique_id = next(t["id"] for t in techniques if t["skill_tag"] == first["technique_skill_tag"])
    existing = [{"id": 999, "technique_id": technique_id, "title": first["title"]}]
    inserted = []
    with patch.object(seed_micro_practices, "get_supabase", return_value=_fake_supabase(techniques, existing, inserted)):
        count = seed_micro_practices.seed_micro_practices()
    assert count == len(MICRO_PRACTICES) - 1
    assert first["title"] not in [row["title"] for row in inserted]


def test_seed_skips_when_no_matching_technique_exists_yet():
    inserted = []
    with patch.object(seed_micro_practices, "get_supabase", return_value=_fake_supabase([], [], inserted)):
        count = seed_micro_practices.seed_micro_practices()
    assert count == 0
    assert inserted == []


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
