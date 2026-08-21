"""Phase S3 -- patient voice/gender/age pipeline: interlocutor_card.gender/
voice_config (Content Studio draft contract) flowing through generation,
validation, publish, and both runtimes (legacy TTS + realtime voice).

No Gemini/AI/TTS calls: draft_generator._call_ai is monkeypatched (same
style as test_content_studio_speaking.py), and the realtime voice-selection
tests call speaking_realtime's pure helper functions directly.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services import ai_registry, draft_generator, draft_publisher, draft_store, tts_service
import app.routers.speaking_realtime as srt
from test_draft_workflow import FakeSupabase


def _run(coro):
    return asyncio.run(coro)


def _valid_speaking_content(**overrides):
    content = {
        "title": "Managing Post-Op Anxiety",
        "setting": "A busy surgical ward on the second day after a hip replacement.",
        "difficulty": "intermediate",
        "specialty": "surgical nursing",
        "nurse_card": {
            "role": "You are the nurse in charge of this patient",
            "tasks": ["Explain the recovery plan", "Address the patient's concerns", "Confirm understanding"],
        },
        "interlocutor_card": {
            "patient_name": "Maria Santos",
            "gender": "female",
            "age": 54,
            "condition": "post-operative hip replacement",
            "mood": "anxious",
            "background": "Lives alone; worried about mobility after discharge.",
            "persona": "Anxious patient worried about pain and independence.",
            "emotional_triggers": ["mention of pain"],
            "questions_to_ask": ["Will I be able to walk again?"],
            "information_to_withhold": ["Has not told her family about the surgery"],
            "voice_config": {"voice_name": "en-GB-Wavenet-A", "language_code": "en-GB", "speaking_rate": 0.95, "pitch": 0.0},
        },
    }
    content.update(overrides)
    return content


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


def _generate(monkeypatch, content):
    _patch_ai(monkeypatch, content)
    return _run(draft_generator.generate_draft(
        module="speaking", difficulty="intermediate", specialty="surgical nursing",
        topic="post-operative recovery",
    ))


def _expect_generation_error(monkeypatch, content, needle: str):
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert needle in str(e)


# ── 1/2. Generation includes gender + voice_config ──────────────────────

def test_generate_draft_speaking_includes_gender(monkeypatch):
    result = _generate(monkeypatch, _valid_speaking_content())
    assert result["validation_warnings"] == []
    assert result["generated_content"]["interlocutor_card"]["gender"] == "female"


def test_generate_draft_speaking_includes_voice_config(monkeypatch):
    result = _generate(monkeypatch, _valid_speaking_content())
    card = result["generated_content"]["interlocutor_card"]
    assert card["voice_config"] == {"voice_name": "en-GB-Wavenet-A", "language_code": "en-GB", "speaking_rate": 0.95, "pitch": 0.0}


# ── 3. Invalid gender rejected ───────────────────────────────────────────

def test_invalid_gender_rejected(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"]["gender"] = "robot"
    _expect_generation_error(monkeypatch, content, "interlocutor_card.gender")


# ── 4. Invalid voice_config rejected ─────────────────────────────────────

def test_invalid_voice_config_not_object_rejected(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"]["voice_config"] = "en-GB-Wavenet-A"
    _expect_generation_error(monkeypatch, content, "voice_config' must be an object")


def test_invalid_voice_config_empty_voice_name_rejected(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"]["voice_config"]["voice_name"] = "   "
    _expect_generation_error(monkeypatch, content, "voice_config.voice_name")


def test_invalid_voice_config_non_numeric_rate_rejected(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"]["voice_config"]["speaking_rate"] = "fast"
    _expect_generation_error(monkeypatch, content, "voice_config.speaking_rate")


def test_invalid_voice_config_non_numeric_pitch_rejected(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"]["voice_config"]["pitch"] = "low"
    _expect_generation_error(monkeypatch, content, "voice_config.pitch")


# ── 5. Draft stores voice fields ─────────────────────────────────────────

def test_draft_save_reload_preserves_voice_fields(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)

    content = _valid_speaking_content()
    created = draft_store.create_draft(
        module="speaking", draft_name="Post-Op Anxiety", ai_title=content["title"],
        metadata={}, prompt={}, generated_content=content, validation_warnings=[],
        model_used=None, created_by="admin-1",
    )
    reloaded = draft_store.get_draft(created["id"])
    assert reloaded["generated_content"]["interlocutor_card"]["gender"] == "female"
    assert reloaded["generated_content"]["interlocutor_card"]["voice_config"] == content["interlocutor_card"]["voice_config"]


# ── 6/7/8. Publish maps gender/age, explicit voice_config wins ──────────

def test_publish_maps_gender_and_age_and_keeps_explicit_voice_config(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)

    content = _valid_speaking_content()
    draft = {
        "id": 1, "module": "speaking", "generated_content": content,
        "ai_title": content["title"], "draft_name": "n", "metadata": {},
    }
    result = draft_publisher.publish(draft, published_by="admin-1")
    assert result["action"] == "created"

    row = fake.tables["scenarios"][0]
    assert row["patient_gender"] == "female"
    assert row["patient_age"] == 54
    assert row["voice_config"] == {"voice_name": "en-GB-Wavenet-A", "language_code": "en-GB", "speaking_rate": 0.95, "pitch": 0.0}


def test_publish_coerces_age_range_string(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)

    content = _valid_speaking_content()
    content["interlocutor_card"]["age"] = "40-50"
    draft = {"id": 1, "module": "speaking", "generated_content": content, "ai_title": content["title"], "draft_name": "n", "metadata": {}}
    draft_publisher.publish(draft, published_by="admin-1")

    row = fake.tables["scenarios"][0]
    assert row["patient_age"] == 40


# ── 9. Missing voice_config uses deterministic fallback ──────────────────

def test_publish_missing_voice_config_uses_deterministic_fallback(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)

    content = _valid_speaking_content()
    del content["interlocutor_card"]["voice_config"]
    draft = {"id": 1, "module": "speaking", "generated_content": content, "ai_title": content["title"], "draft_name": "n", "metadata": {}}
    draft_publisher.publish(draft, published_by="admin-1")

    row = fake.tables["scenarios"][0]
    assert row["voice_config"] == tts_service.get_default_voice_config(gender="female", age=54)


# ── 10/11. Legacy runtime fallback (speaking.py reads these columns and,
# when voice_config is NULL, calls get_default_voice_config directly --
# this pins the exact function that fallback depends on) ────────────────

def test_legacy_voice_fallback_uses_gender_and_age():
    assert tts_service.get_default_voice_config(gender="male", age=70) == {
        "voice_name": "en-GB-Wavenet-D", "speaking_rate": 0.80, "pitch": -3.0, "language_code": "en-GB",
    }


def test_legacy_voice_fallback_generic_default_when_no_gender_age():
    assert tts_service.get_default_voice_config(gender=None, age=None) == {
        "voice_name": "en-GB-Wavenet-A", "speaking_rate": 0.95, "pitch": 0.0, "language_code": "en-GB",
    }


# ── 12/13. Realtime voice selection priority ──────────────────────────────

def test_realtime_prefers_voice_config_gender_over_patient_gender():
    scenario = {"patient_gender": "male", "voice_config": {"gender": "female"}}
    assert srt._resolve_realtime_gender(scenario) == "female"


def test_realtime_falls_back_to_patient_gender_when_voice_config_has_no_gender():
    scenario = {"patient_gender": "male", "voice_config": {"voice_name": "en-GB-Wavenet-D"}}
    assert srt._resolve_realtime_gender(scenario) == "male"


def test_realtime_falls_back_to_patient_gender_when_voice_config_missing():
    scenario = {"patient_gender": "female", "voice_config": None}
    assert srt._resolve_realtime_gender(scenario) == "female"


# ── 14/15. Provider compatibility ────────────────────────────────────────

def test_openai_voice_mapper_compatibility():
    assert srt.VOICE_MAPPERS["openai"]("male") == "ash"
    assert srt.VOICE_MAPPERS["openai"]("female") == "shimmer"
    assert srt.VOICE_MAPPERS["openai"](None) == "alloy"


def test_gemini_voice_mapper_compatibility():
    assert srt.VOICE_MAPPERS["gemini"]("male") == "Puck"
    assert srt.VOICE_MAPPERS["gemini"]("female") == "Kore"
    assert srt.VOICE_MAPPERS["gemini"](None) == "Aoede"


# ── 16. Sibling fields unchanged by the voice mapping ────────────────────

def test_publish_sibling_fields_unaffected(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)

    content = _valid_speaking_content()
    draft = {"id": 1, "module": "speaking", "generated_content": content, "ai_title": content["title"], "draft_name": "n", "metadata": {}}
    draft_publisher.publish(draft, published_by="admin-1")

    row = fake.tables["scenarios"][0]
    assert row["title"] == content["title"]
    assert row["setting"] == content["setting"]
    assert row["nurse_card"] == content["nurse_card"]
    assert row["interlocutor_card"] == content["interlocutor_card"]


# ── Legacy Content Studio draft without gender/voice_config still valid ──

def test_legacy_speaking_draft_without_gender_voice_config_still_valid(monkeypatch):
    content = _valid_speaking_content()
    del content["interlocutor_card"]["gender"]
    del content["interlocutor_card"]["voice_config"]
    result = _generate(monkeypatch, content)
    assert result["validation_warnings"] == []
    card = result["generated_content"]["interlocutor_card"]
    assert "gender" not in card
    assert "voice_config" not in card
