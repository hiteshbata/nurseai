import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services import technique_progress


def test_technique_skill_tag_format():
    assert technique_progress.technique_skill_tag("skimming") == "technique:skimming"


class RecordTechniqueProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_writes_exactly_one_technique_tagged_observation(self):
        with patch.object(technique_progress.skill_graph, "record_skill_observations", new=AsyncMock()) as record_mock, \
             patch.object(technique_progress, "run_sync", new=AsyncMock()):
            await technique_progress.record_technique_progress("user-1", "skimming", 4.5)

        record_mock.assert_called_once_with("user-1", {"technique:skimming": 4.5})

    async def test_logs_raw_observation_with_source_module(self):
        insert_calls = []

        def fake_log_sync(user_id, tag, score):
            insert_calls.append((user_id, tag, score))

        with patch.object(technique_progress.skill_graph, "record_skill_observations", new=AsyncMock()), \
             patch.object(technique_progress, "run_sync", new=AsyncMock(side_effect=lambda fn, *a: fn(*a))), \
             patch.object(technique_progress, "_log_observation_sync", side_effect=fake_log_sync):
            await technique_progress.record_technique_progress("user-1", "scanning", 3.0)

        assert insert_calls == [("user-1", "technique:scanning", 3.0)]

    async def test_score_none_is_a_silent_no_op(self):
        with patch.object(technique_progress.skill_graph, "record_skill_observations", new=AsyncMock()) as record_mock:
            await technique_progress.record_technique_progress("user-1", "skimming", None)
        record_mock.assert_not_called()

    async def test_out_of_range_score_is_rejected(self):
        with patch.object(technique_progress.skill_graph, "record_skill_observations", new=AsyncMock()) as record_mock:
            await technique_progress.record_technique_progress("user-1", "skimming", 6.5)
            await technique_progress.record_technique_progress("user-1", "skimming", -1)
        record_mock.assert_not_called()

    async def test_non_numeric_score_is_rejected_not_raised(self):
        # Regression: an AI that returns "score" as non-numeric text despite
        # instructions must not crash the caller's submit request.
        with patch.object(technique_progress.skill_graph, "record_skill_observations", new=AsyncMock()) as record_mock, \
             patch.object(technique_progress, "run_sync", new=AsyncMock()) as run_sync_mock:
            await technique_progress.record_technique_progress("user-1", "skimming", "excellent")  # must not raise
        record_mock.assert_not_called()
        run_sync_mock.assert_not_called()

    async def test_numeric_string_score_is_accepted_like_a_real_number(self):
        # float("4.5") coerces cleanly -- a numeric string isn't the bug,
        # only genuinely non-numeric text is.
        with patch.object(technique_progress.skill_graph, "record_skill_observations", new=AsyncMock()) as record_mock, \
             patch.object(technique_progress, "run_sync", new=AsyncMock()):
            await technique_progress.record_technique_progress("user-1", "skimming", "4.5")
        record_mock.assert_called_once_with("user-1", {"technique:skimming": 4.5})

    async def test_bool_score_is_rejected_not_coerced_to_one_or_zero(self):
        with patch.object(technique_progress.skill_graph, "record_skill_observations", new=AsyncMock()) as record_mock:
            await technique_progress.record_technique_progress("user-1", "skimming", True)
        record_mock.assert_not_called()

    async def test_a_failed_observation_log_never_raises_or_blocks(self):
        with patch.object(technique_progress.skill_graph, "record_skill_observations", new=AsyncMock()), \
             patch.object(technique_progress, "run_sync", new=AsyncMock(side_effect=Exception("table missing"))):
            await technique_progress.record_technique_progress("user-1", "skimming", 4.0)  # must not raise

    async def test_does_not_touch_an_unrelated_skill_tag(self):
        with patch.object(technique_progress.skill_graph, "record_skill_observations", new=AsyncMock()) as record_mock, \
             patch.object(technique_progress, "run_sync", new=AsyncMock()):
            await technique_progress.record_technique_progress("user-1", "empathy_validation", 5.0)

        tag_scores = record_mock.call_args.args[1]
        assert list(tag_scores.keys()) == ["technique:empathy_validation"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
