import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.routers import practice
from app.services.targeted_practice import TargetedPracticeItem


def _run(coro):
    return asyncio.run(coro)


_USER = SimpleNamespace(id="student-1", is_anonymous=False)
_ITEM = TargetedPracticeItem(
    content_type="listening_test", content_id=42, skill_tag="listening:B", skill_label="Part B",
    band=2.5, match_type="direct", title="Workplace Notices", part="B", difficulty="medium",
)


def test_recommended_returns_top_items_for_listening():
    user_db = SimpleNamespace()
    with patch.object(practice, "get_targeted_practice", new=AsyncMock(return_value=[_ITEM])) as mock_call:
        result = _run(practice.get_recommended_practice(module="listening", current_user=_USER, user_db=user_db))

    mock_call.assert_called_once_with(user_db, "student-1", "listening", limit=3)
    assert result == [{
        "content_type": "listening_test", "content_id": 42, "skill_tag": "listening:B",
        "skill_label": "Part B", "band": 2.5, "match_type": "direct", "title": "Workplace Notices",
        "part": "B", "difficulty": "medium",
    }]


def test_recommended_calls_service_with_authenticated_user_id_not_client_supplied():
    other_user = SimpleNamespace(id="student-2", is_anonymous=False)
    user_db = SimpleNamespace()
    with patch.object(practice, "get_targeted_practice", new=AsyncMock(return_value=[])) as mock_call:
        _run(practice.get_recommended_practice(module="listening", current_user=other_user, user_db=user_db))
    mock_call.assert_called_once_with(user_db, "student-2", "listening", limit=3)


def test_recommended_empty_result_returns_empty_list():
    user_db = SimpleNamespace()
    with patch.object(practice, "get_targeted_practice", new=AsyncMock(return_value=[])):
        result = _run(practice.get_recommended_practice(module="listening", current_user=_USER, user_db=user_db))
    assert result == []


def test_recommended_service_error_returns_empty_list_not_a_500():
    user_db = SimpleNamespace()
    with patch.object(practice, "get_targeted_practice", new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = _run(practice.get_recommended_practice(module="listening", current_user=_USER, user_db=user_db))
    assert result == []


def test_recommended_unsupported_module_400s():
    user_db = SimpleNamespace()
    with patch.object(practice, "get_targeted_practice", new=AsyncMock()) as mock_call:
        try:
            _run(practice.get_recommended_practice(module="technique", current_user=_USER, user_db=user_db))
            assert False, "expected 400"
        except HTTPException as e:
            assert e.status_code == 400
    mock_call.assert_not_called()


def test_recommended_unmapped_module_400s():
    user_db = SimpleNamespace()
    try:
        _run(practice.get_recommended_practice(module="reading", current_user=_USER, user_db=user_db))
        assert False, "expected 400"
    except HTTPException as e:
        assert e.status_code == 400


def test_recommended_performs_no_writes():
    # user_db has no insert/update/upsert attrs at all -- if the router ever
    # tried to write through it, this would AttributeError instead of
    # silently passing.
    user_db = SimpleNamespace()
    with patch.object(practice, "get_targeted_practice", new=AsyncMock(return_value=[_ITEM])):
        _run(practice.get_recommended_practice(module="listening", current_user=_USER, user_db=user_db))
    assert not hasattr(user_db, "insert")


def test_recommended_does_not_duplicate_plan_gating_in_router():
    # The router has no plan/profile lookups of its own -- it passes
    # user_db straight through to the service and returns whatever comes
    # back, even for a plan-gated [] result.
    user_db = SimpleNamespace()
    with patch.object(practice, "get_targeted_practice", new=AsyncMock(return_value=[])) as mock_call:
        result = _run(practice.get_recommended_practice(module="listening", current_user=_USER, user_db=user_db))
    assert result == []
    mock_call.assert_called_once_with(user_db, "student-1", "listening", limit=3)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
