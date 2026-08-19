"""Phase 3B-5 -- wires Content Studio's `part` field from the API request
through draft_generator -> prompt_builder -> the Part A structural
validator. No Gemini/AI calls: _call_ai is monkeypatched throughout, same
style as test_speaking_chat_ai_failure.py.

Covers the five cases from the phase brief:
  1. Reading + part="A" reaches build_reading_prompt(part="A") and the
     Part A validator.
  2. part omitted -> identical to pre-existing behavior.
  3. An invalid part value is rejected at the request-schema boundary,
     never silently coerced.
  4. Non-reading modules are unaffected by `part`.
  5. The prompt-builder dispatch (build_prompt) selects the Part A branch.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from pydantic import ValidationError

import app.services.draft_generator as draft_generator
from app.services import ai_registry, prompt_builder
from app.routers.admin_content_studio import GenerateDraftsRequest

_MATCH_OPTIONS = ["Text A", "Text B", "Text C", "Text D"]
_BODY = "Text A:\nfirst text\n\nText B:\nsecond text\n\nText C:\nthird text\n\nText D:\nfourth text"


def _run(coro):
    return asyncio.run(coro)


def _match_q(n, answer="Text B"):
    return {"content": f"In which text is topic {n} mentioned?", "type": "mcq", "options": list(_MATCH_OPTIONS), "correct_answer": answer}


def _short_q(n):
    return {"content": f"question {n}", "type": "short_answer", "options": [], "correct_answer": f"answer {n}"}


def _valid_part_a_content():
    questions = [_match_q(n) for n in range(1, 6)] + [_short_q(n) for n in range(6, 21)]
    return {"title": "Infection control", "part": "A", "body": _BODY, "questions": questions}


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


# ── 1. Part A request reaches the prompt builder and validator ──────────

def test_generate_draft_part_a_selects_part_a_prompt_and_passes_validation(monkeypatch):
    _patch_ai(monkeypatch, _valid_part_a_content())

    result = _run(draft_generator.generate_draft(
        module="reading", difficulty="intermediate", specialty="cardiology",
        topic="heart failure", part="A",
    ))

    assert "Reading Part A" in result["prompt"]["user_prompt"]
    assert "Text A" in result["prompt"]["user_prompt"]
    assert result["generated_content"]["part"] == "A"
    assert result["validation_warnings"] == []


def _valid_part_b_content():
    passages = [
        {
            "title": f"Extract {n}",
            "body": f"Body text for extract {n}.",
            "questions": [{
                "content": f"What does extract {n} say?", "type": "mcq",
                "options": ["Option A", "Option B", "Option C"], "correct_answer": "Option B",
            }],
        }
        for n in range(1, 7)
    ]
    return {"part": "B", "passages": passages}


def test_generate_draft_part_b_selects_part_b_prompt_and_passes_validation(monkeypatch):
    """Phase 4A -- proves part="B" reaches build_reading_prompt(part="B") and
    the Part B structural validator, mirroring the Part A wiring test above."""
    _patch_ai(monkeypatch, _valid_part_b_content())

    result = _run(draft_generator.generate_draft(
        module="reading", difficulty="intermediate", specialty="cardiology",
        topic="heart failure", part="B",
    ))

    assert "Reading Part B" in result["prompt"]["user_prompt"]
    assert "EXACTLY 6" in result["prompt"]["user_prompt"]
    assert result["generated_content"]["part"] == "B"
    assert result["validation_warnings"] == []


def test_generate_draft_part_b_structural_violation_still_raises(monkeypatch):
    """Proves the Part B validator is actually wired in, not bypassed --
    a malformed AI response (wrong passage count) must still fail."""
    broken = _valid_part_b_content()
    broken["passages"] = broken["passages"][:5]
    _patch_ai(monkeypatch, broken)

    with pytest.raises(draft_generator.DraftGenerationError, match="locked contract"):
        _run(draft_generator.generate_draft(
            module="reading", difficulty="intermediate", specialty="cardiology",
            topic="heart failure", part="B",
        ))


def test_generate_draft_part_a_structural_violation_still_raises(monkeypatch):
    """Proves the Part A validator is actually wired in, not bypassed --
    a malformed AI response (wrong question count) must still fail."""
    broken = _valid_part_a_content()
    broken["questions"] = broken["questions"][:19]
    _patch_ai(monkeypatch, broken)

    with pytest.raises(draft_generator.DraftGenerationError, match="locked contract"):
        _run(draft_generator.generate_draft(
            module="reading", difficulty="intermediate", specialty="cardiology",
            topic="heart failure", part="A",
        ))


def _valid_part_c_content():
    texts = [
        {
            "title": f"Feature {n}",
            "body": f"Long-form journalistic body text for feature {n}.",
            "questions": [{
                "content": f"What does feature {n} question {q} ask?", "type": "mcq",
                "options": ["Option A", "Option B", "Option C", "Option D"], "correct_answer": "Option B",
            } for q in range(1, 9)],
        }
        for n in range(1, 3)
    ]
    return {"part": "C", "texts": texts}


def test_generate_draft_part_c_selects_part_c_prompt_and_passes_validation(monkeypatch):
    """Phase 4C-3 -- proves part="C" reaches build_reading_prompt(part="C") and
    the Part C structural validator, mirroring the Part A/B wiring tests above."""
    _patch_ai(monkeypatch, _valid_part_c_content())

    result = _run(draft_generator.generate_draft(
        module="reading", difficulty="intermediate", specialty="cardiology",
        topic="heart failure", part="C",
    ))

    assert "Reading Part C" in result["prompt"]["user_prompt"]
    assert "EXACTLY 2" in result["prompt"]["user_prompt"]
    assert result["generated_content"]["part"] == "C"
    assert result["validation_warnings"] == []


def test_generate_draft_part_c_structural_violation_still_raises(monkeypatch):
    """Proves the Part C validator is actually wired in, not bypassed --
    a malformed AI response (wrong text count) must still fail."""
    broken = _valid_part_c_content()
    broken["texts"] = broken["texts"][:1]
    _patch_ai(monkeypatch, broken)

    with pytest.raises(draft_generator.DraftGenerationError, match="locked contract"):
        _run(draft_generator.generate_draft(
            module="reading", difficulty="intermediate", specialty="cardiology",
            topic="heart failure", part="C",
        ))


# ── 2. part omitted -> unchanged existing behavior ───────────────────────

def test_generate_draft_part_omitted_uses_default_reading_prompt(monkeypatch):
    # part="Z" here is incidental (any value that isn't "A"/"B"/"C", which now
    # all carry real structural meaning) -- this test only pins that a part=None
    # *request* still reaches the generic prompt branch and validates clean.
    default_content = {"title": "t", "part": "Z", "body": "a passage", "questions": [_short_q(1)]}
    _patch_ai(monkeypatch, default_content)

    result = _run(draft_generator.generate_draft(
        module="reading", difficulty="intermediate", specialty="cardiology", topic="heart failure",
    ))

    assert "Part A" not in result["prompt"]["user_prompt"]
    assert "roughly 700-900 words" in result["prompt"]["user_prompt"]
    assert result["validation_warnings"] == []


# ── 3. invalid part value is rejected, not silently coerced ─────────────

def test_request_schema_rejects_invalid_reading_part():
    with pytest.raises(ValidationError, match="part must be one of"):
        GenerateDraftsRequest(module="reading", difficulty="intermediate", specialty="cardiology", topic="x", part="D")


def test_request_schema_accepts_part_a():
    req = GenerateDraftsRequest(module="reading", difficulty="intermediate", specialty="cardiology", topic="x", part="A")
    assert req.part == "A"


def test_request_schema_accepts_part_b():
    req = GenerateDraftsRequest(module="reading", difficulty="intermediate", specialty="cardiology", topic="x", part="B")
    assert req.part == "B"


def test_request_schema_accepts_part_c():
    req = GenerateDraftsRequest(module="reading", difficulty="intermediate", specialty="cardiology", topic="x", part="C")
    assert req.part == "C"


def test_request_schema_accepts_omitted_part():
    req = GenerateDraftsRequest(module="reading", difficulty="intermediate", specialty="cardiology", topic="x")
    assert req.part is None


# ── 4. non-reading modules unaffected ────────────────────────────────────

@pytest.mark.parametrize("module", ["speaking", "listening", "writing", "vocab", "grammar"])
def test_request_schema_ignores_part_for_non_reading_modules(module):
    """`part` is meaningless outside Reading -- an arbitrary value must not
    be rejected (there's nothing for it to violate) and must not be
    forwarded anywhere that would error."""
    req = GenerateDraftsRequest(module=module, difficulty="intermediate", specialty="cardiology", topic="x", part="A")
    assert req.part == "A"  # accepted, but see below: prompt_builder never sees it


def test_build_prompt_does_not_forward_part_to_non_reading_builders(monkeypatch):
    """build_speaking_prompt (and friends) don't take a `part` kwarg -- if
    build_prompt ever forwarded it, this would raise TypeError."""
    system_prompt, user_prompt = prompt_builder.build_prompt(
        "speaking", "intermediate", "cardiology", "chest pain", part="A",
    )
    assert "part" not in user_prompt.lower().split("difficulty")[0]  # sanity: didn't inject anything odd
    assert system_prompt  # built successfully, no TypeError


# ── 5. prompt-builder dispatch selects the Part A branch ────────────────

def test_build_prompt_dispatches_part_a_branch():
    _, user = prompt_builder.build_prompt("reading", "intermediate", "cardiology", "heart failure", part="A")
    for marker in ["Reading Part A", "Text A", "Text B", "Text C", "Text D", "short_answer"]:
        assert marker in user


def test_build_prompt_dispatches_default_branch_when_part_none():
    _, user = prompt_builder.build_prompt("reading", "intermediate", "cardiology", "heart failure")
    assert "Part A" not in user
    assert "roughly 700-900 words" in user


def test_build_prompt_dispatches_part_c_branch():
    _, user = prompt_builder.build_prompt("reading", "intermediate", "cardiology", "heart failure", part="C")
    for marker in ["Reading Part C", "EXACTLY 2", "EXACTLY 8", "mcq", "options"]:
        assert marker in user


# ── 6. Listening (Phase 3E) -- part is required, not merely validated ────
# Unlike Reading (part omitted -> legacy generic passage), Listening's
# dedicated Part A/B/C generator has no such fallback -- every generation
# through this endpoint must pick one of the three locked contracts.

def test_request_schema_requires_part_for_listening():
    with pytest.raises(ValidationError, match="part must be one of"):
        GenerateDraftsRequest(module="listening", difficulty="intermediate", specialty="cardiology", topic="x")


def test_request_schema_rejects_invalid_listening_part():
    with pytest.raises(ValidationError, match="part must be one of"):
        GenerateDraftsRequest(module="listening", difficulty="intermediate", specialty="cardiology", topic="x", part="D")


@pytest.mark.parametrize("part", ["A", "B", "C"])
def test_request_schema_accepts_valid_listening_parts(part):
    req = GenerateDraftsRequest(module="listening", difficulty="intermediate", specialty="cardiology", topic="x", part=part)
    assert req.part == part


def test_build_prompt_dispatches_listening_part_a_branch():
    _, user = prompt_builder.build_prompt("listening", "intermediate", "cardiology", "chest pain", part="A")
    for marker in ["Listening Part A", "EXACTLY 2", "EXACTLY 12", "short_answer"]:
        assert marker in user


def _valid_listening_part_a_content():
    extracts = [{
        "title": f"Extract {n}",
        "transcript": [{"speaker": "Nurse", "text": "hi"}],
        "body": f"Extract {n} notes\n1. blank ______",
        "questions": [
            {"content": f"Extract {n} blank ({b})", "type": "short_answer", "options": [], "correct_answer": f"answer {n}-{b}"}
            for b in range(1, 13)
        ],
    } for n in range(1, 3)]
    return {"part": "A", "prep_seconds": 30, "audio_mode": "dialogue", "extracts": extracts}


def test_generate_draft_listening_part_a_selects_part_a_prompt_and_passes_validation(monkeypatch):
    """Mirrors test_generate_draft_part_a_selects_part_a_prompt_and_passes_validation
    above, but for Listening's dedicated Part A generator (Phase 3B/3E)."""
    _patch_ai(monkeypatch, _valid_listening_part_a_content())

    result = _run(draft_generator.generate_draft(
        module="listening", difficulty="intermediate", specialty="cardiology",
        topic="ENT", part="A",
    ))

    assert "Listening Part A" in result["prompt"]["user_prompt"]
    assert result["generated_content"]["part"] == "A"
    assert result["validation_warnings"] == []


def test_generate_draft_listening_part_a_structural_violation_still_raises(monkeypatch):
    broken = _valid_listening_part_a_content()
    broken["extracts"][0]["questions"] = broken["extracts"][0]["questions"][:11]
    _patch_ai(monkeypatch, broken)

    with pytest.raises(draft_generator.DraftGenerationError, match="locked contract"):
        _run(draft_generator.generate_draft(
            module="listening", difficulty="intermediate", specialty="cardiology",
            topic="ENT", part="A",
        ))
