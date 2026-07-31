"""
Tests for the Mock Test pack generation logic (app.routers.mock._pick_unused).

Pure unit test -- no Supabase. The one invariant that matters: a new pack
never draws content already claimed by an earlier pack, and generation
refuses (rather than silently repeating) when too little fresh content
remains for the requested count.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.mock import _pick_unused


def test_picks_only_from_unused():
    picked = _pick_unused([1, 2, 3, 4], used={1, 2}, count=2)
    assert picked is not None
    assert set(picked) <= {3, 4}
    assert len(picked) == 2


def test_none_when_not_enough_fresh_content():
    assert _pick_unused([1, 2], used={1, 2}, count=1) is None
    assert _pick_unused([1], used=set(), count=2) is None


def test_exact_fit_still_succeeds():
    assert _pick_unused([1, 2, 3], used={1, 2}, count=1) == [3]


def test_empty_used_set_can_pick_from_full_pool():
    picked = _pick_unused([5, 6, 7], used=set(), count=3)
    assert picked is not None and sorted(picked) == [5, 6, 7]


if __name__ == "__main__":
    test_picks_only_from_unused()
    test_none_when_not_enough_fresh_content()
    test_exact_fit_still_succeeds()
    test_empty_used_set_can_pick_from_full_pool()
    print("ok")
