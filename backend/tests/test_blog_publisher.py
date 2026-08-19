"""Unit tests for app/services/blog_publisher.py (Module 1 Section 12B).
Sanity HTTP is faked via monkeypatch.setattr(httpx, "request") -- no real
network, no live Sanity project. Verifies the one-directional contract:
approved draft -> Sanity DRAFT only (never publish_document, never
Supabase, never draft status/audit)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

from app.services import blog_publisher as bp
from app.services import sanity_client as sc
from app.services.blog_document_mapper import BlogDocumentValidationError
from app.services.markdown_to_portable_text import UnsupportedImageError

BODY_MD = "# Title\n\nSome **body** text for the blog post.\n"


def make_draft(**overrides) -> dict:
    draft = {
        "id": 123,
        "module": "blog",
        "status": "approved",
        "slug": "test-blog-post",
        "excerpt": "A short excerpt describing the post.",
        "cover_image_ref": None,
        "generated_content": {"title": "Test Blog Post", "body": BODY_MD},
    }
    draft.update(overrides)
    return draft


def _configure(monkeypatch, project_id="proj123", dataset="production", token="secret-token", environment="production"):
    monkeypatch.setattr(sc.settings, "SANITY_PROJECT_ID", project_id)
    monkeypatch.setattr(sc.settings, "SANITY_DATASET", dataset)
    monkeypatch.setattr(sc.settings, "SANITY_WRITE_TOKEN", token)
    monkeypatch.setattr(sc.settings, "ENVIRONMENT", environment)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="{}"):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


def _patch_request(monkeypatch, response=None, exc=None, capture=None):
    def fake_request(method, url, headers=None, json=None, timeout=None):
        if capture is not None:
            capture.append({"method": method, "url": url, "headers": headers, "json": json, "timeout": timeout})
        if exc is not None:
            raise exc
        return response

    monkeypatch.setattr(httpx, "request", fake_request)


def _create_response(operation="create", transaction_id="tx1"):
    return FakeResponse(200, {"transactionId": transaction_id, "results": [{"id": "drafts.blog-post-123", "operation": operation}]})


# ── happy path ───────────────────────────────────────────────────────

def test_valid_draft_creates_sanity_draft(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=_create_response(), capture=captured)

    result = bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")

    assert len(captured) == 1
    assert result["draft_id"] == 123
    assert result["sanity_document_id"] == "blog-post-123"
    assert result["sanity_draft_id"] == "drafts.blog-post-123"
    assert result["operation"] == "created"
    assert result["transaction_id"] == "tx1"


def test_correct_document_id_targeted(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=_create_response(), capture=captured)

    bp.create_sanity_draft(make_draft(id=999), publish_time="2026-08-19T00:00:00Z")

    mutation = captured[0]["json"]["mutations"][0]["createOrReplace"]
    assert mutation["_id"] == "drafts.blog-post-999"


def test_correct_payload_sent(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=_create_response(), capture=captured)

    bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")

    mutation = captured[0]["json"]["mutations"][0]["createOrReplace"]
    assert mutation["_type"] == "post"
    assert mutation["title"] == "Test Blog Post"
    assert mutation["slug"] == {"_type": "slug", "current": "test-blog-post"}
    assert mutation["excerpt"] == "A short excerpt describing the post."
    assert isinstance(mutation["body"], list) and len(mutation["body"]) > 0


def test_update_operation_labelled_updated(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=_create_response(operation="update"))

    result = bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")

    assert result["operation"] == "updated"


# ── idempotency / deterministic repeat ──────────────────────────────

def test_repeated_call_targets_same_draft_id(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=_create_response(), capture=captured)

    bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")
    bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")

    id_1 = captured[0]["json"]["mutations"][0]["createOrReplace"]["_id"]
    id_2 = captured[1]["json"]["mutations"][0]["createOrReplace"]["_id"]
    assert id_1 == id_2 == "drafts.blog-post-123"
    assert len(captured) == 2  # replace, not a second document


# ── publish guard (Step 12) ─────────────────────────────────────────

def test_create_sanity_draft_never_calls_publish_document(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=_create_response())
    publish_called = []
    monkeypatch.setattr(sc, "publish_document", lambda *a, **k: publish_called.append(a))

    bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")

    assert publish_called == []


# ── mapper validation failure -> zero Sanity calls (Case A) ────────

def test_mapper_validation_error_prevents_sanity_call(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, capture=captured)

    draft = make_draft()
    draft["generated_content"]["title"] = ""
    with pytest.raises(BlogDocumentValidationError):
        bp.create_sanity_draft(draft, publish_time="2026-08-19T00:00:00Z")

    assert captured == []


def test_mapper_markdown_error_prevents_sanity_call(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, capture=captured)

    draft = make_draft()
    draft["generated_content"]["body"] = "![alt](https://example.com/x.png)"
    with pytest.raises(UnsupportedImageError):
        bp.create_sanity_draft(draft, publish_time="2026-08-19T00:00:00Z")

    assert captured == []


# ── typed Sanity errors propagate unchanged (Case C) ────────────────

def test_sanity_auth_error_propagates(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=FakeResponse(401, {"error": "unauthorized"}))
    with pytest.raises(sc.SanityAuthError):
        bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")


def test_sanity_rate_limit_error_propagates(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=FakeResponse(429, {"error": "slow down"}))
    with pytest.raises(sc.SanityRateLimitError):
        bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")


def test_sanity_api_error_propagates(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=FakeResponse(500, {"error": "boom"}))
    with pytest.raises(sc.SanityAPIError):
        bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")


def test_sanity_network_error_propagates(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, exc=httpx.TimeoutException("timed out"))
    with pytest.raises(sc.SanityNetworkError):
        bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")


def test_sanity_invalid_request_error_propagates(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=FakeResponse(400, {"error": "bad request"}))
    with pytest.raises(sc.SanityInvalidRequestError):
        bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")


# ── Supabase / audit / status boundary (Step 13) ────────────────────

def test_no_supabase_or_draft_store_import():
    """Module-level static check: create_sanity_draft has no way to reach
    Supabase or draft_store.mark_published if neither is ever imported."""
    assert "supabase" not in bp.__dict__
    assert "draft_store" not in bp.__dict__
    assert "mark_published" not in bp.__dict__


def test_draft_status_not_mutated(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=_create_response())

    draft = make_draft(status="approved")
    bp.create_sanity_draft(draft, publish_time="2026-08-19T00:00:00Z")

    assert draft["status"] == "approved"


# ── result contract ──────────────────────────────────────────────────

def test_result_contains_document_id(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=_create_response())
    result = bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")
    assert result["sanity_document_id"] == "blog-post-123"


def test_result_contains_transaction_id_when_provided(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=_create_response(transaction_id="abc-tx"))
    result = bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")
    assert result["transaction_id"] == "abc-tx"


def test_result_transaction_id_none_when_absent(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=FakeResponse(200, {"results": [{"operation": "create"}]}))
    result = bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")
    assert result["transaction_id"] is None


def test_token_not_leaked_in_result_or_exception(monkeypatch):
    _configure(monkeypatch, token="super-secret-token")
    _patch_request(monkeypatch, response=FakeResponse(401, {"error": "unauthorized"}))

    with pytest.raises(sc.SanityAuthError) as exc_info:
        bp.create_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z")

    assert "super-secret-token" not in str(exc_info.value)


# ── cover image ──────────────────────────────────────────────────────

def test_cover_image_included_in_payload(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=_create_response(), capture=captured)

    bp.create_sanity_draft(make_draft(cover_image_ref="image-abc-800x600-jpg"), publish_time="2026-08-19T00:00:00Z")

    mutation = captured[0]["json"]["mutations"][0]["createOrReplace"]
    assert mutation["coverImage"] == {
        "_type": "image",
        "asset": {"_type": "reference", "_ref": "image-abc-800x600-jpg"},
    }


def test_cover_image_omitted_from_payload_when_none(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=_create_response(), capture=captured)

    bp.create_sanity_draft(make_draft(cover_image_ref=None), publish_time="2026-08-19T00:00:00Z")

    mutation = captured[0]["json"]["mutations"][0]["createOrReplace"]
    assert "coverImage" not in mutation


# ── Section 12C: publish_sanity_draft ───────────────────────────────
# Sanity HTTP is faked at the function level (bp.create_sanity_draft /
# bp.publish_document / bp.get_document) rather than via httpx.request --
# this section is about publish_sanity_draft's own orchestration/state
# logic, not about re-testing the HTTP layer 12B/sanity_client already cover.

PUBLISHED_ID = "blog-post-123"


def _intended_document(*, publish_time="2026-08-19T00:00:00Z", existing_published_at=None):
    from app.services.blog_document_mapper import build_blog_sanity_document
    return build_blog_sanity_document(make_draft(), publish_time=publish_time, existing_published_at=existing_published_at)


def _published_doc_from_intended(intended, **overrides):
    doc = {
        "_id": PUBLISHED_ID,
        "_type": "post",
        "title": intended["title"],
        "slug": intended["slug"],
        "excerpt": intended["excerpt"],
        "body": intended["body"],
        "publishedAt": intended["publishedAt"],
    }
    if "coverImage" in intended:
        doc["coverImage"] = intended["coverImage"]
    doc.update(overrides)
    return doc


def _mock_publish_pipeline(monkeypatch, *, get_results, publish_result=None, publish_exc=None):
    """Wires bp.create_sanity_draft / bp.publish_document / bp.get_document
    to recording fakes. get_results is consumed in call order: the
    idempotency pre-check first, then each confirmation attempt."""
    create_calls, publish_calls, get_calls = [], [], []
    remaining = list(get_results)

    def fake_create_sanity_draft(draft, *, publish_time=None, existing_published_at=None):
        create_calls.append((draft, publish_time, existing_published_at))
        return {"draft_id": draft["id"], "sanity_document_id": PUBLISHED_ID}

    def fake_publish_document(draft_id):
        publish_calls.append(draft_id)
        if publish_exc is not None:
            raise publish_exc
        return publish_result or sc.SanityWriteResult(document_id=PUBLISHED_ID, operation="publish", transaction_id="tx-pub")

    def fake_get_document(document_id):
        get_calls.append(document_id)
        item = remaining.pop(0) if remaining else None
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(bp, "create_sanity_draft", fake_create_sanity_draft)
    monkeypatch.setattr(bp, "publish_document", fake_publish_document)
    monkeypatch.setattr(bp, "get_document", fake_get_document)
    return create_calls, publish_calls, get_calls


# ── happy path ───────────────────────────────────────────────────────

def test_valid_publish_returns_published_status(monkeypatch):
    published_doc = _published_doc_from_intended(_intended_document())
    _mock_publish_pipeline(monkeypatch, get_results=[None, published_doc])

    result = bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert result["status"] == "published"
    assert result["draft_id"] == 123
    assert result["already_published"] is False


def test_create_draft_called_before_publish_before_confirm(monkeypatch):
    order = []

    def fake_create(draft, *, publish_time=None, existing_published_at=None):
        order.append("create")
        return {}

    def fake_publish(draft_id):
        order.append("publish")
        return sc.SanityWriteResult(document_id=PUBLISHED_ID, operation="publish", transaction_id="tx")

    def fake_get(document_id):
        order.append("get")
        return _published_doc_from_intended(_intended_document()) if order.count("get") > 1 else None

    monkeypatch.setattr(bp, "create_sanity_draft", fake_create)
    monkeypatch.setattr(bp, "publish_document", fake_publish)
    monkeypatch.setattr(bp, "get_document", fake_get)

    bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert order == ["get", "create", "publish", "get"]


def test_publish_document_called_with_draft_id(monkeypatch):
    _, publish_calls, _ = _mock_publish_pipeline(
        monkeypatch, get_results=[None, _published_doc_from_intended(_intended_document())],
    )

    bp.publish_sanity_draft(make_draft(id=123), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert publish_calls == [123]


def test_publish_document_called_exactly_once(monkeypatch):
    _, publish_calls, _ = _mock_publish_pipeline(
        monkeypatch, get_results=[None, _published_doc_from_intended(_intended_document())],
    )

    bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert len(publish_calls) == 1


def test_confirmation_uses_published_document_id(monkeypatch):
    _, _, get_calls = _mock_publish_pipeline(
        monkeypatch, get_results=[None, _published_doc_from_intended(_intended_document())],
    )

    bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert get_calls == [PUBLISHED_ID, PUBLISHED_ID]


def test_confirmation_verifies_matching_cover_image(monkeypatch):
    intended = dict(
        _intended_document(),
        coverImage={"_type": "image", "asset": {"_type": "reference", "_ref": "image-abc-800x600-jpg"}},
    )
    _mock_publish_pipeline(monkeypatch, get_results=[None, _published_doc_from_intended(intended)])

    result = bp.publish_sanity_draft(
        make_draft(cover_image_ref="image-abc-800x600-jpg"), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None,
    )

    assert result["status"] == "published"


# ── confirmation field verification (Step 6) ────────────────────────

@pytest.mark.parametrize("field,bad_value", [
    ("_id", "blog-post-999"),
    ("_type", "page"),
    ("title", "Wrong Title"),
    ("slug", {"_type": "slug", "current": "wrong-slug"}),
    ("excerpt", "wrong excerpt"),
    ("body", [{"_type": "block", "children": []}]),
    ("publishedAt", "2020-01-01T00:00:00Z"),
])
def test_confirmation_detects_field_mismatch(monkeypatch, field, bad_value):
    intended = _intended_document()
    bad_doc = _published_doc_from_intended(intended, **{field: bad_value})
    _mock_publish_pipeline(monkeypatch, get_results=[None, bad_doc])

    with pytest.raises(bp.BlogPublicationUncertainError):
        bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)


def test_confirmation_detects_cover_image_mismatch(monkeypatch):
    intended = _intended_document()
    bad_doc = _published_doc_from_intended(
        intended, coverImage={"_type": "image", "asset": {"_type": "reference", "_ref": "image-wrong"}},
    )
    _mock_publish_pipeline(monkeypatch, get_results=[None, bad_doc])

    with pytest.raises(bp.BlogPublicationUncertainError):
        bp.publish_sanity_draft(
            make_draft(cover_image_ref="image-abc-800x600-jpg"), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None,
        )


# ── failure matrix (Step 10) ─────────────────────────────────────────

def test_draft_creation_failure_stops_publish(monkeypatch):
    publish_calls = []

    def fake_create(draft, *, publish_time=None, existing_published_at=None):
        raise sc.SanityAuthError("nope")

    def fake_publish(draft_id):
        publish_calls.append(draft_id)
        return sc.SanityWriteResult(document_id=PUBLISHED_ID, operation="publish")

    monkeypatch.setattr(bp, "create_sanity_draft", fake_create)
    monkeypatch.setattr(bp, "publish_document", fake_publish)
    monkeypatch.setattr(bp, "get_document", lambda document_id: None)

    with pytest.raises(sc.SanityAuthError):
        bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert publish_calls == []


def test_publish_failure_stops_confirmation(monkeypatch):
    get_calls = []

    def fake_get(document_id):
        get_calls.append(document_id)
        return None

    def fake_publish(draft_id):
        raise sc.SanityInvalidRequestError("bad request")

    monkeypatch.setattr(bp, "create_sanity_draft", lambda *a, **k: {})
    monkeypatch.setattr(bp, "publish_document", fake_publish)
    monkeypatch.setattr(bp, "get_document", fake_get)

    with pytest.raises(bp.BlogPublicationError):
        bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert get_calls == [PUBLISHED_ID]  # only the pre-check call -- confirmation never ran


def test_publish_timeout_classified_uncertain(monkeypatch):
    def fake_publish(draft_id):
        raise sc.SanityNetworkError("timed out")

    monkeypatch.setattr(bp, "create_sanity_draft", lambda *a, **k: {})
    monkeypatch.setattr(bp, "publish_document", fake_publish)
    monkeypatch.setattr(bp, "get_document", lambda document_id: None)

    with pytest.raises(bp.BlogPublicationUncertainError):
        bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)


def test_confirmation_missing_document_classified_uncertain(monkeypatch):
    sleeps = []
    _, _, get_calls = _mock_publish_pipeline(monkeypatch, get_results=[None, None, None, None])

    with pytest.raises(bp.BlogPublicationUncertainError):
        bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: sleeps.append(s))

    assert len(get_calls) == 1 + bp._CONFIRM_MAX_ATTEMPTS  # pre-check + all bounded confirm attempts
    assert len(sleeps) == bp._CONFIRM_MAX_ATTEMPTS - 1  # bounded, not a sleep before the first attempt


def test_confirmation_api_error_classified_uncertain(monkeypatch):
    calls = {"n": 0}

    def fake_get(document_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # pre-check: no published document yet
        raise sc.SanityAPIError("boom")

    monkeypatch.setattr(bp, "create_sanity_draft", lambda *a, **k: {})
    monkeypatch.setattr(bp, "publish_document", lambda draft_id: sc.SanityWriteResult(document_id=PUBLISHED_ID, operation="publish"))
    monkeypatch.setattr(bp, "get_document", fake_get)

    with pytest.raises(bp.BlogPublicationUncertainError):
        bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)


# ── idempotency (Step 11/12) ─────────────────────────────────────────

def test_repeated_publish_second_call_is_idempotent(monkeypatch):
    published_doc = _published_doc_from_intended(_intended_document())
    create_calls, publish_calls, _ = _mock_publish_pipeline(
        monkeypatch, get_results=[None, published_doc, published_doc],
    )

    bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)
    result2 = bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert result2["already_published"] is True
    assert len(create_calls) == 1  # second call did not write/publish again
    assert len(publish_calls) == 1


def test_mismatched_existing_published_document_triggers_republish(monkeypatch):
    intended = _intended_document()
    stale_doc = _published_doc_from_intended(intended, title="Old Title")
    fresh_doc = _published_doc_from_intended(intended)
    create_calls, publish_calls, _ = _mock_publish_pipeline(monkeypatch, get_results=[stale_doc, fresh_doc])

    result = bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert result["already_published"] is False
    assert len(create_calls) == 1
    assert len(publish_calls) == 1


# ── Supabase / audit boundary (Step 13/14) ───────────────────────────

def test_publish_does_not_mutate_draft_status(monkeypatch):
    _mock_publish_pipeline(monkeypatch, get_results=[None, _published_doc_from_intended(_intended_document())])
    draft = make_draft(status="approved")

    bp.publish_sanity_draft(draft, publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert draft["status"] == "approved"


def test_no_audit_log_import():
    assert "_write_audit_log" not in bp.__dict__
    assert "audit" not in bp.__dict__


# ── security ──────────────────────────────────────────────────────────

def test_publish_rejection_does_not_leak_token(monkeypatch):
    _configure(monkeypatch, token="super-secret-publish-token")
    _patch_request(monkeypatch, response=FakeResponse(401, {"error": "unauthorized"}))
    monkeypatch.setattr(bp, "create_sanity_draft", lambda *a, **k: {})
    monkeypatch.setattr(bp, "get_document", lambda document_id: None)

    with pytest.raises(bp.BlogPublicationError) as exc_info:
        bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T00:00:00Z", _sleep=lambda s: None)

    assert "super-secret-publish-token" not in str(exc_info.value)


# ── publishedAt handling (Step 8) ────────────────────────────────────

def test_first_publish_uses_publish_time(monkeypatch):
    intended = _intended_document(publish_time="2026-08-19T09:00:00Z")
    _mock_publish_pipeline(monkeypatch, get_results=[None, _published_doc_from_intended(intended)])

    result = bp.publish_sanity_draft(make_draft(), publish_time="2026-08-19T09:00:00Z", _sleep=lambda s: None)

    assert result["published_at"] == "2026-08-19T09:00:00Z"


def test_republish_preserves_existing_published_at(monkeypatch):
    intended = _intended_document(publish_time="2026-08-19T09:00:00Z", existing_published_at="2026-01-01T00:00:00Z")
    _mock_publish_pipeline(monkeypatch, get_results=[None, _published_doc_from_intended(intended)])

    result = bp.publish_sanity_draft(
        make_draft(), publish_time="2026-08-19T09:00:00Z", existing_published_at="2026-01-01T00:00:00Z", _sleep=lambda s: None,
    )

    assert result["published_at"] == "2026-01-01T00:00:00Z"
