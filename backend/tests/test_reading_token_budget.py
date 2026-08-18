"""Part A production incident: Gemini hit finish_reason=MAX_TOKENS at the old
module-level 6000-token ceiling and got cut off mid-questions-array. Part A
now gets a higher ceiling (9000) via _resolve_max_tokens; Part B/C/Listening/
Grammar are pinned to prove they didn't move.

Covers both the pure selection function and the actual value _call_ai
receives from generate_draft(), so a future refactor that reintroduces
`_MAX_TOKENS_OVERRIDE.get(module, ...)` at the call site would fail these.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.draft_generator as draft_generator
from app.services import ai_registry
from app.services.draft_generator import _resolve_max_tokens


def _run(coro):
    return asyncio.run(coro)


# ── pure selection function ──────────────────────────────────────────

def test_reading_part_a_gets_9000():
    assert _resolve_max_tokens("reading", "A") == 9000


def test_reading_part_b_stays_6000():
    assert _resolve_max_tokens("reading", "B") == 6000


def test_reading_part_c_stays_6000():
    assert _resolve_max_tokens("reading", "C") == 6000


def test_reading_part_none_preserves_existing_default():
    assert _resolve_max_tokens("reading", None) == 6000


def test_listening_unaffected():
    assert _resolve_max_tokens("listening", None) == 6000


def test_grammar_unaffected():
    assert _resolve_max_tokens("grammar", None) == 6000


def test_non_overridden_module_falls_back_to_default():
    assert _resolve_max_tokens("speaking", None) == 3000


# ── regression: bumping Part A must not move B/C ────────────────────

def test_part_a_override_is_isolated_from_part_b_and_c():
    assert _resolve_max_tokens("reading", "A") != _resolve_max_tokens("reading", "B")
    assert _resolve_max_tokens("reading", "B") == _resolve_max_tokens("reading", "C")


# ── integration: the actual max_tokens argument _call_ai receives ──────

_MATCH_OPTIONS = ["Text A", "Text B", "Text C", "Text D"]
_BODY = "Text A:\nfirst text\n\nText B:\nsecond text\n\nText C:\nthird text\n\nText D:\nfourth text"


def _match_q(n, answer="Text B"):
    return {"content": f"In which text is topic {n} mentioned?", "type": "mcq", "options": list(_MATCH_OPTIONS), "correct_answer": answer}


def _short_q(n):
    return {"content": f"question {n}", "type": "short_answer", "options": [], "correct_answer": f"answer {n}"}


def _valid_part_a_content():
    questions = [_match_q(n) for n in range(1, 6)] + [_short_q(n) for n in range(6, 21)]
    return {"title": "Infection control", "part": "A", "body": _BODY, "questions": questions}


def _valid_part_b_content():
    passages = [
        {
            "title": f"Extract {n}", "body": f"Body text for extract {n}.",
            "questions": [{
                "content": f"What does extract {n} say?", "type": "mcq",
                "options": ["Option A", "Option B", "Option C"], "correct_answer": "Option B",
            }],
        }
        for n in range(1, 7)
    ]
    return {"part": "B", "passages": passages}


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


def _patch_ai(monkeypatch, content: dict, captured: dict):
    async def fake_call_ai(*a, **kw):
        captured["max_tokens"] = kw.get("max_tokens")
        return dict(content)

    async def fake_get_model_config(purpose):
        raise ai_registry.PurposeNotConfigured("no model configured in tests")

    monkeypatch.setattr(draft_generator, "_call_ai", fake_call_ai)
    monkeypatch.setattr(ai_registry, "get_model_config", fake_get_model_config)
    monkeypatch.setattr(draft_generator, "get_supabase", lambda: _FakeDupCheckSupabase())


def test_generate_draft_part_a_calls_call_ai_with_9000(monkeypatch):
    captured = {}
    _patch_ai(monkeypatch, _valid_part_a_content(), captured)

    _run(draft_generator.generate_draft(
        module="reading", difficulty="intermediate", specialty="cardiology",
        topic="heart failure", part="A",
    ))

    assert captured["max_tokens"] == 9000


def test_generate_draft_part_b_calls_call_ai_with_6000(monkeypatch):
    captured = {}
    _patch_ai(monkeypatch, _valid_part_b_content(), captured)

    _run(draft_generator.generate_draft(
        module="reading", difficulty="intermediate", specialty="cardiology",
        topic="heart failure", part="B",
    ))

    assert captured["max_tokens"] == 6000
