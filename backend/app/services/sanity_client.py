"""Server-side Sanity Content API client for the future Blog Publisher
(Module 1 Section 5+). Deliberately isolated -- not wired into Content
Studio, draft_publisher, or any router yet (see Section 4 scope).

Uses Sanity's plain HTTP Content API (mutate + actions + doc endpoints)
rather than the @sanity/client SDK: httpx is already a backend dependency
and the two operations needed here (idempotent create/replace, Actions-API
publish/unpublish) don't justify adding one.

Draft/publish model (https://www.sanity.io/docs/http-actions-api): a
document id "drafts.<id>" is the unpublished/editable copy, invisible to
published-only queries; "<id>" (no prefix) is the public copy. Writing
straight to "<id>" would make content publicly visible immediately, so
create_or_replace_document() always targets the draft id -- only
publish_document() (via the Actions API's sanity.action.document.publish)
promotes draft -> published, matching what Sanity Studio's own Publish
button does. unpublish_document() is the Actions API's inverse
(published -> draft), not a delete.
"""
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.env_guard import SanityDatasetIsolationError as SanityDatasetIsolationError
from app.core.env_guard import verify_sanity_dataset_isolation

logger = logging.getLogger(__name__)

# Matches frontend/src/lib/sanity.ts's apiVersion -- keep both in sync.
SANITY_API_VERSION = "2026-07-01"

# Server-to-server call, same bound as app/services/alerts.py and email.py.
_REQUEST_TIMEOUT = 10.0

# Binary image uploads (up to COVER_IMAGE_MAX_BYTES in admin_content_studio.py)
# take longer than a small JSON mutation -- the 10s bound above is too tight.
_ASSET_UPLOAD_TIMEOUT = 20.0

# Sanity's Assets API accepts any image type, but this client only exposes the
# formats admin_content_studio.py's Blog cover-image endpoint allows in
# (Module 1 Section 11) -- see that router for the sniffed-bytes validation
# this content_type is checked against before it ever reaches here.
_IMAGE_ASSET_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

# generated_content_drafts.id is a Postgres bigserial -- only positive
# integers are ever real draft ids.
_DRAFT_ID_RE = re.compile(r"^[1-9][0-9]*$")

# Sanity document ids this client ever hands to a URL path: alphanumeric,
# underscore, dot, hyphen; must start with an alphanumeric char (blocks a
# leading "." or "-", which would otherwise let ".." or "-" gain meaning).
# No "/", "?", "#", or whitespace -- rules out path traversal, extra path
# segments, and query/fragment injection into the doc endpoint URL. Covers
# both ids this client generates itself (sanity_blog_document_id) and any
# other legitimate Sanity document id (e.g. "drafts.blog-post-123").
_DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class SanityConfigError(Exception):
    """SANITY_PROJECT_ID / SANITY_DATASET / SANITY_WRITE_TOKEN missing."""


class SanityAuthError(Exception):
    """401/403 from the Sanity API -- bad or missing write token."""


class SanityInvalidRequestError(Exception):
    """400/404 from the Sanity API -- malformed mutation/action, or the
    document/dataset doesn't exist."""


class SanityRateLimitError(Exception):
    """429 from the Sanity API."""


class SanityAPIError(Exception):
    """5xx, or any other non-2xx response, or a malformed response body."""


class SanityNetworkError(Exception):
    """Request never got a response -- timeout, connection error, DNS."""


def sanity_blog_document_id(draft_id: Any) -> str:
    """Deterministic Sanity document id for a generated_content_drafts row:
    blog-post-{draft_id}. Pure, no DB lookup -- same draft id always yields
    the same Sanity id (what makes create_or_replace_document idempotent),
    different draft ids always yield different ones. draft_id is validated
    as a positive integer rather than interpolated raw, so a malformed or
    attacker-controlled value can't produce an unexpected/invalid _id."""
    draft_id_str = str(draft_id).strip()
    if not _DRAFT_ID_RE.match(draft_id_str):
        raise ValueError(f"draft_id must be a positive integer, got {draft_id!r}")
    return f"blog-post-{draft_id_str}"


