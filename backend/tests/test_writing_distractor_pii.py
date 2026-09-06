"""W4: distractor/relevance metadata (distractor_notes) and PII hygiene for
generated Writing content. Layered on top of the W2/W3 structured contract in
draft_generator._validate_writing -- no schema migration, internal content
metadata only (never exposed through learner-facing Writing endpoints). No
Gemini/TTS/DB writes: _call_ai is faked directly (same style as
test_content_studio_writing.py / test_writing_consistency.py).
"""
import asyncio
import inspect

from app.services import ai_registry, draft_generator, draft_publisher
from app.routers import writing


def _run(coro):
    return asyncio.run(coro)


class _FakeDupCheckSupabase:
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


def _render_case_notes(structured):
    lines = []
    for section in structured:
        lines.append(section["section"])
        lines.extend(section["items"])
        lines.append("")
    return "\n".join(lines).strip()


def _valid_content(**overrides) -> dict:
    structured = [
        {"section": "Patient Details", "items": ["Arthur Whitfield (Mr), DOB 14/03/1946."]},
        {"section": "Medical History", "items": [
            "Chest X-ray from a previous admission in 2019 showed mild cardiomegaly.",
        ]},
        {"section": "Presenting Complaint", "items": [
            "Admission date 12/10/2023 with exacerbation of COPD and type 2 diabetes.",
        ]},
        {"section": "Medical Progress", "items": [
            "Stabilised on oxygen therapy.",
            "Blood glucose controlled with insulin adjustment.",
            "Discharge date 18/10/2023.",
        ]},
    ]
    content = {
        "title": "Discharge Letter - COPD and Diabetes",
        "difficulty": "medium",
        "specialty": "geriatrics",
        "letter_type": "discharge",
        "patient": {"name": "Arthur Whitfield", "dob": "14/03/1946", "age": "77", "gender": "male", "address": ""},
        "recipient": {
            "name": "Priya Nair", "role": "Practice Nurse",
            "organization": "Riverside Medical Centre", "address": "12 Elm Street, Riverside",
        },
        "purpose": "To hand over Mr Whitfield's ongoing care to the practice nurse following discharge.",
        "case_notes_structured": structured,
        "case_notes": _render_case_notes(structured),
        "task": "Write a discharge letter to Ms Priya Nair. The body of the letter should be approximately 180-200 words.",
        "key_points": [
            "Explain COPD exacerbation management",
            "Note insulin adjustment for diabetes control",
            "Flag discharge date",
        ],
        "writing_requirements": dict(draft_generator._WRITING_REQUIREMENTS_DEFAULT),
        "distractor_notes": [
            {
                "text": "Chest X-ray from a previous admission in 2019 showed mild cardiomegaly.",
                "reason": "Historical admission-only imaging finding, not relevant to this discharge letter.",
            },
        ],
    }
    content.update(overrides)
    return content


def _legacy_content() -> dict:
    return {
        "title": "Old Scenario",
        "difficulty": "medium",
        "case_notes": "notes",
        "task": "Write a letter.",
        "key_points": ["Point one"],
    }


# ── 1. Valid distractor metadata ──────────────────────────────────────────

def test_valid_distractor_metadata_passes():
    assert draft_generator._validate_writing(_valid_content()) == []


# ── 2. Invalid distractor shape ───────────────────────────────────────────

def test_distractor_notes_not_a_list_rejected():
    errors = draft_generator._validate_writing(_valid_content(distractor_notes={"text": "x", "reason": "y"}))
    assert any("distractor_notes' must be a list" in e for e in errors)


def test_distractor_note_not_an_object_rejected():
    errors = draft_generator._validate_writing(_valid_content(distractor_notes=["just a string"]))
    assert any("distractor_notes[1] must be an object" in e for e in errors)


# ── 3. Distractor text not grounded → reject ──────────────────────────────

def test_distractor_text_not_grounded_rejected():
    content = _valid_content(distractor_notes=[
        {"text": "Patient previously worked as a commercial airline pilot for 20 years.", "reason": "Not needed."},
    ])
    errors = draft_generator._validate_writing(content)
    assert any("not grounded in case_notes" in e for e in errors)


def test_distractor_text_near_verbatim_grounded_passes():
    content = _valid_content(distractor_notes=[
        {"text": "Chest X-ray from previous admission 2019 showed mild cardiomegaly", "reason": "Historical imaging, not needed for this letter."},
    ])
    assert draft_generator._validate_writing(content) == []


# ── 4. Empty reason → reject ──────────────────────────────────────────────

