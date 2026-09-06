"""W3.4: server-side, calendar-aware patient.age derivation for newly
generated Writing Content Studio drafts. The AI supplies patient.dob; it is
no longer authoritative for patient.age -- generate_draft() derives it from
dob + the existing deterministic reference-date rule (explicit > admission >
discharge) via draft_generator._derive_writing_patient_age, before
_validate_writing() runs. An existing/legacy draft never passes through
generate_draft(), so its age (if any) is left untouched and only checked for
consistency by the pre-existing W3.1 validator. No Gemini/TTS/DB writes:
_call_ai is faked directly, same style as test_writing_consistency.py.
"""
import asyncio
from datetime import date

import pytest

from app.services import ai_registry, draft_generator

DOB = date(1946, 3, 14)


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


def _content(*, ai_age="78", extra_note=None, dob="14/03/1946", dob_in_notes=True):
    """DOB 14/03/1946, admission 12/10/2023, discharge 18/10/2023 -> age 77
    at either reference date. ai_age simulates whatever (possibly wrong) age
    the AI put in patient.age -- generate_draft must override it.

    dob_in_notes controls whether the DOB also appears as free text in the
    case notes -- _labeled_writing_dates scans notes text (not just
    patient.dob) for a "DOB"-keyworded date, so a no-DOB scenario needs both
    patient.dob blanked AND no DOB mention left in the notes."""
    patient_line = "Arthur Whitfield (Mr), DOB 14/03/1946." if dob_in_notes else "Arthur Whitfield (Mr)."
    structured = [
        {"section": "Patient Details", "items": [patient_line]},
        {"section": "Presenting Complaint", "items": ["Admission date 12/10/2023 with exacerbation of COPD."]},
        {"section": "Medical Progress", "items": ["Stabilised on oxygen therapy.", "Discharge date 18/10/2023."]},
    ]
    if extra_note:
        structured[-1]["items"].append(extra_note)
    return {
        "title": "Discharge Letter - COPD",
        "patient": {"name": "Arthur Whitfield", "dob": dob, "age": ai_age, "gender": "male", "address": ""},
        "purpose": "To hand over Mr Whitfield's ongoing care following discharge.",
        "case_notes_structured": structured,
        "case_notes": _render_case_notes(structured),
        "task": "Write a discharge letter. The body of the letter should be approximately 180-200 words.",
    }


# ── 1/2. DOB + reference date derives the correct calendar age ────────────

def test_dob_and_reference_date_derive_correct_age():
    assert draft_generator._calculate_age(DOB, date(2023, 10, 18)) == 77


# ── 3. Birthday not yet reached in the reference year ──────────────────────

def test_birthday_not_yet_reached_subtracts_a_year():
    dob = date(2000, 12, 25)
    reference = date(2023, 1, 1)  # before the Dec 25 anniversary that year
    assert draft_generator._calculate_age(dob, reference) == 22


# ── 4. Birthday already passed in the reference year ────────────────────────

def test_birthday_already_passed_uses_full_year_count():
    dob = date(2000, 1, 1)
    reference = date(2023, 12, 25)  # well after the Jan 1 anniversary
    assert draft_generator._calculate_age(dob, reference) == 23


# ── 5. Leap-day DOB edge case ────────────────────────────────────────────────

def test_leap_day_dob_before_anniversary_in_non_leap_year():
    dob = date(2000, 2, 29)  # 2000 is a leap year
    reference = date(2023, 2, 28)  # day before the Feb 29 anniversary; 2023 isn't a leap year
    assert draft_generator._calculate_age(dob, reference) == 22


# ── 6. New generation gets the derived (authoritative) age ─────────────────

def test_generate_draft_overrides_ai_age_with_derived_age(monkeypatch):
    _patch_ai(monkeypatch, _content(ai_age="78"))  # AI's wrong guess

    result = _run(draft_generator.generate_draft(
        module="writing", difficulty="medium", specialty="geriatrics", topic="discharge planning",
    ))

    assert result["generated_content"]["patient"]["age"] == "77"
    assert result["validation_warnings"] == []


# ── 7. Legacy draft with a matching age passes ──────────────────────────────

def test_legacy_draft_with_matching_age_passes():
    content = _content(ai_age="77")  # already correct, validated as-is (not through generate_draft)
    assert draft_generator._validate_writing(content) == []


# ── 8. Legacy draft with a mismatched age fails ─────────────────────────────

def test_legacy_draft_with_mismatched_age_fails():
    content = _content(ai_age="78")  # wrong, and never routed through generate_draft's derivation
    errors = draft_generator._validate_writing(content)
    assert any("patient.age" in e and "78" in e for e in errors)


# ── 9. Contradictory age stated in case_notes still fails ──────────────────

def test_contradictory_age_in_case_notes_still_fails(monkeypatch):
    # patient.age will be correctly derived to 77, but the notes separately
    # claim the patient is 75 -- that contradiction must still be caught.
    _patch_ai(monkeypatch, _content(extra_note="Patient is a 75 y.o. male."))

    with pytest.raises(draft_generator.DraftGenerationError) as exc_info:
        _run(draft_generator.generate_draft(
            module="writing", difficulty="medium", specialty="geriatrics", topic="discharge planning",
        ))
    assert "Conflicting patient age values" in str(exc_info.value)


# ── 10. No DOB + an existing age stays backward compatible ─────────────────

def test_no_dob_leaves_existing_age_untouched(monkeypatch):
    content = _content(ai_age="80", dob="", dob_in_notes=False)  # nothing to derive from

    _patch_ai(monkeypatch, content)
    result = _run(draft_generator.generate_draft(
        module="writing", difficulty="medium", specialty="geriatrics", topic="discharge planning",
    ))

    assert result["generated_content"]["patient"]["age"] == "80"
    assert result["validation_warnings"] == []
