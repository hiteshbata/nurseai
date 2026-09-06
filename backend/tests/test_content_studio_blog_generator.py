"""Blog AI Generator (Content Studio "generate" screen extended to Blog).

Blog reuses the existing /generate + /drafts endpoints and the existing
draft lifecycle unchanged -- generation only ever returns an unpersisted
preview (see draft_generator.generate_draft's docstring), never calls
/publish, and Save Draft always lands a normal status='draft' row via the
existing draft_store.create_draft path. No Gemini/TTS/DB writes: _call_ai is
faked directly (same style as test_content_studio_writing.py).
"""
import asyncio

from app.services import ai_registry, draft_generator, prompt_builder


def _run(coro):
    return asyncio.run(coro)


class _FakeDupCheckSupabase:
    """No production rows ever match -- duplicate-title check is a no-op.
    Blog has no entry in _DUPLICATE_CHECK_TABLE anyway (no production blog
    content table -- Blog publishes to Sanity, not a Supabase table), so
    this is only here because generate_draft() always calls get_supabase()."""

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


def _blog_content(**overrides):
    content = {
        "title": "OET Speaking Role-Play Tips for Nurses",
        "excerpt": "A practical guide to acing the OET Speaking role-play.",
        "body": "## Introduction\n\nSome substantial markdown body content about OET Speaking role-play technique.",
    }
    content.update(overrides)
    return content


# ── 1. Blog prompt builder ────────────────────────────────────────────────

def test_build_blog_prompt_includes_topic_and_schema_fields():
    system, user = prompt_builder.build_blog_prompt(
        "intermediate", "general", "OET Speaking role-play tips for nurses",
    )
    assert "OET" in system
    assert "OET Speaking role-play tips for nurses" in user
    for marker in ("title", "excerpt", "body"):
        assert marker in user


def test_build_blog_prompt_includes_additional_instructions_when_given():
    _, user = prompt_builder.build_blog_prompt(
        "intermediate", "general", "OET Speaking role-play tips for nurses",
        instructions="Include a role-play framework and common mistakes.",
    )
    assert "Include a role-play framework and common mistakes." in user


def test_build_blog_prompt_omits_instructions_line_when_not_given():
    _, user = prompt_builder.build_blog_prompt("intermediate", "general", "some topic")
    assert "Additional instructions:" not in user


# ── 2. Blog registered in BUILDERS / dispatchable via build_prompt ────────

def test_blog_registered_in_builders():
    assert prompt_builder.BUILDERS["blog"] is prompt_builder.build_blog_prompt


def test_build_prompt_dispatches_blog_module():
    system, user = prompt_builder.build_prompt("blog", "intermediate", "general", "some topic")
    assert "some topic" in user


# ── 3. Required-field validation (generic _REQUIRED_FIELDS path) ─────────

def test_blog_required_fields_registered():
    assert draft_generator._REQUIRED_FIELDS["blog"] == ["title", "body", "excerpt"]


def test_missing_title_fails():
    errors_raised = False
    try:
        draft_generator._validate("blog", _blog_content(title=""))
    except draft_generator.DraftGenerationError as e:
        errors_raised = True
        assert "title" in str(e)
    assert errors_raised


def test_missing_body_fails():
    errors_raised = False
    try:
        draft_generator._validate("blog", _blog_content(body=""))
    except draft_generator.DraftGenerationError as e:
        errors_raised = True
        assert "body" in str(e)
    assert errors_raised


def test_missing_excerpt_fails():
    errors_raised = False
    try:
        draft_generator._validate("blog", _blog_content(excerpt=""))
    except draft_generator.DraftGenerationError as e:
        errors_raised = True
        assert "excerpt" in str(e)
    assert errors_raised


def test_valid_blog_content_passes_validation():
    assert draft_generator._validate("blog", _blog_content()) == []


# ── 4. End-to-end generation succeeds with valid structured output ───────

def test_generate_draft_succeeds_with_valid_blog_output(monkeypatch):
    _patch_ai(monkeypatch, _blog_content())

    result = _run(draft_generator.generate_draft(
        module="blog", difficulty="intermediate", specialty="general",
        topic="OET Speaking role-play tips for nurses",
    ))

    content = result["generated_content"]
    assert content["title"] == "OET Speaking Role-Play Tips for Nurses"
    assert content["excerpt"]
    assert content["body"]
    assert result["validation_warnings"] == []
    assert result["ai_title"] == content["title"]


def test_generate_draft_never_persists_or_publishes(monkeypatch):
    """generate_draft returns a plain dict -- it must not touch draft_store
    (no persistence) and there is no publish call reachable from this
    function at all (draft_publisher is never imported/used here)."""
    _patch_ai(monkeypatch, _blog_content())

    result = _run(draft_generator.generate_draft(
        module="blog", difficulty="intermediate", specialty="general", topic="a topic",
    ))

    assert set(result.keys()) == {"generated_content", "metadata", "prompt", "validation_warnings", "ai_title", "model_used"}
    assert "id" not in result
    assert "status" not in result


def test_generate_draft_missing_required_field_raises_draft_generation_error(monkeypatch):
    _patch_ai(monkeypatch, _blog_content(excerpt=""))

    raised = False
    try:
        _run(draft_generator.generate_draft(
            module="blog", difficulty="intermediate", specialty="general", topic="a topic",
        ))
    except draft_generator.DraftGenerationError as e:
        raised = True
        assert "excerpt" in str(e)
    assert raised
