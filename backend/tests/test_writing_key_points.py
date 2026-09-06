"""W1: scenarios.key_points must reach score_writing's scoring prompt, taking
precedence over the legacy nurse_card.tasks checklist. No real network --
ai_scoring._call_ai is faked directly."""
import asyncio

from app.services import ai_scoring as ai
from app.routers import writing


def _run(coro):
    return asyncio.run(coro)


_FULL_SCORES = {
    "purpose": {"score": 2, "feedback": ""},
    "content": {"score": 5, "feedback": ""},
    "conciseness": {"score": 5, "feedback": ""},
    "genre_style": {"score": 5, "feedback": ""},
    "organization": {"score": 5, "feedback": ""},
    "language": {"score": 5, "feedback": ""},
}


def _patch_call_ai(monkeypatch, captured):
    async def fake_call_ai(messages, **kwargs):
        captured.append(messages[0]["content"])
        return {"scores": {k: dict(v) for k, v in _FULL_SCORES.items()},
                "top_strengths": [], "top_improvements": [], "corrected_version": "x"}

    monkeypatch.setattr(ai, "_call_ai", fake_call_ai)


def test_non_empty_key_points_passed_to_scorer_and_take_precedence(monkeypatch):
    captured = []
    _patch_call_ai(monkeypatch, captured)
    _run(ai.score_writing(
        content="Dear Doctor...",
        nurse_card={"tasks": ["legacy task should not appear"], "role": "Write a letter"},
        scenario_title="Discharge Letter",
        case_notes="notes",
        key_points=["Explain medication change", "Note follow-up appointment"],
    ))
    prompt = captured[0]
    assert "Explain medication change" in prompt
    assert "Note follow-up appointment" in prompt
    assert "legacy task should not appear" not in prompt


def test_key_points_appear_as_scoring_checklist_bullets(monkeypatch):
    captured = []
    _patch_call_ai(monkeypatch, captured)
    _run(ai.score_writing(
        content="Dear Doctor...",
        nurse_card={},
        key_points=["Point one"],
    ))
    assert "- Point one" in captured[0]
    assert "KEY POINTS THE LETTER SHOULD COVER:" in captured[0]


def test_empty_key_points_falls_back_to_nurse_card_tasks(monkeypatch):
    captured = []
    _patch_call_ai(monkeypatch, captured)
    _run(ai.score_writing(
        content="Dear Doctor...",
        nurse_card={"tasks": ["Legacy task A", "Legacy task B"]},
        key_points=[],
    ))
    assert "- Legacy task A" in captured[0]
    assert "- Legacy task B" in captured[0]


def test_both_empty_yields_empty_checklist_not_a_crash(monkeypatch):
    captured = []
    _patch_call_ai(monkeypatch, captured)
    result = _run(ai.score_writing(
        content="Dear Doctor...",
        nurse_card={},
        key_points=None,
    ))
    assert "(no key points provided)" in captured[0]
    assert result["scoring_failed"] is False


def test_legacy_scenario_without_key_points_kwarg_still_scores(monkeypatch):
    """Old call sites that never pass key_points (default None) must keep
    working exactly as before this change."""
    captured = []
    _patch_call_ai(monkeypatch, captured)
    result = _run(ai.score_writing(
        content="Dear Doctor...",
        nurse_card={"tasks": ["Legacy task"]},
        scenario_title="Old Scenario",
        case_notes="notes",
    ))
    assert "- Legacy task" in captured[0]
    assert result["scoring_failed"] is False
    assert result["overall_score"] is not None


def test_scenario_select_for_submit_includes_key_points():
    """Regression guard for the original bug: _require_writing_scenario's
    select must fetch key_points, or score_writing never receives it no
    matter what ai_scoring.py does."""
    import inspect
    source = inspect.getsource(writing._require_writing_scenario)
    assert "key_points" in source


def test_student_facing_scenario_endpoints_never_select_key_points():
    """key_points is scoring-only metadata (like nurse_card's rubric) --
    student-facing endpoints must not leak it in their select."""
    import inspect
    for fn in (writing.list_scenarios, writing.get_scenario, writing._recommend_writing_scenarios):
        source = inspect.getsource(fn)
        assert "key_points" not in source
