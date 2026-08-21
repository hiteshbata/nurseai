"""Phase S2 -- conditional patient responses + conversation progression.

Covers app.services.ai_scoring.build_interlocutor_roleplay_instructions()
(the shared block extracted so the legacy chat path and the realtime voice
path stop drifting) and both its callers:
  - ai_scoring.get_patient_response()      (legacy text chat)
  - speaking_realtime._build_realtime_system_prompt()  (live voice)

No Gemini/AI calls: get_patient_response's _call_ai is monkeypatched to
capture the system prompt it was given, same style as
test_speaking_chat_ai_failure.py. _build_realtime_system_prompt is a pure
string builder, called directly.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.ai_scoring as ai_scoring
import app.routers.speaking_realtime as srt
from app.services.ai_scoring import build_interlocutor_roleplay_instructions


def _run(coro):
    return asyncio.run(coro)


CARD = {
    "patient_name": "Amit Patel",
    "age": 45,
    "condition": "Type 2 diabetes",
    "mood": "anxious",
    "background": "Newly diagnosed, lives alone.",
    "instructions_for_ai": "Anxious about starting insulin.",
    "emotional_triggers": ["mention of injections"],
    "questions_to_ask": ["Is there another option besides insulin?"],
    "information_to_withhold": ["Has been skipping his current medication"],
    "conditional_responses": [
        {
            "trigger": "When the nurse asks about self-injecting",
            "response_guidance": "Say you dislike the idea and doubt you'll manage it.",
        },
        {
            "trigger": "When the nurse explains the benefits and technique clearly",
            "response_guidance": "Acknowledge the explanation is clear and become more reassured.",
        },
    ],
    "progression": [
        "Initially show anxiety about starting insulin.",
        "Express concern about self-injection.",
        "Listen to the nurse's explanation and acknowledge understanding.",
        "Become more comfortable with insulin injections.",
    ],
}

SETTING = "A diabetes outpatient clinic, second visit since diagnosis."


# ── Shared helper: conditional_responses / progression rendering ─────────

def test_helper_renders_conditional_responses():
    prompt = build_interlocutor_roleplay_instructions(CARD)

    assert "CONDITIONAL RESPONSES" in prompt
    assert "When the nurse asks about self-injecting" in prompt
    assert "Say you dislike the idea and doubt you'll manage it." in prompt


def test_helper_renders_progression_in_order():
    prompt = build_interlocutor_roleplay_instructions(CARD)

    assert "CONVERSATION PROGRESSION" in prompt
    first = prompt.index("Initially show anxiety about starting insulin.")
    second = prompt.index("Express concern about self-injection.")
    third = prompt.index("Become more comfortable with insulin injections.")
    assert first < second < third


def test_helper_omits_sections_for_legacy_card_without_either_field():
    legacy_card = {k: v for k, v in CARD.items() if k not in ("conditional_responses", "progression")}
    prompt = build_interlocutor_roleplay_instructions(legacy_card)

    assert "CONDITIONAL RESPONSES" not in prompt
    assert "CONVERSATION PROGRESSION" not in prompt


def test_helper_includes_scenario_setting_when_given():
    prompt = build_interlocutor_roleplay_instructions(CARD, SETTING)

    assert "SCENARIO SETTING" in prompt
    assert SETTING in prompt


def test_helper_omits_setting_section_when_blank():
    prompt = build_interlocutor_roleplay_instructions(CARD, "")

    assert "SCENARIO SETTING" not in prompt


def test_helper_still_respects_questions_and_withholding():
    prompt = build_interlocutor_roleplay_instructions(CARD)

    assert "Is there another option besides insulin?" in prompt
    assert "Has been skipping his current medication" in prompt


def test_helper_does_not_leak_nurse_card_shaped_keys():
    """Regression: the helper only ever reads interlocutor_card fields.
    A caller accidentally handing it the whole scenario row (which also has
    nurse_card) must not leak nurse-only content into the patient prompt."""
    polluted = dict(CARD)
    polluted["nurse_card"] = {"role": "You are the nurse", "tasks": ["Explain insulin technique"]}

    prompt = build_interlocutor_roleplay_instructions(polluted)

    assert "You are the nurse" not in prompt
    assert "nurse_card" not in prompt


# ── Legacy text-chat path: get_patient_response ───────────────────────────

def test_legacy_patient_response_prompt_receives_conditional_and_progression(monkeypatch):
    captured = {}

    async def fake_call_ai(messages, *a, **kw):
        captured["system_prompt"] = messages[0]["content"]
        return {"raw_feedback": "I'm a bit worried, doctor.", "provider_failure": False}

    monkeypatch.setattr(ai_scoring, "_call_ai", fake_call_ai)

    _run(ai_scoring.get_patient_response(CARD, [], "How do you feel about starting insulin?", setting=SETTING))

    prompt = captured["system_prompt"]
    assert "CONDITIONAL RESPONSES" in prompt
    assert "CONVERSATION PROGRESSION" in prompt
    assert "SCENARIO SETTING" in prompt
    assert SETTING in prompt
    assert "Amit Patel" in prompt


# ── Realtime voice path: _build_realtime_system_prompt ────────────────────

def test_realtime_prompt_receives_conditional_and_progression():
    prompt = srt._build_realtime_system_prompt(CARD, SETTING)

    assert "CONDITIONAL RESPONSES" in prompt
    assert "CONVERSATION PROGRESSION" in prompt
    assert "SCENARIO SETTING" in prompt
    assert SETTING in prompt
    assert "Amit Patel" in prompt


def test_realtime_prompt_still_works_without_setting_arg():
    """Signature added `setting` with a default -- existing single-arg
    callers/tests must keep working unchanged."""
    prompt = srt._build_realtime_system_prompt(CARD)

    assert "Amit Patel" in prompt
    assert "SCENARIO SETTING" not in prompt


# ── Both runtimes stay behaviorally equivalent ─────────────────────────────

def test_legacy_and_realtime_prompts_share_the_same_patient_facts(monkeypatch):
    captured = {}

    async def fake_call_ai(messages, *a, **kw):
        captured["system_prompt"] = messages[0]["content"]
        return {"raw_feedback": "ok", "provider_failure": False}

    monkeypatch.setattr(ai_scoring, "_call_ai", fake_call_ai)
    _run(ai_scoring.get_patient_response(CARD, [], "hello", setting=SETTING))
    legacy_prompt = captured["system_prompt"]

    realtime_prompt = srt._build_realtime_system_prompt(CARD, SETTING)

    facts = [
        "Amit Patel", "Type 2 diabetes", "Newly diagnosed, lives alone.",
        "mention of injections", "Is there another option besides insulin?",
        "Has been skipping his current medication",
        "When the nurse asks about self-injecting",
        "Say you dislike the idea and doubt you'll manage it.",
        "Initially show anxiety about starting insulin.",
        SETTING,
    ]
    for fact in facts:
        assert fact in legacy_prompt, f"missing from legacy prompt: {fact}"
        assert fact in realtime_prompt, f"missing from realtime prompt: {fact}"
