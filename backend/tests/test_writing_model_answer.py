"""W5: admin-only model_answer (reference/model letter) for generated Writing
content. Layered on top of the W2/W3/W4 structured contract in
draft_generator._validate_writing -- no schema migration, internal content
metadata only (never exposed through learner-facing Writing endpoints, never
sent to the learner scorer, never replaces key_points). No Gemini/TTS/DB
writes: _call_ai is faked directly (same style as test_writing_distractor_pii.py).
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


_VALID_MODEL_ANSWER = (
    "Dear Ms Nair,\n\n"
    "I am writing to hand over the ongoing care of Mr Arthur Whitfield, a 77-year-old man, "
    "following his discharge from our ward on 18/10/2023, so that his care can continue "
    "smoothly in the community.\n\n"
    "Mr Whitfield was admitted on 12/10/2023 with an exacerbation of chronic obstructive "
    "pulmonary disease alongside his known type 2 diabetes. During his stay he was stabilised "
    "on oxygen therapy and his blood glucose was brought under control following an adjustment "
    "to his insulin regimen. He responded well to treatment and was fit for discharge with both "
    "conditions well managed at the time he left our care.\n\n"
    "Given his history, I would be grateful if you could continue to monitor his respiratory "
    "status and blood glucose control at his next community appointment, and review his insulin "
    "dose as needed. Please do not hesitate to contact the ward if you require any further "
    "information about his admission.\n\n"
    "Yours sincerely,\nRegistered Nurse"
)


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
        "model_answer": _VALID_MODEL_ANSWER,
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


# ── 1. model_answer schema validation ─────────────────────────────────────

def test_valid_model_answer_passes():
    assert draft_generator._validate_writing(_valid_content()) == []


def test_model_answer_empty_string_rejected():
    errors = draft_generator._validate_writing(_valid_content(model_answer="   "))
    assert any("model_answer' must be a non-empty string" in e for e in errors)


def test_model_answer_wrong_type_rejected():
    errors = draft_generator._validate_writing(_valid_content(model_answer=["not", "a", "string"]))
    assert any("model_answer' must be a non-empty string" in e for e in errors)


def test_model_answer_too_short_rejected():
    errors = draft_generator._validate_writing(_valid_content(model_answer="Dear Ms Nair, discharge complete. Regards."))
    assert any("word count" in e for e in errors)


def test_model_answer_too_long_rejected():
    long_answer = "Dear Ms Nair, " + ("word " * 400) + "Yours sincerely, Nurse."
    errors = draft_generator._validate_writing(_valid_content(model_answer=long_answer))
    assert any("word count" in e for e in errors)


def test_model_answer_does_not_address_recipient_rejected():
    off_topic_answer = _VALID_MODEL_ANSWER.replace("Nair", "Smith")
    errors = draft_generator._validate_writing(_valid_content(model_answer=off_topic_answer))
    assert any("does not appear to address the recipient" in e for e in errors)


def test_model_answer_leaks_internal_metadata_rejected():
    leaky_answer = _VALID_MODEL_ANSWER + "\n\nkey_points: covered all of them."
    errors = draft_generator._validate_writing(_valid_content(model_answer=leaky_answer))
    assert any("must not expose internal metadata" in e for e in errors)


def test_model_answer_copies_case_note_shorthand_rejected():
    shorthand_answer = _VALID_MODEL_ANSWER + " Admission date 12/10/2023 with exacerbation of COPD and type 2 diabetes."
    errors = draft_generator._validate_writing(_valid_content(model_answer=shorthand_answer))
    assert any("copied verbatim" in e for e in errors)


def test_model_answer_fabricated_date_rejected():
    fabricated_answer = _VALID_MODEL_ANSWER + " A follow-up scan is booked for 01/01/2099."
    errors = draft_generator._validate_writing(_valid_content(model_answer=fabricated_answer))
    assert any("possible fabricated fact" in e for e in errors)


# ── 2. model_answer preserved through save (draft content round-trips as-is;
#      draft_store.py's update path is a plain JSONB merge, nothing to test
#      beyond the shape draft_generator/draft_publisher already agree on) ──

def test_generate_draft_returns_model_answer(monkeypatch):
    _patch_ai(monkeypatch, _valid_content())
    result = _run(draft_generator.generate_draft(
        module="writing", difficulty="medium", specialty="geriatrics", topic="COPD discharge",
    ))
    assert result["validation_warnings"] == []
    assert result["generated_content"]["model_answer"] == _VALID_MODEL_ANSWER


# ── 3. model_answer preserved through publish ─────────────────────────────

def test_publish_preserves_model_answer_in_interlocutor_card():
    draft = {"id": 1, "module": "writing", "ai_title": None, "draft_name": None, "generated_content": _valid_content()}
    payload = draft_publisher._scenario_payload(draft)
    assert payload["interlocutor_card"]["model_answer"] == _VALID_MODEL_ANSWER
    # Never leaked into the top-level fields the learner-facing select reads,
    # and never merged into/replacing key_points.
    assert "model_answer" not in payload["setting"]
    assert "model_answer" not in payload["nurse_card"]
    assert payload["key_points"] == _valid_content()["key_points"]


# ── 4. no fabricated obvious facts test fixture (covered above:
#      test_model_answer_fabricated_date_rejected) plus a clean fixture that
#      must NOT be flagged ────────────────────────────────────────────────

def test_model_answer_grounded_facts_not_flagged():
    assert draft_generator._validate_writing(_valid_content()) == []


# ── 5 & 6. learner endpoint excludes model_answer and distractor_notes ────

def test_learner_endpoints_never_select_model_answer():
    for fn in (writing.list_scenarios, writing.get_scenario, writing._require_writing_scenario, writing._recommend_writing_scenarios):
        source = inspect.getsource(fn)
        assert "model_answer" not in source
        assert "interlocutor_card" not in source


# ── 7. legacy Writing drafts without model_answer remain valid ───────────

def test_legacy_draft_without_model_answer_still_valid():
    assert draft_generator._validate_writing(_legacy_content()) == []


def test_publish_legacy_draft_has_no_model_answer_key():
    draft = {"id": 2, "module": "writing", "ai_title": None, "draft_name": None, "generated_content": _legacy_content()}
    payload = draft_publisher._scenario_payload(draft)
    assert "model_answer" not in payload["interlocutor_card"]
