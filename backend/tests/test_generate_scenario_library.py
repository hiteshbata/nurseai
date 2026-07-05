"""
Tests for the scenario-generation quality gate (app.services.generate_scenario_library).

Pure unit tests against validate_scenario only -- no network, no AI calls,
no Supabase. This is the automated check that stands between AI output and
a scenario actually landing in the database, so it needs its own coverage
independent of the (untestable-without-mocking) generation call itself.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.generate_scenario_library import validate_scenario


def _valid_scenario(**overrides):
    base = {
        "title": "Post-Fall Assessment in Aged Care",
        "setting": "Aged care facility, morning shift. Mrs. Lee fell in the bathroom overnight.",
        "difficulty": "medium",
        "nurse_card": {
            "role": "You are speaking to a 78-year-old woman who fell overnight.",
            "tasks": ["Task 1", "Task 2", "Task 3", "Task 4", "Task 5"],
        },
        "interlocutor_card": {
            "patient_name": "Mrs. Lee",
            "age": 78,
            "condition": "post-fall, bruised hip",
            "mood": "anxious",
            "background": "Lives alone. Worried about losing independence.",
            "emotional_triggers": ["mentions of moving to a nursing home", "fear of another fall"],
            "questions_to_ask": ["Will I need surgery?", "Can I still live alone?"],
            "information_to_withhold": ["Has fallen once before, unreported"],
            "instructions_for_ai": "Play an anxious but proud elderly woman.",
        },
    }
    base.update(overrides)
    return base


def test_valid_scenario_passes():
    assert validate_scenario(_valid_scenario()) == []


def test_rejects_non_dict():
    assert validate_scenario("not a dict") == ["not a JSON object"]
    assert validate_scenario(None) == ["not a JSON object"]
    assert validate_scenario([1, 2, 3]) == ["not a JSON object"]


def test_rejects_short_title():
    errors = validate_scenario(_valid_scenario(title="Hi"))
    assert "missing or too-short title" in errors


def test_rejects_missing_title():
    errors = validate_scenario(_valid_scenario(title=""))
    assert "missing or too-short title" in errors


def test_rejects_short_setting():
    errors = validate_scenario(_valid_scenario(setting="Too short."))
    assert "missing or too-short setting" in errors


def test_rejects_too_few_tasks():
    scenario = _valid_scenario()
    scenario["nurse_card"]["tasks"] = ["Task 1", "Task 2"]
    errors = validate_scenario(scenario)
    assert any("nurse_card.tasks has 2 items" in e for e in errors)


def test_rejects_too_many_tasks():
    scenario = _valid_scenario()
    scenario["nurse_card"]["tasks"] = [f"Task {i}" for i in range(8)]
    errors = validate_scenario(scenario)
    assert any("nurse_card.tasks has 8 items" in e for e in errors)


def test_rejects_missing_nurse_card_role():
    scenario = _valid_scenario()
    del scenario["nurse_card"]["role"]
    errors = validate_scenario(scenario)
    assert "missing nurse_card.role" in errors


def test_rejects_missing_nurse_card_entirely():
    scenario = _valid_scenario()
    del scenario["nurse_card"]
    errors = validate_scenario(scenario)
    assert "missing nurse_card" in errors


def test_rejects_missing_interlocutor_fields():
    scenario = _valid_scenario()
    del scenario["interlocutor_card"]["mood"]
    errors = validate_scenario(scenario)
    assert "missing interlocutor_card.mood" in errors


def test_rejects_too_few_emotional_triggers():
    scenario = _valid_scenario()
    scenario["interlocutor_card"]["emotional_triggers"] = ["only one"]
    errors = validate_scenario(scenario)
    assert any("emotional_triggers" in e for e in errors)


def test_rejects_too_few_questions_to_ask():
    scenario = _valid_scenario()
    scenario["interlocutor_card"]["questions_to_ask"] = []
    errors = validate_scenario(scenario)
    assert any("questions_to_ask" in e for e in errors)


def test_rejects_missing_information_to_withhold():
    scenario = _valid_scenario()
    scenario["interlocutor_card"]["information_to_withhold"] = []
    errors = validate_scenario(scenario)
    assert any("information_to_withhold" in e for e in errors)


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    tests = [f for name, f in vars(mod).items() if name.startswith("test_") and inspect.isfunction(f)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
