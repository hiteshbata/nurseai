"""
Tests for the Mock Test pack/session staleness guard (app.routers.mock).

Pure unit tests on _pack_is_servable -- no Supabase. Mock Test freezes content
by reference (ids), not by copying it; these prove the guard that stops a
pack/session from being listed/started/advanced once one of its frozen ids
has gone inactive (or never resolved), while leaving unrelated
packs/sections untouched.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.mock import _pack_is_servable

ACTIVE = {
    "listening_tests": {1},
    "reading_tests": {10},
    "scenarios": {100, 101, 102},
}


def _pack(**overrides):
    base = {
        "listening_test_id": 1,
        "reading_test_id": 10,
        "writing_scenario_id": 100,
        "speaking_scenario_id_1": 101,
        "speaking_scenario_id_2": 102,
    }
    base.update(overrides)
    return base


def test_servable_when_all_five_still_active():
    assert _pack_is_servable(_pack(), ACTIVE) is True


def test_not_servable_when_reading_went_inactive():
    # reading_test_id=99 isn't in the active set -- unpublished after the pack was built.
    assert _pack_is_servable(_pack(reading_test_id=99), ACTIVE) is False


def test_not_servable_when_a_speaking_scenario_went_inactive():
    assert _pack_is_servable(_pack(speaking_scenario_id_2=999), ACTIVE) is False


def test_not_servable_when_an_id_is_missing_entirely():
    # e.g. a pack built before a column existed / never fully assembled.
    assert _pack_is_servable(_pack(reading_test_id=None), ACTIVE) is False


def test_unrelated_pack_with_all_active_ids_is_unaffected():
    other_pack = _pack(listening_test_id=1, reading_test_id=10)
    stale_pack = _pack(reading_test_id=99)
    assert _pack_is_servable(other_pack, ACTIVE) is True
    assert _pack_is_servable(stale_pack, ACTIVE) is False


if __name__ == "__main__":
    test_servable_when_all_five_still_active()
    test_not_servable_when_reading_went_inactive()
    test_not_servable_when_a_speaking_scenario_went_inactive()
    test_not_servable_when_an_id_is_missing_entirely()
    test_unrelated_pack_with_all_active_ids_is_unaffected()
    print("ok")