@dataclass
class SanityWriteResult:
    document_id: str
    operation: str  # "create" | "update" | "publish" | "unpublish"
    transaction_id: Optional[str] = None
    success: bool = True


def _require_config() -> tuple[str, str, str]:
    project_id, dataset, token = settings.SANITY_PROJECT_ID, settings.SANITY_DATASET, settings.SANITY_WRITE_TOKEN
    if not project_id or not dataset or not token:
        raise SanityConfigError("SANITY_PROJECT_ID, SANITY_DATASET and SANITY_WRITE_TOKEN must all be set.")
    # Fail closed rather than silently writing to the production Sanity
    # dataset from a non-production ENVIRONMENT (see app/core/env_guard.py --
    # same fail-closed pattern app/main.py already applies to Supabase).
    verify_sanity_dataset_isolation(settings.ENVIRONMENT, dataset)
    return project_id, dataset, token


def _validate_document_id(document_id: str) -> str:
    """Rejects anything that isn't a plain Sanity document id before it's
    interpolated into a URL path -- see _DOCUMENT_ID_RE."""
    if not document_id or not _DOCUMENT_ID_RE.match(document_id):
        raise SanityInvalidRequestError(f"Invalid Sanity document id: {document_id!r}")
    return document_id


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _raise_for_status(resp: httpx.Response, operation: str, document_id: str) -> None:
    if resp.status_code < 400:
        return
    logger.warning("sanity_client %s failed | document_id=%s status=%s", operation, document_id, resp.status_code)
    if resp.status_code in (401, 403):
        raise SanityAuthError(f"Sanity {operation} unauthorized (status {resp.status_code}).")
    if resp.status_code == 429:
        raise SanityRateLimitError(f"Sanity {operation} rate-limited.")
    if resp.status_code in (400, 404):
        raise SanityInvalidRequestError(f"Sanity {operation} rejected the request (status {resp.status_code}).")
    raise SanityAPIError(f"Sanity {operation} failed (status {resp.status_code}).")


def _request(method: str, url: str, token: str, operation: str, document_id: str, json_body: Optional[dict] = None) -> dict:
    try:
        resp = httpx.request(method, url, headers=_headers(token), json=json_body, timeout=_REQUEST_TIMEOUT)
    except httpx.TimeoutException as exc:
        logger.warning("sanity_client %s timed out | document_id=%s", operation, document_id)
        raise SanityNetworkError(f"Sanity {operation} timed out.") from exc
    except httpx.HTTPError as exc:
        logger.warning("sanity_client %s network error | document_id=%s error_type=%s", operation, document_id, type(exc).__name__)
        raise SanityNetworkError(f"Sanity {operation} network error.") from exc
    _raise_for_status(resp, operation, document_id)
    try:
        return resp.json()
    except ValueError as exc:
        raise SanityAPIError(f"Sanity {operation} returned a malformed response.") from exc


def create_or_replace_document(draft_id: Any, fields: dict) -> SanityWriteResult:
    """Idempotent create/replace of the DRAFT copy (drafts.blog-post-{draft_id}).
    Never touches the published id -- calling this twice for the same
    draft_id updates the same draft document in place, and never makes
    anything publicly visible (that's publish_document's job)."""
    project_id, dataset, token = _require_config()
    doc_id = sanity_blog_document_id(draft_id)
    draft_doc_id = f"drafts.{doc_id}"
    body = {**fields, "_id": draft_doc_id, "_type": "post"}
    url = f"https://{project_id}.api.sanity.io/v{SANITY_API_VERSION}/data/mutate/{dataset}"
    data = _request("POST", url, token, "create_or_replace_document", doc_id, {"mutations": [{"createOrReplace": body}]})
    results = data.get("results") or []
    operation = results[0].get("operation", "unknown") if results else "unknown"
    return SanityWriteResult(document_id=doc_id, operation=operation, transaction_id=data.get("transactionId"))


