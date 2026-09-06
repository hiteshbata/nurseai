"""W3.1: deterministic internal-consistency validation for generated Writing
content (age/DOB vs a reference date, date ordering, conflicting patient
facts, task/recipient mismatch, key_points grounded in case notes). Layered
on top of the W2 structural contract in draft_generator._validate_writing --
no schema change, no new Content Studio field. No Gemini/TTS/DB writes:
_call_ai is faked directly (same style as test_content_studio_writing.py).
"""
import asyncio

from app.services import ai_registry, draft_generator


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


def _sync_case_notes(content):
    """Re-render `case_notes` from `case_notes_structured` after a test
    mutates the structured items -- both are scanned for dates/ages, so
    letting them drift apart would silently defeat the mutation under test."""
    content["case_notes"] = _render_case_notes(content["case_notes_structured"])


def _valid_content() -> dict:
    """Matches the DOB=14/03/1946, reference=12/10/2023 -> age 77 example
    from the W3.1 spec: a realistic discharge letter with a consistent
    admission (12/10/2023) < discharge (18/10/2023) <= follow-up (25/10/2023)
    date chain, and key_points each grounded in a case-note fact."""
    structured = [
        {"section": "Patient Details", "items": ["Arthur Whitfield (Mr), DOB 14/03/1946."]},
        {"section": "Presenting Complaint", "items": [
            "Admission date 12/10/2023 with exacerbation of COPD and type 2 diabetes.",
        ]},
        {"section": "Medical Progress", "items": [
            "Stabilised on oxygen therapy.",
            "Blood glucose controlled with insulin adjustment.",
            "Discharge date 18/10/2023.",
            "Follow-up appointment arranged for 25/10/2023.",
        ]},
    ]
    return {
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
            "Mention oxygen therapy weaning plan",
            "Flag discharge date",
            "Confirm follow-up appointment",
        ],
        "writing_requirements": dict(draft_generator._WRITING_REQUIREMENTS_DEFAULT),
    }


# ── 1. Correct DOB/age passes ─────────────────────────────────────────────

def test_correct_dob_age_passes():
    assert draft_generator._validate_writing(_valid_content()) == []


# ── 2. Incorrect age fails ────────────────────────────────────────────────

def test_incorrect_age_fails():
    content = _valid_content()
    content["patient"]["age"] = "78"  # DOB 14/03/1946 as of 12/10/2023 is 77, not 78
    errors = draft_generator._validate_writing(content)
    assert any("patient.age" in e and "78" in e for e in errors)


# ── 3. Admission/discharge ordering ───────────────────────────────────────

def test_admission_after_discharge_rejected():
    content = _valid_content()
    content["case_notes_structured"][1]["items"][0] = (
        "Admission date 20/10/2023 with exacerbation of COPD and type 2 diabetes."
    )
    _sync_case_notes(content)
    errors = draft_generator._validate_writing(content)
    assert any("after discharge date" in e for e in errors)


# ── 4. Valid follow-up date ────────────────────────────────────────────────

def test_valid_follow_up_date_passes():
    content = _valid_content()  # follow-up 25/10/2023 is after discharge 18/10/2023
    errors = draft_generator._validate_writing(content)
    assert not any("Follow-up date" in e for e in errors)


# ── 5. Invalid follow-up date ──────────────────────────────────────────────

def test_follow_up_before_discharge_rejected():
    content = _valid_content()
    content["case_notes_structured"][2]["items"][3] = "Follow-up appointment arranged for 15/10/2023."
    _sync_case_notes(content)
    errors = draft_generator._validate_writing(content)
    assert any("before discharge date" in e for e in errors)


# ── 6. Conflicting patient age ────────────────────────────────────────────

def test_conflicting_patient_age_rejected():
    content = _valid_content()
    content["case_notes_structured"][0]["items"][0] = "Arthur Whitfield (Mr), DOB 14/03/1946, 70 y.o."
    _sync_case_notes(content)
    errors = draft_generator._validate_writing(content)
    assert any("Conflicting patient age values" in e for e in errors)


# ── 7. Task/recipient mismatch ────────────────────────────────────────────

def test_task_recipient_mismatch_rejected():
    content = _valid_content()
    content["recipient"]["name"] = "Someone Else"  # task still addresses "Ms Priya Nair"
    errors = draft_generator._validate_writing(content)
    assert any("Task addresses" in e for e in errors)


# ── 8. Key point absent from notes ────────────────────────────────────────

def test_key_point_absent_from_notes_rejected():
    content = _valid_content()
    content["key_points"][0] = "Explain recent orthopaedic surgery"  # not in case notes at all
    errors = draft_generator._validate_writing(content)
    assert any("shares no clinical detail" in e for e in errors)


# ── 9. Valid realistic Writing draft passes end-to-end ────────────────────

def test_valid_realistic_draft_generates_and_saves_clean(monkeypatch):
    _patch_ai(monkeypatch, _valid_content())

    result = _run(draft_generator.generate_draft(
        module="writing", difficulty="medium", specialty="geriatrics",
        topic="discharge planning for an older patient with multiple chronic conditions",
    ))

    assert result["validation_warnings"] == []
    assert result["generated_content"]["patient"]["age"] == "77"
