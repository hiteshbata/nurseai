"""Blog draft -> Sanity DRAFT document (Module 1 Section 12B), and Sanity
DRAFT -> Sanity PUBLISHED document (Module 1 Section 12C). Neither section
touches Supabase, writes audit logs, or changes draft status -- the caller
(router) owns workflow state and is responsible for checking the draft is
'approved' before calling this, same as draft_publisher.publish() leaves
status validation to its router rather than re-checking it here.

create_sanity_draft() is intentionally just build_blog_sanity_document() +
sanity_client.create_or_replace_document() wired together -- see those two
modules for the mapping/validation and HTTP/error-handling logic, both
reused as-is, not duplicated here.

publish_sanity_draft() (12C) promotes that Sanity draft to the published
document via sanity_client.publish_document(), then confirms via
get_document() -- see BlogPublicationUncertainError below for why a missing
or unreachable confirmation is never treated as "publish failed".
"""
import time
from typing import Any, Optional

from app.services.blog_document_mapper import build_blog_sanity_document
from app.services.sanity_client import (
    SanityAPIError,
    SanityAuthError,
    SanityInvalidRequestError,
    SanityNetworkError,
    SanityRateLimitError,
    create_or_replace_document,
    get_document,
    publish_document,
    sanity_blog_document_id,
)

# Sanity's mutate API reports "create"/"update"; the result contract here
# uses "created"/"updated" to match publish_document's own action naming.
_OPERATION_LABELS = {"create": "created", "update": "updated"}


class BlogPublicationError(Exception):
    """Publish action definitely failed -- Sanity returned a response
    rejecting it (auth/invalid-request/rate-limit/server error). The Sanity
    draft is untouched and safe to retry; nothing was promoted to published."""


class BlogPublicationUncertainError(Exception):
    """Publish outcome is unknown, not "failed": the publish request timed
    out before a response arrived, or the request succeeded but
    get_document() couldn't confirm the published document (missing,
    mismatched, or itself unreachable). The caller must not assume the
    document is unpublished and must not retry blindly -- see Module 1
    Section 12D (not implemented here) for reconciliation."""


# Actions API responses aren't documented as guaranteeing the published
# document is immediately readable via get_document() (unlike the mutate
# endpoint, which is synchronous) -- so confirmation gets a small bounded
# retry instead of trusting a single read or sleeping an arbitrary fixed
# amount. 3 attempts / 0.2s is a ceiling, not a tuned SLA.
_CONFIRM_MAX_ATTEMPTS = 3
_CONFIRM_RETRY_DELAY_SECONDS = 0.2

_CONTENT_FIELDS = ("title", "excerpt", "body", "publishedAt")


def _content_matches(existing: dict, intended: dict, published_id: str) -> bool:
    """True if `existing` (a document read back from Sanity) already has
    every field 12C would otherwise publish -- used both to detect an
    idempotent no-op publish (Case G) and to confirm a just-published
    document (Step 6). Ignores Sanity system metadata (_rev/_createdAt/
    _updatedAt) per Step 12."""
    if existing.get("_id") != published_id or existing.get("_type") != "post":
        return False
    if existing.get("slug") != intended.get("slug"):
        return False
    if existing.get("coverImage") != intended.get("coverImage"):
        return False
    return all(existing.get(field) == intended.get(field) for field in _CONTENT_FIELDS)


def create_sanity_draft(
    draft: dict,
    *,
    publish_time: Optional[str] = None,
    existing_published_at: Optional[str] = None,
) -> dict[str, Any]:
    """Builds the Sanity document for `draft` and createOrReplaces it as
    drafts.blog-post-{draft_id} -- never blog-post-{draft_id} (that's
    publish_document's job, Section 12C). Raises BlogDocumentValidationError
    (mapper) or a typed Sanity*Error (sanity_client) -- both propagate as-is,
    no Sanity call happens if the mapper raises first."""
    document = build_blog_sanity_document(
        draft, existing_published_at=existing_published_at, publish_time=publish_time,
    )
    draft_id = draft["id"]
    result = create_or_replace_document(draft_id, document)
    return {
        "draft_id": draft_id,
        "sanity_document_id": result.document_id,
        "sanity_draft_id": f"drafts.{sanity_blog_document_id(draft_id)}",
        "operation": _OPERATION_LABELS.get(result.operation, result.operation),
        "transaction_id": result.transaction_id,
    }