def test_distractor_note_empty_reason_rejected():
    content = _valid_content(distractor_notes=[
        {"text": "Chest X-ray from a previous admission in 2019 showed mild cardiomegaly.", "reason": ""},
    ])
    errors = draft_generator._validate_writing(content)
    assert any("distractor_notes[1] must have non-empty 'reason'" in e for e in errors)


def test_distractor_note_empty_text_rejected():
    content = _valid_content(distractor_notes=[{"text": "", "reason": "Some reason."}])
    errors = draft_generator._validate_writing(content)
    assert any("distractor_notes[1] must have non-empty 'text'" in e for e in errors)


# ── 5. PII: phone number → reject ─────────────────────────────────────────

def test_pii_phone_number_in_case_notes_rejected():
    content = _valid_content()
    content["case_notes_structured"].append(
        {"section": "Social Background", "items": ["Emergency contact reachable on 0412 345 678."]}
    )
    content["case_notes"] = _render_case_notes(content["case_notes_structured"])
    errors = draft_generator._validate_writing(content)
    assert any("invented phone number" in e for e in errors)


# ── 6. PII: email → reject ────────────────────────────────────────────────

def test_pii_email_in_case_notes_rejected():
    content = _valid_content()
    content["case_notes_structured"].append(
        {"section": "Social Background", "items": ["Patient prefers contact via arthur.whitfield83@gmail.com."]}
    )
    content["case_notes"] = _render_case_notes(content["case_notes_structured"])
    errors = draft_generator._validate_writing(content)
    assert any("invented email address" in e for e in errors)


# ── 7. Valid recipient/facility address → allowed ─────────────────────────

def test_recipient_and_facility_address_never_flagged_as_pii():
    content = _valid_content(recipient={
        "name": "Priya Nair", "role": "Practice Nurse",
        "organization": "Riverside Medical Centre",
        "address": "12 Elm Street, Riverside, Phone: 03 9345 6789",
    })
    errors = draft_generator._validate_writing(content)
    assert not any("invented phone number" in e or "invented email address" in e for e in errors)


def test_patient_address_field_never_scanned_for_pii():
    content = _valid_content()
    content["patient"]["address"] = "45 Ocean Road, phone 03 9876 5432"
    errors = draft_generator._validate_writing(content)
    assert not any("invented phone number" in e for e in errors)


# ── 8. Legacy draft without distractor_notes → still valid ───────────────

def test_legacy_draft_without_distractor_notes_still_valid():
    assert draft_generator._validate_writing(_legacy_content()) == []


def test_legacy_draft_generates_end_to_end(monkeypatch):
    _patch_ai(monkeypatch, _legacy_content())
    result = _run(draft_generator.generate_draft(
        module="writing", difficulty="medium", specialty="respiratory", topic="pneumonia",
    ))
    assert result["validation_warnings"] == []


# ── 9. Learner endpoint excludes distractor_notes ─────────────────────────

def test_learner_endpoints_never_select_distractor_notes():
    for fn in (writing.list_scenarios, writing.get_scenario, writing._require_writing_scenario, writing._recommend_writing_scenarios):
        source = inspect.getsource(fn)
        assert "distractor_notes" not in source
        assert "interlocutor_card" not in source


# ── 10. Publish preserves metadata ────────────────────────────────────────

def test_publish_preserves_distractor_notes_in_interlocutor_card():
    draft = {"id": 1, "module": "writing", "ai_title": None, "draft_name": None, "generated_content": _valid_content()}
    payload = draft_publisher._scenario_payload(draft)
    assert payload["interlocutor_card"]["distractor_notes"] == _valid_content()["distractor_notes"]
    # Never leaked into the top-level fields the learner-facing select reads.
    assert "distractor_notes" not in payload["setting"]
    assert "distractor_notes" not in payload["nurse_card"]


def test_publish_legacy_draft_has_no_distractor_notes_key():
    draft = {"id": 2, "module": "writing", "ai_title": None, "draft_name": None, "generated_content": _legacy_content()}
    payload = draft_publisher._scenario_payload(draft)
    assert payload["interlocutor_card"] == {}


# ── 11. End-to-end generation with distractor_notes ───────────────────────

def test_generate_draft_returns_distractor_notes(monkeypatch):
    _patch_ai(monkeypatch, _valid_content())
    result = _run(draft_generator.generate_draft(
        module="writing", difficulty="medium", specialty="geriatrics", topic="COPD discharge",
    ))
    assert result["validation_warnings"] == []
    assert result["generated_content"]["distractor_notes"][0]["reason"]
