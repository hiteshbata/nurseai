"""W2: structured OET Writing Content Studio contract (specialty, letter_type,
recipient, patient, purpose, case_notes_structured, writing_requirements) on
top of the existing title/case_notes/task/key_points fields. Additive and
opt-in throughout -- a legacy flat draft must still generate/validate/publish
exactly as before. No Gemini/TTS/DB writes: _call_ai is faked directly (same
style as test_content_studio_part_wiring.py / test_writing_key_points.py);
draft_publisher's payload builders take a plain dict and never touch
Supabase, so no supabase mocking is needed for the publish tests either.
"""
import asyncio
import inspect

import pytest

from app.services import ai_registry, draft_generator, draft_publisher, prompt_builder
from app.services import ai_scoring as ai
from app.routers import writing


def _run(coro):
    return asyncio.run(coro)


class _FakeDupCheckSupabase:
    """No production rows ever match -- duplicate-title check is a no-op."""

    def table(self, *_a, **_k):
        return self

    def select(self, *_a, **_k):
        return self

    def ilike(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        class _Result:
            data = []
        return _Result()


def _patch_ai(monkeypatch, content: dict):
    async def fake_call_ai(*a, **kw):
        return dict(content)

    async def fake_get_model_config(purpose):
        raise ai_registry.PurposeNotConfigured("no model configured in tests")

    monkeypatch.setattr(draft_generator, "_call_ai", fake_call_ai)
    monkeypatch.setattr(ai_registry, "get_model_config", fake_get_model_config)
    monkeypatch.setattr(draft_generator, "get_supabase", lambda: _FakeDupCheckSupabase())


def _structured_content(**overrides):
    content = {
        "title": "Discharge Letter - Pneumonia",
        "difficulty": "medium",
        "specialty": "respiratory",
        "letter_type": "discharge",
        "patient": {"name": "Lionel Ramamurthy", "dob": "", "age": "63", "gender": "male", "address": ""},
        "recipient": {
            "name": "Georgine Ponsford", "role": "Resident Community Nurse",
            "organization": "Community Retirement Home", "address": "103 Light Street, Newtown",
        },
        "purpose": "To hand over Mr Ramamurthy's care back to the retirement home on discharge.",
        "case_notes_structured": [
            {"section": "Patient Details", "items": ["Admitted with community-acquired pneumonia."]},
            {"section": "Medical Progress", "items": [
                "Afebrile.",
                "Dietary review by dietitian; weight gain 1.5kg.",
                "Chest physio continuing twice daily.",
                "Discharge planned; follow-up appointment arranged.",
            ]},
        ],
        "case_notes": (
            "Patient Details\nAdmitted with community-acquired pneumonia.\n\n"
            "Medical Progress\nAfebrile. Dietary review by dietitian; weight gain 1.5kg. "
            "Chest physio continuing twice daily. Discharge planned; follow-up appointment arranged."
        ),
        "task": "Write a discharge letter to Ms Georgine Ponsford. The body of the letter should be approximately 180-200 words.",
        "key_points": ["Explain pneumonia diagnosis", "Note ongoing dietary monitoring", "Mention chest physio plan", "Flag discharge date", "Confirm follow-up"],
        "writing_requirements": dict(draft_generator._WRITING_REQUIREMENTS_DEFAULT),
    }
    content.update(overrides)
    return content


def _legacy_content(**overrides):
    content = {
        "title": "Old Scenario",
        "difficulty": "medium",
        "case_notes": "notes",
        "task": "Write a letter.",
        "key_points": ["Point one"],
    }
    content.update(overrides)
    return content


# ── 1. Generated structured writing schema ───────────────────────────────

def test_prompt_schema_covers_every_structured_field():
    _, user = prompt_builder.build_writing_prompt("medium", "cardiology", "chest pain")
    for marker in (
        "letter_type", "referral, discharge, transfer, ongoing_care",
        "patient", "recipient", "purpose", "case_notes_structured", "case_notes", "task", "key_points",
    ):
        assert marker in user


def test_generate_draft_returns_structured_writing_content(monkeypatch):
    _patch_ai(monkeypatch, _structured_content())

    result = _run(draft_generator.generate_draft(
        module="writing", difficulty="medium", specialty="respiratory", topic="pneumonia",
    ))

    content = result["generated_content"]
    assert content["letter_type"] == "discharge"
    assert content["recipient"]["organization"] == "Community Retirement Home"
    assert content["patient"]["name"] == "Lionel Ramamurthy"
    assert content["case_notes_structured"][0]["section"] == "Patient Details"
    assert content["writing_requirements"] == draft_generator._WRITING_REQUIREMENTS_DEFAULT
    assert result["validation_warnings"] == []


# ── 2. Recipient validation ───────────────────────────────────────────────

def test_recipient_missing_fields_rejected():
    errors = draft_generator._validate_writing(_structured_content(recipient={"name": "X", "role": "", "organization": "", "address": ""}))
    assert any("recipient.role" in e for e in errors)
    assert any("recipient.organization" in e for e in errors)
    assert any("recipient.address" in e for e in errors)


def test_recipient_fully_filled_passes():
    errors = draft_generator._validate_writing(_structured_content())
    assert errors == []


# ── 3. Patient validation ─────────────────────────────────────────────────

def test_patient_missing_name_rejected():
    errors = draft_generator._validate_writing(_structured_content(patient={"name": "", "age": "63"}))
    assert any("patient.name" in e for e in errors)


def test_patient_with_name_passes():
    errors = draft_generator._validate_writing(_structured_content(patient={"name": "Jake Peterson", "age": "18"}))
    assert errors == []


# ── 4. letter_type validation ─────────────────────────────────────────────

def test_invalid_letter_type_rejected():
    errors = draft_generator._validate_writing(_structured_content(letter_type="update"))
    assert any("letter_type" in e for e in errors)


@pytest.mark.parametrize("letter_type", ["referral", "discharge", "transfer", "ongoing_care"])
def test_each_controlled_letter_type_accepted(letter_type):
    errors = draft_generator._validate_writing(_structured_content(letter_type=letter_type))
    assert errors == []


# ── 5. purpose validation ─────────────────────────────────────────────────

def test_structured_draft_without_purpose_rejected():
    errors = draft_generator._validate_writing(_structured_content(purpose=""))
    assert any("purpose" in e for e in errors)


def test_legacy_draft_without_purpose_is_fine():
    errors = draft_generator._validate_writing(_legacy_content())
    assert errors == []


# ── 6. Structured case notes ──────────────────────────────────────────────

def test_case_notes_structured_empty_list_rejected():
    errors = draft_generator._validate_writing(_structured_content(case_notes_structured=[]))
    assert any("case_notes_structured" in e for e in errors)


def test_case_notes_structured_section_missing_name_rejected():
    errors = draft_generator._validate_writing(_structured_content(case_notes_structured=[{"section": "", "items": ["a"]}]))
    assert any("section" in e for e in errors)


def test_case_notes_structured_section_empty_items_rejected():
    errors = draft_generator._validate_writing(_structured_content(case_notes_structured=[{"section": "Plan", "items": []}]))
    assert any("items" in e for e in errors)


def test_case_notes_structured_valid_passes():
    errors = draft_generator._validate_writing(_structured_content())
    assert errors == []


# ── 7. Writing requirements ───────────────────────────────────────────────

def test_writing_requirements_bad_types_rejected():
    errors = draft_generator._validate_writing(_structured_content(writing_requirements={
        "reading_minutes": "five", "writing_minutes": 40, "target_word_count": "", "letter_format": "yes", "no_note_form": True,
    }))
    assert any("reading_minutes" in e for e in errors)
    assert any("target_word_count" in e for e in errors)
    assert any("letter_format" in e for e in errors)


def test_writing_requirements_default_injected_when_ai_omits_it(monkeypatch):
    content = _structured_content()
    content.pop("writing_requirements", None)
    _patch_ai(monkeypatch, content)

    result = _run(draft_generator.generate_draft(
        module="writing", difficulty="medium", specialty="respiratory", topic="pneumonia",
    ))
    assert result["generated_content"]["writing_requirements"] == draft_generator._WRITING_REQUIREMENTS_DEFAULT


# ── 8. Legacy flat draft compatibility ────────────────────────────────────

def test_legacy_flat_draft_passes_structured_validator():
    assert draft_generator._validate_writing(_legacy_content()) == []


def test_legacy_flat_draft_generates_and_validates_end_to_end(monkeypatch):
    _patch_ai(monkeypatch, _legacy_content())

    result = _run(draft_generator.generate_draft(
        module="writing", difficulty="medium", specialty="respiratory", topic="pneumonia",
    ))
    assert result["validation_warnings"] == []
    assert result["generated_content"]["title"] == "Old Scenario"
    # Constant requirements are still injected even for a legacy AI response --
    # this is generator-side, not something the legacy draft opted into.
    assert result["generated_content"]["writing_requirements"] == draft_generator._WRITING_REQUIREMENTS_DEFAULT


# ── 9. Publish preserves new fields ───────────────────────────────────────

def _draft(module="writing", **content_overrides):
    return {"id": 42, "module": module, "ai_title": None, "draft_name": None, "generated_content": _structured_content(**content_overrides)}


def test_publish_payload_preserves_structured_fields_via_interlocutor_card():
    payload = draft_publisher._scenario_payload(_draft())
    assert payload["setting"] == _structured_content()["case_notes"]
    assert payload["nurse_card"] == {"role": _structured_content()["task"]}
    assert payload["key_points"] == _structured_content()["key_points"]

    extra = payload["interlocutor_card"]
    assert extra["letter_type"] == "discharge"
    assert extra["recipient"]["organization"] == "Community Retirement Home"
    assert extra["patient"]["name"] == "Lionel Ramamurthy"
    assert extra["purpose"]
    assert extra["case_notes_structured"][0]["section"] == "Patient Details"
    assert extra["writing_requirements"]["target_word_count"] == "180-200"


def test_publish_payload_legacy_draft_keeps_interlocutor_card_empty():
    draft = {"id": 43, "module": "writing", "ai_title": None, "draft_name": None, "generated_content": _legacy_content()}
    payload = draft_publisher._scenario_payload(draft)
    assert payload["interlocutor_card"] == {}
    assert payload["setting"] == "notes"
    assert payload["nurse_card"] == {"role": "Write a letter."}
    assert payload["key_points"] == ["Point one"]


# ── 10. key_points remain available to scoring ────────────────────────────

_FULL_SCORES = {k: {"score": 5, "feedback": ""} for k in ("purpose", "content", "conciseness", "genre_style", "organization", "language")}


def test_structured_draft_key_points_reach_scoring(monkeypatch):
    captured = []

    async def fake_call_ai(messages, **kwargs):
        captured.append(messages[0]["content"])
        return {"scores": {k: dict(v) for k, v in _FULL_SCORES.items()}, "top_strengths": [], "top_improvements": [], "corrected_version": "x"}

    monkeypatch.setattr(ai, "_call_ai", fake_call_ai)

    content = _structured_content()
    payload = draft_publisher._scenario_payload({"id": 1, "module": "writing", "ai_title": None, "draft_name": None, "generated_content": content})

    _run(ai.score_writing(
        content="Dear Ms Ponsford...",
        nurse_card=payload["nurse_card"],
        scenario_title=content["title"],
        case_notes=payload["setting"],
        key_points=payload["key_points"],
    ))

    prompt = captured[0]
    for kp in content["key_points"]:
        assert kp in prompt


# ── 11. Learner projection remains safe ───────────────────────────────────

def test_learner_select_never_touches_structured_metadata_columns():
    """The new fields live only in interlocutor_card (see publisher test
    above). The learner-facing writing endpoints must keep selecting the
    same columns as before W2 -- interlocutor_card must not appear."""
    source = inspect.getsource(writing._require_writing_scenario)
    assert "interlocutor_card" not in source
    for fn in (writing.list_scenarios, writing.get_scenario, writing._recommend_writing_scenarios):
        assert "interlocutor_card" not in inspect.getsource(fn)


def test_structured_metadata_confined_to_interlocutor_card():
    payload = draft_publisher._scenario_payload(_draft())
    for leaked_field in ("letter_type", "recipient", "patient", "purpose", "case_notes_structured"):
        assert leaked_field not in payload
        assert leaked_field not in payload["setting"]
        assert leaked_field not in payload["nurse_card"]