def publish_document(draft_id: Any) -> SanityWriteResult:
    """Promotes drafts.blog-post-{draft_id} to the public blog-post-{draft_id}
    via the Actions API's sanity.action.document.publish -- the same action
    Sanity Studio's Publish button performs, not a raw mutate/createOrReplace
    on the published id."""
    project_id, dataset, token = _require_config()
    doc_id = sanity_blog_document_id(draft_id)
    url = f"https://{project_id}.api.sanity.io/v{SANITY_API_VERSION}/data/actions/{dataset}"
    action = {"actionType": "sanity.action.document.publish", "draftId": f"drafts.{doc_id}", "publishedId": doc_id}
    data = _request("POST", url, token, "publish_document", doc_id, {"actions": [action]})
    return SanityWriteResult(document_id=doc_id, operation="publish", transaction_id=data.get("transactionId"))


def unpublish_document(draft_id: Any) -> SanityWriteResult:
    """Inverse of publish_document: moves blog-post-{draft_id} back to
    drafts.blog-post-{draft_id} via sanity.action.document.unpublish. Content
    is kept as a draft, not deleted -- final product-level archive semantics
    (what Content Studio does with an 'archived' draft) are decided later."""
    project_id, dataset, token = _require_config()
    doc_id = sanity_blog_document_id(draft_id)
    url = f"https://{project_id}.api.sanity.io/v{SANITY_API_VERSION}/data/actions/{dataset}"
    action = {"actionType": "sanity.action.document.unpublish", "draftId": f"drafts.{doc_id}", "publishedId": doc_id}
    data = _request("POST", url, token, "unpublish_document", doc_id, {"actions": [action]})
    return SanityWriteResult(document_id=doc_id, operation="unpublish", transaction_id=data.get("transactionId"))


def upload_image_asset(contents: bytes, content_type: str) -> dict:
    """Uploads raw image bytes to Sanity's Assets API and returns
    {"ref": <asset _id>, "url": <CDN url>}. Assets are dataset-wide, not
    draft/published-scoped like documents -- there's no separate "draft"
    asset to promote later, so this needs no publish step of its own.

    The returned _id already has the shape image-<hex>-<w>x<h>-<format>
    (Sanity's own asset id format) -- exactly what admin_content_studio.py's
    _COVER_IMAGE_REF_RE validates cover_image_ref against, so no translation
    is needed between what this returns and what gets stored."""
    if content_type not in _IMAGE_ASSET_CONTENT_TYPES:
        raise ValueError(f"Unsupported image content type: {content_type!r}")
    project_id, dataset, token = _require_config()
    url = f"https://{project_id}.api.sanity.io/v{SANITY_API_VERSION}/assets/images/{dataset}"
    try:
        resp = httpx.post(
            url, content=contents,
            headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
            timeout=_ASSET_UPLOAD_TIMEOUT,
        )
    except httpx.TimeoutException as exc:
        logger.warning("sanity_client upload_image_asset timed out")
        raise SanityNetworkError("Sanity upload_image_asset timed out.") from exc
    except httpx.HTTPError as exc:
        logger.warning("sanity_client upload_image_asset network error | error_type=%s", type(exc).__name__)
        raise SanityNetworkError("Sanity upload_image_asset network error.") from exc
    _raise_for_status(resp, "upload_image_asset", "<asset>")
    try:
        data = resp.json()
    except ValueError as exc:
        raise SanityAPIError("Sanity upload_image_asset returned a malformed response.") from exc
    document = data.get("document") or {}
    asset_id, asset_url = document.get("_id"), document.get("url")
    if not asset_id or not asset_url:
        raise SanityAPIError("Sanity upload_image_asset response missing document._id/url.")
    return {"ref": asset_id, "url": asset_url}


def get_document(document_id: str) -> Optional[dict]:
    """Fetch a single document by its exact _id (caller passes either the
    "drafts.blog-post-{id}" or "blog-post-{id}" form). Returns None if it
    doesn't exist -- absence isn't an error here, callers decide what it
    means."""
    document_id = _validate_document_id(document_id)
    project_id, dataset, token = _require_config()
    url = f"https://{project_id}.api.sanity.io/v{SANITY_API_VERSION}/data/doc/{dataset}/{document_id}"
    data = _request("GET", url, token, "get_document", document_id)
    documents = data.get("documents") or []
    return documents[0] if documents else None
