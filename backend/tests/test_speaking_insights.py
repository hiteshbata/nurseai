"""
Tests for the Adaptive Speaking V1 rule-based recommendation (Sprint 1,
ADR-008): app.routers.speaking._skill_label and _build_speaking_insights.

_build_speaking_insights delegates scenario picking to the existing
_recommend_scenarios and weakness history to the existing get_weakness
(neither changed here) -- these tests monkeypatch those two collaborators
rather than re-testing them.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import app.routers.speaking as speaking_router


class FakeUser:
    def __init__(self, user_id):
        self.id = user_id


def _patch_recommend(monkeypatch, recs):
    monkeypatch.setattr(speaking_router, "_recommend_scenarios", lambda current_user, user_db, limit: recs)


def _patch_history(monkeypatch, history):
    async def _fake_get_weakness(user_db, user_id, tag_prefix):
        return history
    monkeypatch.setattr(speaking_router, "get_weakness", _fake_get_weakness)


def test_skill_label_formats_tag():
    assert speaking_router._skill_label("speaking:clinical_communication") == "Clinical Communication"


def test_build_speaking_insights_returns_none_without_scores():
    result = asyncio.run(speaking_router._build_speaking_insights({}, current_user=None, user_db=None))
    assert result is None


def test_build_speaking_insights_falls_back_to_session_when_no_history(monkeypatch):
    _patch_history(monkeypatch, [])
    _patch_recommend(monkeypatch, [{"scenario_id": 7, "title": "Chest Pain", "reason": "Needs practice"}])

    insights = asyncio.run(speaking_router._build_speaking_insights(
        {"speaking:fluency": 2.0, "speaking:grammar": 5.0, "speaking:empathy": 4.0},
        current_user=FakeUser("user-1"),
        user_db=None,
    ))

    assert insights["based_on"] == "session"
    assert insights["weakest_skill"] == {"tag": "speaking:fluency", "label": "Fluency", "score": 2.0}
    assert insights["strongest_skill"] == {"tag": "speaking:grammar", "label": "Grammar", "score": 5.0}
    assert insights["next_best_action"]["scenario_id"] == 7
    assert "today" in insights["recommendation_reason"]
    assert "Fluency" in insights["actionable_improvement"]
    assert "today's session" in insights["confidence_message"]


def test_build_speaking_insights_prefers_learner_history_over_session(monkeypatch):
    # Session's own worst criterion is empathy, but history says grammar is the
    # real, recurring weak spot -- the recommendation should follow history.
    _patch_history(monkeypatch, [{"skill": "grammar", "label": "Grammar", "band": 2.5, "attempts": 5}])
    _patch_recommend(monkeypatch, [{"scenario_id": 3, "title": "Discharge Planning", "reason": "Needs practice"}])

    insights = asyncio.run(speaking_router._build_speaking_insights(
        {"speaking:empathy": 3.0, "speaking:grammar": 4.0, "speaking:fluency": 5.0},
        current_user=FakeUser("user-1"),
        user_db=None,
    ))

    assert insights["based_on"] == "history"
    assert insights["weakest_skill"] == {"tag": "speaking:grammar", "label": "Grammar", "score": 2.5}
    assert "recent sessions" in insights["recommendation_reason"]
    assert "5" in insights["confidence_message"]


def test_build_speaking_insights_degrades_gracefully_with_no_scenarios(monkeypatch):
    _patch_history(monkeypatch, [])

    def _raise(current_user, user_db, limit):
        raise HTTPException(status_code=404, detail="No scenarios available")

    monkeypatch.setattr(speaking_router, "_recommend_scenarios", _raise)

    insights = asyncio.run(speaking_router._build_speaking_insights(
        {"speaking:fluency": 2.0}, current_user=FakeUser("user-1"), user_db=None,
    ))

    assert insights["next_best_action"] is None
    assert insights["weakest_skill"]["tag"] == "speaking:fluency"


def test_build_speaking_insights_degrades_gracefully_on_unexpected_error(monkeypatch):
    # A DB blip in the history/weakness lookup (anything other than the
    # "no scenarios" HTTPException) must not bubble up -- by this point the
    # submission is already saved, so this is best-effort like
    # record_skill_observations, not something worth failing the request over.
    async def _raise(user_db, user_id, tag_prefix):
        raise ConnectionError("db unreachable")

    monkeypatch.setattr(speaking_router, "get_weakness", _raise)

    insights = asyncio.run(speaking_router._build_speaking_insights(
        {"speaking:fluency": 2.0}, current_user=FakeUser("user-1"), user_db=None,
    ))

    assert insights is None
