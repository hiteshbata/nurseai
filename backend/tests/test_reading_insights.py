"""
Tests for Adaptive Reading V1 (Sprint 2): app.routers.reading._reading_skill_label
and _build_reading_insights. Ported locally from Speaking's Sprint 1 pattern
(app.routers.speaking._skill_label / _build_speaking_insights) rather than a
shared service -- see _build_reading_insights's docstring.

_build_reading_insights delegates test picking to the existing
_recommend_reading_tests and weakness history to the existing get_weakness
(neither changed here) -- these tests monkeypatch those two collaborators
rather than re-testing them.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import app.routers.reading as reading_router


class FakeUser:
    def __init__(self, user_id):
        self.id = user_id


def _patch_recommend(monkeypatch, recs):
    monkeypatch.setattr(reading_router, "_recommend_reading_tests", lambda current_user, user_db, limit: recs)


def _patch_history(monkeypatch, history):
    async def _fake_get_weakness(user_db, user_id, tag_prefix, label_fn=None):
        return history
    monkeypatch.setattr(reading_router, "get_weakness", _fake_get_weakness)


def test_reading_skill_label_uses_existing_skill_labels():
    assert reading_router._reading_skill_label("reading:skill:inference") == reading_router.SKILL_LABELS["inference"]


def test_reading_skill_label_falls_back_for_unknown_tag():
    assert reading_router._reading_skill_label("reading:skill:made-up") == "Made Up"


def test_build_reading_insights_returns_none_without_scores():
    result = asyncio.run(reading_router._build_reading_insights({}, current_user=None, user_db=None))
    assert result is None


def test_build_reading_insights_falls_back_to_session_when_no_history(monkeypatch):
    _patch_history(monkeypatch, [])
    _patch_recommend(monkeypatch, [{"test_id": 7, "title": "OET Reading Test 3", "reason": "Needs practice"}])

    insights = asyncio.run(reading_router._build_reading_insights(
        {"reading:skill:inference": 2.0, "reading:skill:scanning": 5.0, "reading:skill:detail": 4.0},
        current_user=FakeUser("user-1"),
        user_db=None,
    ))

    assert insights["based_on"] == "session"
    assert insights["weakest_skill"]["tag"] == "reading:skill:inference"
    assert insights["weakest_skill"]["score"] == 2.0
    assert insights["strongest_skill"]["tag"] == "reading:skill:scanning"
    assert insights["next_best_action"]["test_id"] == 7
    assert "today" in insights["recommendation_reason"]
    assert insights["weakest_skill"]["label"] in insights["actionable_improvement"]
    assert "today's session" in insights["confidence_message"]


def test_build_reading_insights_prefers_learner_history_over_session(monkeypatch):
    # Session's own worst skill is inference, but history says scanning is the
    # real, recurring weak spot -- the recommendation should follow history.
    _patch_history(monkeypatch, [{"skill": "scanning", "label": "Scanning (finding which text has the info)", "band": 2.5, "attempts": 5}])
    _patch_recommend(monkeypatch, [{"test_id": 3, "title": "OET Reading Test 1", "reason": "Needs practice"}])

    insights = asyncio.run(reading_router._build_reading_insights(
        {"reading:skill:inference": 3.0, "reading:skill:scanning": 4.0, "reading:skill:detail": 5.0},
        current_user=FakeUser("user-1"),
        user_db=None,
    ))

    assert insights["based_on"] == "history"
    assert insights["weakest_skill"] == {"tag": "reading:skill:scanning", "label": "Scanning (finding which text has the info)", "score": 2.5}
    assert "recent sessions" in insights["recommendation_reason"]
    assert "5" in insights["confidence_message"]


def test_build_reading_insights_degrades_gracefully_with_no_tests(monkeypatch):
    _patch_history(monkeypatch, [])

    def _raise(current_user, user_db, limit):
        raise HTTPException(status_code=404, detail="No reading tests available")

    monkeypatch.setattr(reading_router, "_recommend_reading_tests", _raise)

    insights = asyncio.run(reading_router._build_reading_insights(
        {"reading:skill:inference": 2.0}, current_user=FakeUser("user-1"), user_db=None,
    ))

    assert insights["next_best_action"] is None
    assert insights["weakest_skill"]["tag"] == "reading:skill:inference"


def test_build_reading_insights_degrades_gracefully_on_unexpected_error(monkeypatch):
    # A DB blip in the history/weakness lookup (anything other than the
    # "no tests" HTTPException) must not bubble up -- by this point the
    # submission is already saved, so this is best-effort like
    # record_skill_observations, not something worth failing the request over.
    async def _raise(user_db, user_id, tag_prefix, label_fn=None):
        raise ConnectionError("db unreachable")

    monkeypatch.setattr(reading_router, "get_weakness", _raise)

    insights = asyncio.run(reading_router._build_reading_insights(
        {"reading:skill:inference": 2.0}, current_user=FakeUser("user-1"), user_db=None,
    ))

    assert insights is None
