"""Blog AI Generator Phase 1 -- draft_generator.generate_draft(module="blog").
No AI calls: _call_ai is monkeypatched, same style as
test_content_studio_part_wiring.py.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import app.services.draft_generator as draft_generator
from app.services import ai_registry


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


def _valid_blog_content():
    return {
        "title": "How Nurses Can Prepare for OET Speaking Role Plays",
        "excerpt": "Practical tips for nurses tackling the OET Speaking sub-test.",
        "body": "## Getting started\n\nSome useful Markdown content for candidates.",
    }


def test_generate_draft_blog_returns_title_excerpt_body(monkeypatch):
    _patch_ai(monkeypatch, _valid_blog_content())

    result = _run(draft_generator.generate_draft(
        module="blog", difficulty="intermediate", specialty="general",
        topic="OET Speaking role plays",
    ))

    assert result["generated_content"]["title"] == "How Nurses Can Prepare for OET Speaking Role Plays"
    assert result["generated_content"]["excerpt"]
    assert result["generated_content"]["body"]
    assert result["ai_title"] == "How Nurses Can Prepare for OET Speaking Role Plays"
    assert result["validation_warnings"] == []


def test_generate_draft_blog_missing_title_rejected(monkeypatch):
    broken = _valid_blog_content()
    del broken["title"]
    _patch_ai(monkeypatch, broken)

    with pytest.raises(draft_generator.DraftGenerationError, match="title"):
        _run(draft_generator.generate_draft(
            module="blog", difficulty="intermediate", specialty="general",
            topic="OET Speaking role plays",
        ))


def test_generate_draft_blog_missing_body_rejected(monkeypatch):
    broken = _valid_blog_content()
    del broken["body"]
    _patch_ai(monkeypatch, broken)

    with pytest.raises(draft_generator.DraftGenerationError, match="body"):
        _run(draft_generator.generate_draft(
            module="blog", difficulty="intermediate", specialty="general",
            topic="OET Speaking role plays",
        ))


def test_generate_draft_blog_missing_excerpt_rejected(monkeypatch):
    broken = _valid_blog_content()
    del broken["excerpt"]
    _patch_ai(monkeypatch, broken)

    with pytest.raises(draft_generator.DraftGenerationError, match="excerpt"):
        _run(draft_generator.generate_draft(
            module="blog", difficulty="intermediate", specialty="general",
            topic="OET Speaking role plays",
        ))


def test_blog_uses_prompt_builder_blog_branch(monkeypatch):
    _patch_ai(monkeypatch, _valid_blog_content())

    result = _run(draft_generator.generate_draft(
        module="blog", difficulty="intermediate", specialty="general",
        topic="OET Speaking role plays",
    ))

    assert "OET Speaking role plays" in result["prompt"]["user_prompt"]
    assert '"body"' in result["prompt"]["user_prompt"]


def test_other_modules_unaffected_by_blog_addition(monkeypatch):
    """Reading's required-field set (no 'excerpt') must be untouched by the
    blog entry added alongside it."""
    _patch_ai(monkeypatch, {"title": "t", "body": "b", "questions": [{"content": "q", "type": "mcq", "options": ["a", "b"], "correct_answer": "a"}]})

    result = _run(draft_generator.generate_draft(
        module="reading", difficulty="intermediate", specialty="general",
        topic="wound care",
    ))
    assert result["generated_content"]["title"] == "t"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
