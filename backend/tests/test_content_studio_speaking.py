"""Phase S1 -- Speaking Content Studio schema parity with the runtime's
richer patient model (interlocutor_card: patient_name/age/condition/mood/
background/emotional_triggers/questions_to_ask/information_to_withhold).

No Gemini/AI calls: _call_ai is monkeypatched, same style as
test_content_studio_part_wiring.py. Reuses FakeSupabase from
test_draft_workflow.py for the save/reload and publish tests instead of
reinventing an in-memory query-builder mock.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import copy

from app.services import ai_registry, draft_generator, draft_publisher, draft_store
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
            "age": 54,
            "condition": "post-operative hip replacement",
            "mood": "anxious",
            "background": "Lives alone; worried about mobility after discharge.",
            "persona": "Anxious patient worried about pain and independence.",
            "emotional_triggers": ["mention of pain"],
            "questions_to_ask": ["Will I be able to walk again?"],
            "information_to_withhold": ["Has not told her family about the surgery"],
        },
    }
    content.update(overrides)
    return content


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


def _generate(monkeypatch, content):
    _patch_ai(monkeypatch, content)
    return _run(draft_generator.generate_draft(
        module="speaking", difficulty="intermediate", specialty="surgical nursing",
        topic="post-operative recovery",
    ))


# ── 1. Rich patient card generation schema ──────────────────────────────

def test_generate_draft_speaking_produces_rich_patient_card_schema(monkeypatch):
    result = _generate(monkeypatch, _valid_speaking_content())

    assert result["validation_warnings"] == []
    card = result["generated_content"]["interlocutor_card"]
    for field in ("patient_name", "age", "condition", "mood", "background", "emotional_triggers", "questions_to_ask", "information_to_withhold"):
        assert field in card, f"missing {field}"
    assert "patient_name" in result["prompt"]["user_prompt"] or "patient" in result["prompt"]["user_prompt"].lower()


# ── 2/3. Required patient fields validation / missing patient name ─────

def test_missing_patient_name_raises(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"] = {**content["interlocutor_card"], "patient_name": ""}
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "patient_name" in str(e)


# ── 4. Invalid age ───────────────────────────────────────────────────────

def test_invalid_age_raises(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"] = {**content["interlocutor_card"], "age": "very old"}
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "age" in str(e)


# ── 5. Empty condition ───────────────────────────────────────────────────

def test_empty_condition_raises(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"] = {**content["interlocutor_card"], "condition": "  "}
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "condition" in str(e)


# ── 6. Empty mood ─────────────────────────────────────────────────────────

def test_empty_mood_raises(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"] = {**content["interlocutor_card"], "mood": ""}
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "mood" in str(e)


# ── 7. Empty background ──────────────────────────────────────────────────

def test_empty_background_raises(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"] = {**content["interlocutor_card"], "background": ""}
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "background" in str(e)


# ── 8/9/10. emotional_triggers / questions_to_ask / information_to_withhold preserved ──

def test_patient_list_fields_preserved_unchanged(monkeypatch):
    content = _valid_speaking_content()
    content["interlocutor_card"]["emotional_triggers"] = ["pain", "being alone"]
    content["interlocutor_card"]["questions_to_ask"] = ["Will I need more surgery?", "When can I drive?"]
    content["interlocutor_card"]["information_to_withhold"] = ["Missed two follow-up appointments"]

    result = _generate(monkeypatch, content)
    card = result["generated_content"]["interlocutor_card"]
    assert card["emotional_triggers"] == ["pain", "being alone"]
    assert card["questions_to_ask"] == ["Will I need more surgery?", "When can I drive?"]
    assert card["information_to_withhold"] == ["Missed two follow-up appointments"]


# ── 11. Nurse card unaffected ────────────────────────────────────────────

def test_nurse_card_unaffected_by_patient_card_validation(monkeypatch):
    content = _valid_speaking_content()
    result = _generate(monkeypatch, content)
    assert result["generated_content"]["nurse_card"] == content["nurse_card"]


def test_nurse_card_missing_role_raises(monkeypatch):
    content = _valid_speaking_content()
    content["nurse_card"] = {**content["nurse_card"], "role": ""}
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "nurse_card.role" in str(e)


def test_nurse_card_empty_tasks_raises(monkeypatch):
    content = _valid_speaking_content()
    content["nurse_card"] = {**content["nurse_card"], "tasks": []}
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "nurse_card.tasks" in str(e)


# ── 12. Draft save/reload preserves all fields ──────────────────────────

def test_draft_save_reload_preserves_all_fields(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)

    content = _valid_speaking_content()
    created = draft_store.create_draft(
        module="speaking", draft_name="Post-Op Anxiety", ai_title=content["title"],
        metadata={}, prompt={}, generated_content=content, validation_warnings=[],
        model_used=None, created_by="admin-1",
    )

    reloaded = draft_store.get_draft(created["id"])
    assert reloaded["generated_content"] == content


# ── 13. Publish preserves the richer interlocutor_card ──────────────────

def test_publish_preserves_rich_interlocutor_card(monkeypatch):
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
    assert row["interlocutor_card"] == content["interlocutor_card"]
    assert row["nurse_card"] == content["nurse_card"]


# ── 14. Legacy Speaking draft without richer fields still loads ─────────

def test_legacy_speaking_draft_without_rich_fields_still_loads(monkeypatch):
    legacy_content = {
        "title": "Legacy Scenario",
        "setting": "A ward.",
        "difficulty": "intermediate",
        "specialty": "general",
        "nurse_card": {"role": "You are the nurse", "tasks": ["Task 1"]},
        "interlocutor_card": {"persona": "Old-style persona-only card", "emotional_triggers": [], "questions_to_ask": [], "information_to_withhold": []},
    }

    fake = FakeSupabase()
    fake.tables["generated_content_drafts"] = [{
        "id": 42, "module": "speaking", "draft_name": "legacy", "ai_title": None,
        "metadata": {}, "prompt": {}, "generated_content": copy.deepcopy(legacy_content),
        "validation_warnings": [], "status": "draft", "model_used": None,
        "ai_generated": True, "created_by": None,
    }]
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)

    reloaded = draft_store.get_draft(42)
    assert reloaded["generated_content"] == legacy_content

    # Publisher must survive the legacy shape unchanged too -- no KeyError,
    # no forced richer fields.
    monkeypatch.setattr(draft_publisher, "get_supabase", lambda: fake)
    result = draft_publisher.publish(
        {"id": 42, "module": "speaking", "generated_content": legacy_content, "ai_title": None, "draft_name": "legacy", "metadata": {}},
        published_by="admin-1",
    )
    row = fake.tables["scenarios"][0]
    assert row["interlocutor_card"] == legacy_content["interlocutor_card"]


# ── Phase S2: conditional_responses + progression ───────────────────────

def _s2_content(**overrides):
    content = _valid_speaking_content()
    content["interlocutor_card"] = {
        **content["interlocutor_card"],
        "conditional_responses": [
            {"trigger": "When the nurse asks about self-injecting", "response_guidance": "Express doubt about managing it alone."},
            {"trigger": "When the nurse explains the technique clearly", "response_guidance": "Become more reassured."},
        ],
        "progression": [
            "Show anxiety about starting insulin.",
            "Raise a concern about self-injection.",
            "Listen and acknowledge the nurse's explanation.",
            "Become more comfortable with the plan.",
        ],
    }
    content.update(overrides)
    return content


def test_generated_content_contains_conditional_responses(monkeypatch):
    result = _generate(monkeypatch, _s2_content())

    assert result["validation_warnings"] == []
    card = result["generated_content"]["interlocutor_card"]
    assert len(card["conditional_responses"]) == 2
    assert card["conditional_responses"][0]["trigger"]
    assert card["conditional_responses"][0]["response_guidance"]


def test_generated_content_contains_progression(monkeypatch):
    result = _generate(monkeypatch, _s2_content())

    card = result["generated_content"]["interlocutor_card"]
    assert card["progression"] == [
        "Show anxiety about starting insulin.",
        "Raise a concern about self-injection.",
        "Listen and acknowledge the nurse's explanation.",
        "Become more comfortable with the plan.",
    ]


def test_invalid_conditional_response_missing_trigger_rejected(monkeypatch):
    content = _s2_content()
    content["interlocutor_card"]["conditional_responses"] = [
        {"trigger": "", "response_guidance": "Something"}
    ]
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "conditional_responses[1].trigger" in str(e)


def test_invalid_conditional_response_missing_guidance_rejected(monkeypatch):
    content = _s2_content()
    content["interlocutor_card"]["conditional_responses"] = [
        {"trigger": "Something happens", "response_guidance": ""}
    ]
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "conditional_responses[1].response_guidance" in str(e)


def test_invalid_conditional_responses_not_a_list_rejected(monkeypatch):
    content = _s2_content()
    content["interlocutor_card"]["conditional_responses"] = "not a list"
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "conditional_responses' must be a list" in str(e)


def test_invalid_progression_empty_beat_rejected(monkeypatch):
    content = _s2_content()
    content["interlocutor_card"]["progression"] = ["Fine beat", "   "]
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "progression[2]" in str(e)


def test_invalid_progression_too_many_beats_rejected(monkeypatch):
    content = _s2_content()
    content["interlocutor_card"]["progression"] = [f"beat {i}" for i in range(13)]
    try:
        _generate(monkeypatch, content)
        assert False, "expected DraftGenerationError"
    except draft_generator.DraftGenerationError as e:
        assert "progression' must have at most 12 beats" in str(e)


def test_legacy_speaking_draft_without_s2_fields_still_valid(monkeypatch):
    """A card with neither conditional_responses nor progression (Phase S1
    shape) must still generate cleanly -- both fields stay optional."""
    result = _generate(monkeypatch, _valid_speaking_content())

    assert result["validation_warnings"] == []
    card = result["generated_content"]["interlocutor_card"]
    assert "conditional_responses" not in card
    assert "progression" not in card