def _confirm_published(published_id: str, intended_document: dict, *, sleep) -> None:
    """Bounded-retry confirmation (Step 7): a missing document on the first
    read isn't treated as failure, but running out of attempts -- or a
    get_document() error at any point -- raises BlogPublicationUncertainError
    rather than being swallowed or retried forever."""
    last_seen: Optional[dict] = None
    for attempt in range(_CONFIRM_MAX_ATTEMPTS):
        if attempt:
            sleep(_CONFIRM_RETRY_DELAY_SECONDS)
        try:
            last_seen = get_document(published_id)
        except (SanityNetworkError, SanityAPIError, SanityAuthError, SanityInvalidRequestError, SanityRateLimitError) as exc:
            raise BlogPublicationUncertainError(
                f"Sanity publish for {published_id} may have succeeded, but confirmation failed: {exc}"
            ) from exc
        if last_seen is not None:
            break
    if last_seen is None:
        raise BlogPublicationUncertainError(
            f"Sanity publish action for {published_id} completed, but the published document was not "
            f"visible after {_CONFIRM_MAX_ATTEMPTS} confirmation attempts."
        )
    if not _content_matches(last_seen, intended_document, published_id):
        raise BlogPublicationUncertainError(
            f"Sanity publish action for {published_id} completed, but the confirmed document content "
            f"does not match what was published."
        )


def publish_sanity_draft(
    draft: dict,
    *,
    publish_time: Optional[str] = None,
    existing_published_at: Optional[str] = None,
    _sleep=time.sleep,
) -> dict[str, Any]:
    """Promotes the Sanity draft for `draft` to published (Module 1 Section
    12C): ensure the Sanity draft matches `draft`, publish it, confirm the
    published document. Never touches Supabase / draft status / audit logs
    -- see the module docstring and test_no_supabase_or_draft_store_import.

    Idempotency (Step 11/12): before writing anything, checks whether the
    published document already exists and already matches the intended
    content -- if so, returns immediately without a second Sanity draft
    write or a second publish action (Case G). If a published document
    exists but differs, this proceeds with the normal create-then-publish
    flow below (Option A: update + republish) rather than rejecting --
    build_blog_sanity_document's existing_published_at/publish_time split
    already exists specifically to support republishing approved edits, so
    refusing here would fight that design. A stricter policy is a 12D
    decision, not this section's.

    Raises BlogDocumentValidationError / UnsupportedImageError /
    UnsupportedTableError (mapper, via create_sanity_draft) if the draft
    fails to convert -- no Sanity call happens (Case A). Raises a typed
    Sanity*Error unchanged if the DRAFT write fails (Case B upstream half).
    Raises BlogPublicationError if the publish action itself is definitely
    rejected by Sanity (Case B). Raises BlogPublicationUncertainError if the
    publish request times out (Case E) or succeeds but confirmation can't
    prove it (Cases D/F) -- see that class's docstring.
    """
    draft_id = draft["id"]
    published_id = sanity_blog_document_id(draft_id)

    # Built once up front: used for both the idempotency pre-check below and
    # (via create_sanity_draft, which rebuilds it internally) the actual
    # Sanity draft write. Raises before any Sanity call if the draft is
    # invalid (Case A) -- publish_time is required so this cannot succeed
    # with a None publishedAt.
    intended_document = build_blog_sanity_document(
        draft, existing_published_at=existing_published_at, publish_time=publish_time,
    )

    existing_published = get_document(published_id)
    if existing_published is not None and _content_matches(existing_published, intended_document, published_id):
        return {
            "draft_id": draft_id,
            "sanity_document_id": published_id,
            "sanity_draft_id": f"drafts.{published_id}",
            "status": "published",
            "published_at": intended_document["publishedAt"],
            "transaction_id": None,
            "already_published": True,
        }

    create_sanity_draft(draft, publish_time=publish_time, existing_published_at=existing_published_at)

    try:
        publish_result = publish_document(draft_id)
    except SanityNetworkError as exc:
        raise BlogPublicationUncertainError(
            f"Sanity publish request for {published_id} did not receive a response (timeout/network "
            f"error); publication state is unknown. The Sanity draft was not deleted."
        ) from exc
    except (SanityAuthError, SanityInvalidRequestError, SanityRateLimitError, SanityAPIError) as exc:
        raise BlogPublicationError(f"Sanity publish action for {published_id} was rejected: {exc}") from exc

    _confirm_published(published_id, intended_document, sleep=_sleep)

    return {
        "draft_id": draft_id,
        "sanity_document_id": published_id,
        "sanity_draft_id": f"drafts.{published_id}",
        "status": "published",
        "published_at": intended_document["publishedAt"],
        "transaction_id": publish_result.transaction_id,
        "already_published": False,
    }
