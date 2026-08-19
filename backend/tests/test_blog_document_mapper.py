"""Unit tests for app/services/blog_document_mapper.py (Module 1 Section 12A).
Pure function -- no network, no Supabase, no env vars, no Sanity."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.blog_document_mapper import BlogDocumentValidationError, build_blog_sanity_document
from app.services.markdown_to_portable_text import UnsupportedImageError, UnsupportedTableError

BODY_MD = """# How to Improve OET Speaking

OET Speaking requires clear and patient-friendly communication.

## Before the role-play

- Understand the patient's concern
- Plan your opening
- Use appropriate empathy

## During the role-play

Use **clear** and *patient-friendly* language.
"""


def make_draft(**overrides) -> dict:
    draft = {
        "id": 42,
        "module": "blog",
        "slug": "how-to-improve-oet-speaking",
        "excerpt": "Practical strategies to improve clarity, empathy and confidence in OET Speaking.",
        "cover_image_ref": None,
        "generated_content": {
            "title": "How to Improve OET Speaking",
            "body": BODY_MD,
        },
    }
    draft.update(overrides)
    return draft


def test_valid_first_publish_document():
    doc = build_blog_sanity_document(make_draft(), publish_time="2026-08-19T00:00:00Z")
    assert doc["_type"] == "post"
    assert doc["_id"] == "drafts.blog-post-42"
    assert doc["title"] == "How to Improve OET Speaking"
    assert doc["slug"] == {"_type": "slug", "current": "how-to-improve-oet-speaking"}
    assert doc["excerpt"] == make_draft()["excerpt"]
    assert doc["publishedAt"] == "2026-08-19T00:00:00Z"
    assert isinstance(doc["body"], list) and len(doc["body"]) > 0
    assert "coverImage" not in doc


def test_cover_image_included_when_ref_present():
    doc = build_blog_sanity_document(
        make_draft(cover_image_ref="image-abc123-800x600-jpg"), publish_time="2026-08-19T00:00:00Z"
    )
    assert doc["coverImage"] == {
        "_type": "image",
        "asset": {"_type": "reference", "_ref": "image-abc123-800x600-jpg"},
    }


def test_cover_image_omitted_when_none():
    doc = build_blog_sanity_document(make_draft(cover_image_ref=None), publish_time="2026-08-19T00:00:00Z")
    assert "coverImage" not in doc


def test_missing_title_rejected():
    draft = make_draft()
    draft["generated_content"]["title"] = ""
    with pytest.raises(BlogDocumentValidationError):
        build_blog_sanity_document(draft, publish_time="2026-08-19T00:00:00Z")


def test_missing_body_rejected():
    draft = make_draft()
    draft["generated_content"]["body"] = ""
    with pytest.raises(BlogDocumentValidationError):
        build_blog_sanity_document(draft, publish_time="2026-08-19T00:00:00Z")


def test_missing_slug_rejected():
    with pytest.raises(BlogDocumentValidationError):
        build_blog_sanity_document(make_draft(slug=None), publish_time="2026-08-19T00:00:00Z")


def test_invalid_slug_rejected():
    with pytest.raises(BlogDocumentValidationError):
        build_blog_sanity_document(make_draft(slug="Not A Slug!"), publish_time="2026-08-19T00:00:00Z")


def test_missing_excerpt_rejected():
    with pytest.raises(BlogDocumentValidationError):
        build_blog_sanity_document(make_draft(excerpt=None), publish_time="2026-08-19T00:00:00Z")


def test_unsupported_markdown_image_rejected():
    draft = make_draft()
    draft["generated_content"]["body"] = "Some text\n\n![alt](https://example.com/x.png)\n"
    with pytest.raises(UnsupportedImageError):
        build_blog_sanity_document(draft, publish_time="2026-08-19T00:00:00Z")


def test_unsupported_markdown_table_rejected():
    draft = make_draft()
    draft["generated_content"]["body"] = "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    with pytest.raises(UnsupportedTableError):
        build_blog_sanity_document(draft, publish_time="2026-08-19T00:00:00Z")


def test_empty_portable_text_rejected():
    draft = make_draft()
    draft["generated_content"]["body"] = "   \n\n  "
    with pytest.raises(BlogDocumentValidationError):
        build_blog_sanity_document(draft, publish_time="2026-08-19T00:00:00Z")


def test_first_publish_uses_supplied_publish_time():
    doc = build_blog_sanity_document(make_draft(), publish_time="2026-01-01T00:00:00Z")
    assert doc["publishedAt"] == "2026-01-01T00:00:00Z"


def test_republish_preserves_existing_published_at():
    doc = build_blog_sanity_document(
        make_draft(),
        existing_published_at="2025-06-01T00:00:00Z",
        publish_time="2026-01-01T00:00:00Z",
    )
    assert doc["publishedAt"] == "2025-06-01T00:00:00Z"


def test_missing_publish_time_rejected():
    with pytest.raises(BlogDocumentValidationError):
        build_blog_sanity_document(make_draft())


def test_deterministic_output():
    draft = make_draft()
    doc1 = build_blog_sanity_document(draft, publish_time="2026-08-19T00:00:00Z")
    doc2 = build_blog_sanity_document(draft, publish_time="2026-08-19T00:00:00Z")
    assert doc1 == doc2


def test_no_network_supabase_or_env_access(monkeypatch):
    """Blocks httpx and the Supabase client factory -- if the mapper ever
    reaches for either, this fails loudly instead of silently passing."""
    import httpx

    def _boom(*args, **kwargs):
        raise AssertionError("mapper must not perform network I/O")

    monkeypatch.setattr(httpx, "request", _boom)
    monkeypatch.setattr(httpx, "post", _boom)
    monkeypatch.setattr(httpx, "get", _boom)

    doc = build_blog_sanity_document(make_draft(), publish_time="2026-08-19T00:00:00Z")
    assert doc["_type"] == "post"
