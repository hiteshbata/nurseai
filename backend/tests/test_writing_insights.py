"""
Tests for Adaptive Writing V1 (Sprint 4): app.routers.writing.normalize_writing_score,
_writing_skill_label and _build_writing_insights. Ported locally from Reading's
Sprint 2 pattern (app.routers.reading._reading_skill_label / _build_reading_insights)
rather than a shared service -- see _build_writing_insights's docstring.

_build_writing_insights delegates scenario picking to the existing
_recommend_writing_scenarios and weakness history to the existing get_weakness
(neither changed here) -- these tests monkeypatch those two collaborators
rather than re-testing them.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import app.routers.writing as writing_router


class FakeUser:
    def __init__(self, user_id):
        self.id = user_id


def _patch_recommend(monkeypatch, recs):
    monkeypatch.setattr(writing_router, "_recommend_writing_scenarios", lambda current_user, user_db, limit: recs)


def _patch_history(monkeypatch, history):
    async def _fake_get_weakness(user_db, user_id, tag_prefix, label_fn=None):
        return history
    monkeypatch.setattr(writing_router, "get_weakness", _fake_get_weakness)


# ── normalize_writing_score ────────────────────────────────────────────

def test_normalize_writing_score_rescales_purpose_0_to_3():
    assert writing_router.normalize_writing_score(2, 3) == 4.0


def test_normalize_writing_score_rescales_7_max_criteria():
    assert writing_router.normalize_writing_score(5, 7) == 4.29


def test_normalize_writing_score_full_marks_hits_band_ceiling_regardless_of_max():
    assert writing_router.normalize_writing_score(3, 3) == 6.0
    assert writing_router.normalize_writing_score(7, 7) == 6.0


def test_normalize_writing_score_zero_is_zero():
    assert writing_router.normalize_writing_score(0, 3) == 0.0
    assert writing_router.normalize_writing_score(0, 7) == 0.0


# ── _writing_skill_label ────────────────────────────────────────────────

def test_writing_skill_label_uses_existing_criteria_labels():
    assert writing_router._writing_skill_label("writing:genre_style") == "Genre & Style"
    assert writing_router._writing_skill_label("writing:organization") == "Organisation & Layout"


def test_writing_skill_label_falls_back_for_unknown_tag():
    # Writing tags use underscores (genre_style, not genre-style), unlike Reading's
    # hyphenated skill tags -- the fallback replaces "_", matching Speaking's convention.
    assert writing_router._writing_skill_label("writing:made_up") == "Made Up"


# ── _build_writing_insights ──────────────────────────────────────────────

def test_build_writing_insights_returns_none_without_scores():
    result = asyncio.run(writing_router._build_writing_insights({}, current_user=None, user_db=None))
    assert result is None


def test_build_writing_insights_falls_back_to_session_when_no_history(monkeypatch):
    _patch_history(monkeypatch, [])
    _patch_recommend(monkeypatch, [{"scenario_id": 7, "title": "Discharge Letter", "reason": "Needs practice"}])

    insights = asyncio.run(writing_router._build_writing_insights(
        {"writing:purpose": 2.0, "writing:content": 5.0, "writing:language": 4.0},
        current_user=FakeUser("user-1"),
        user_db=None,
    ))

    assert insights["based_on"] == "session"
    assert insights["weakest_skill"]["tag"] == "writing:purpose"
    assert insights["weakest_skill"]["score"] == 2.0
    assert insights["strongest_skill"]["tag"] == "writing:content"
    assert insights["next_best_action"]["scenario_id"] == 7
    assert "today" in insights["recommendation_reason"]
    assert insights["weakest_skill"]["label"] in insights["actionable_improvement"]
    assert "today's session" in insights["confidence_message"]


def test_build_writing_insights_prefers_learner_history_over_session(monkeypatch):
    # Session's own worst criterion is purpose, but history says language is the
    # real, recurring weak spot -- the recommendation should follow history.
    _patch_history(monkeypatch, [{"skill": "language", "label": "Language", "band": 2.5, "attempts": 5}])
    _patch_recommend(monkeypatch, [{"scenario_id": 3, "title": "Referral Letter", "reason": "Needs practice"}])

    insights = asyncio.run(writing_router._build_writing_insights(
        {"writing:purpose": 3.0, "writing:language": 4.0, "writing:content": 5.0},
        current_user=FakeUser("user-1"),
        user_db=None,
    ))

    assert insights["based_on"] == "history"
    assert insights["weakest_skill"] == {"tag": "writing:language", "label": "Language", "score": 2.5}
    assert "recent sessions" in insights["recommendation_reason"]
    assert "5" in insights["confidence_message"]


def test_build_writing_insights_degrades_gracefully_with_no_scenarios(monkeypatch):
    _patch_history(monkeypatch, [])

    def _raise(current_user, user_db, limit):
        raise HTTPException(status_code=404, detail="No scenarios available")

    monkeypatch.setattr(writing_router, "_recommend_writing_scenarios", _raise)

    insights = asyncio.run(writing_router._build_writing_insights(
        {"writing:purpose": 2.0}, current_user=FakeUser("user-1"), user_db=None,
    ))

    assert insights["next_best_action"] is None
    assert insights["weakest_skill"]["tag"] == "writing:purpose"


def test_build_writing_insights_degrades_gracefully_on_unexpected_error(monkeypatch):
    # A DB blip in the history/weakness lookup (anything other than the
    # "no scenarios" HTTPException) must not bubble up -- by this point the
    # submission is already scored and saved, so this is best-effort like
    # record_skill_observations, not something worth failing the request over.
    async def _raise(user_db, user_id, tag_prefix, label_fn=None):
        raise ConnectionError("db unreachable")

    monkeypatch.setattr(writing_router, "get_weakness", _raise)

    insights = asyncio.run(writing_router._build_writing_insights(
        {"writing:purpose": 2.0}, current_user=FakeUser("user-1"), user_db=None,
    ))

    assert insights is None
