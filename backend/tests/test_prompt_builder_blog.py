"""Blog AI Generator Phase 1 -- prompt_builder.build_blog_prompt registration
and content. Prompt-string assertions only, no AI calls.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import prompt_builder
from app.services.prompt_builder import build_blog_prompt, build_prompt

KWARGS = dict(difficulty="intermediate", specialty="general", topic="OET Speaking role play tips")


def test_blog_registered_in_builders():
    assert prompt_builder.BUILDERS["blog"] is build_blog_prompt


def test_build_prompt_dispatches_to_blog():
    system, user = build_prompt("blog", **KWARGS)
    assert "OET Speaking role play tips" in user
    assert system  # non-empty system header


def test_blog_prompt_requests_structured_fields():
    _, user = build_blog_prompt(**KWARGS)
    assert '"title"' in user
    assert '"excerpt"' in user
    assert '"body"' in user
    assert "Markdown" in user


def test_blog_prompt_includes_instructions_when_given():
    _, user = build_blog_prompt(**KWARGS, instructions="Focus on nervous first-time candidates")
    assert "Focus on nervous first-time candidates" in user


def test_blog_prompt_omits_instructions_line_when_absent():
    _, user = build_blog_prompt(**KWARGS)
    assert "Additional instructions:" not in user


def test_blog_prompt_forbids_meta_commentary_and_slug():
    _, user = build_blog_prompt(**KWARGS)
    assert "slug" in user.lower()
    assert "AI-generated" in user or "AI generated" in user
    assert "code fence" in user.lower()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
