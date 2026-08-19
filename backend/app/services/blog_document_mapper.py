"""Pure Blog draft -> Sanity document mapper (Module 1 Section 12A).

build_blog_sanity_document() is the only export. It takes a plain draft
dict (the generated_content_drafts row shape draft_store.py already
returns) and returns a Sanity document dict -- no Sanity call, no Supabase
call, no env access, no clock read. Same inputs always produce the same
output; the caller supplies any timestamp (publish_time /
existing_published_at) explicitly rather than this module calling
datetime.now() internally.

Deliberately does not import app.routers.admin_content_studio (it pulls in
FastAPI at import time, which a pure mapper must never do) or
app.services.draft_publisher (existing Postgres-module publisher, untouched
by this section) -- see _SLUG_RE below for the one piece of validation that
is duplicated rather than imported for that reason.
"""
import re
from typing import Any, Optional

from app.services.markdown_to_portable_text import markdown_to_portable_text
from app.services.sanity_client import sanity_blog_document_id


class BlogDocumentValidationError(Exception):
    """Draft is missing or has invalid data required to build a Sanity document."""


# Mirrors app/routers/admin_content_studio.py's _SLUG_RE exactly. Not
# imported from there because that module imports fastapi at module load,
# which this pure mapper must never pull in (Section 12A Step 12).
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SLUG_MAX_LEN = 200
_EXCERPT_MAX_LEN = 200


def build_blog_sanity_document(
    draft: dict,
    *,
    existing_published_at: Optional[str] = None,
    publish_time: Optional[str] = None,
) -> dict:
    generated_content = draft.get("generated_content") or {}

    title = generated_content.get("title")
    if not isinstance(title, str) or not title.strip():
        raise BlogDocumentValidationError("Blog document requires a non-empty title")

    slug = draft.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise BlogDocumentValidationError("Blog document requires a non-empty slug")
    if len(slug) > _SLUG_MAX_LEN or not _SLUG_RE.match(slug):
        raise BlogDocumentValidationError(
            "Blog document slug must be lowercase letters, numbers, and hyphens only, max 200 chars"
        )

    excerpt = draft.get("excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip():
        raise BlogDocumentValidationError("Blog document requires a non-empty excerpt")
    if len(excerpt) > _EXCERPT_MAX_LEN:
        raise BlogDocumentValidationError(f"Blog document excerpt must be at most {_EXCERPT_MAX_LEN} characters")

    # UnsupportedImageError / UnsupportedTableError / MarkdownConversionError
    # propagate as-is -- they're already controlled, admin-safe exceptions.
    body = markdown_to_portable_text(generated_content.get("body"))
    if not body:
        raise BlogDocumentValidationError("Blog document body must produce at least one Portable Text block")

    published_at = existing_published_at or publish_time
    if not published_at:
        raise BlogDocumentValidationError("Blog document requires publish_time on first publish")

    doc_id = sanity_blog_document_id(draft.get("id"))

    document: dict[str, Any] = {
        "_id": f"drafts.{doc_id}",
        "_type": "post",
        "title": title,
        "slug": {"_type": "slug", "current": slug},
        "excerpt": excerpt,
        "publishedAt": published_at,
        "body": body,
    }

    cover_image_ref = draft.get("cover_image_ref")
    if cover_image_ref:
        document["coverImage"] = {
            "_type": "image",
            "asset": {"_type": "reference", "_ref": cover_image_ref},
        }

    return document
