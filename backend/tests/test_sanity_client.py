"""Unit tests for app/services/sanity_client.py (Module 1 Section 4). All
HTTP is faked via monkeypatch.setattr(httpx, "request") -- no real network,
no live Sanity project, no real SANITY_WRITE_TOKEN required."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

from app.services import sanity_client as sc


def _configure(monkeypatch, project_id="proj123", dataset="production", token="secret-token", environment="production"):
    monkeypatch.setattr(sc.settings, "SANITY_PROJECT_ID", project_id)
    monkeypatch.setattr(sc.settings, "SANITY_DATASET", dataset)
    monkeypatch.setattr(sc.settings, "SANITY_WRITE_TOKEN", token)
    # Pinned explicitly (rather than left to whatever the real dotenv has)
    # so these tests are deterministic regardless of the local machine's
    # ENVIRONMENT -- see the dataset-isolation tests below for the qa/dev cases.
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


# ── configuration ────────────────────────────────────────────────────

def test_missing_config_raises_config_error(monkeypatch):
    _configure(monkeypatch, project_id="", token="")
    with pytest.raises(sc.SanityConfigError):
        sc.create_or_replace_document(1, {"title": "x"})


def test_missing_write_token_raises_config_error(monkeypatch):
    _configure(monkeypatch, token="")
    with pytest.raises(sc.SanityConfigError):
        sc.get_document("blog-post-1")


# ── deterministic document id ───────────────────────────────────────

def test_document_id_is_deterministic():
    assert sc.sanity_blog_document_id(42) == "blog-post-42"
    assert sc.sanity_blog_document_id(42) == sc.sanity_blog_document_id(42)


def test_document_id_differs_per_draft():
    assert sc.sanity_blog_document_id(1) != sc.sanity_blog_document_id(2)


def test_document_id_rejects_non_integer():
    with pytest.raises(ValueError):
        sc.sanity_blog_document_id("1; drop table posts")
    with pytest.raises(ValueError):
        sc.sanity_blog_document_id("../../etc/passwd")
    with pytest.raises(ValueError):
        sc.sanity_blog_document_id(-1)
    with pytest.raises(ValueError):
        sc.sanity_blog_document_id(None)


# ── create_or_replace_document ──────────────────────────────────────

def test_create_or_replace_sends_post_to_mutate_endpoint(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=FakeResponse(200, {"transactionId": "tx1", "results": [{"id": "drafts.blog-post-7", "operation": "create"}]}), capture=captured)

    sc.create_or_replace_document(7, {"title": "Hello"})

    req = captured[0]
    assert req["method"] == "POST"
    assert req["url"] == "https://proj123.api.sanity.io/v2026-07-01/data/mutate/production"


def test_create_or_replace_targets_draft_id_not_published_id(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=FakeResponse(200, {"results": [{"operation": "create"}]}), capture=captured)

    sc.create_or_replace_document(7, {"title": "Hello"})

    mutation = captured[0]["json"]["mutations"][0]["createOrReplace"]
    assert mutation["_id"] == "drafts.blog-post-7"


def test_authorization_header_present(monkeypatch):
    _configure(monkeypatch, token="my-secret-token")
    captured = []
    _patch_request(monkeypatch, response=FakeResponse(200, {"results": [{"operation": "create"}]}), capture=captured)

    sc.create_or_replace_document(7, {"title": "Hello"})

    assert captured[0]["headers"]["Authorization"] == "Bearer my-secret-token"


def test_token_not_leaked_in_exception_message(monkeypatch):
    _configure(monkeypatch, token="super-secret-token")
    _patch_request(monkeypatch, response=FakeResponse(401, {"error": "unauthorized"}))

    with pytest.raises(sc.SanityAuthError) as exc_info:
        sc.create_or_replace_document(7, {"title": "Hello"})

    assert "super-secret-token" not in str(exc_info.value)


def test_token_not_leaked_in_logs(monkeypatch, caplog):
    _configure(monkeypatch, token="super-secret-token")
    _patch_request(monkeypatch, response=FakeResponse(500, {"error": "boom"}))

    with caplog.at_level("WARNING"):
        with pytest.raises(sc.SanityAPIError):
            sc.create_or_replace_document(7, {"title": "Hello"})

    assert "super-secret-token" not in caplog.text


def test_repeated_create_or_replace_uses_same_document_id(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=FakeResponse(200, {"results": [{"operation": "create"}]}), capture=captured)

    sc.create_or_replace_document(9, {"title": "First"})
    sc.create_or_replace_document(9, {"title": "Second"})

    first_id = captured[0]["json"]["mutations"][0]["createOrReplace"]["_id"]
    second_id = captured[1]["json"]["mutations"][0]["createOrReplace"]["_id"]
    assert first_id == second_id == "drafts.blog-post-9"


def test_create_or_replace_no_real_network_call(monkeypatch):
    """httpx.request is fully replaced by the fake -- if the client ever fell
    through to a real call, it would hit this stub, not the network."""
    _configure(monkeypatch)
    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append(url)
        return FakeResponse(200, {"results": [{"operation": "create"}]})

    monkeypatch.setattr(httpx, "request", fake_request)
    sc.create_or_replace_document(1, {"title": "x"})

    assert calls == ["https://proj123.api.sanity.io/v2026-07-01/data/mutate/production"]


# ── publish / unpublish semantics ───────────────────────────────────

def test_publish_uses_actions_endpoint_and_publish_action_type(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=FakeResponse(200, {"transactionId": "tx2"}), capture=captured)

    result = sc.publish_document(7)

    req = captured[0]
    assert req["url"] == "https://proj123.api.sanity.io/v2026-07-01/data/actions/production"
    action = req["json"]["actions"][0]
    assert action["actionType"] == "sanity.action.document.publish"
    assert action["draftId"] == "drafts.blog-post-7"
    assert action["publishedId"] == "blog-post-7"
    assert result.operation == "publish"
    assert result.document_id == "blog-post-7"


def test_unpublish_uses_unpublish_action_type(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_request(monkeypatch, response=FakeResponse(200, {"transactionId": "tx3"}), capture=captured)

    result = sc.unpublish_document(7)

    action = captured[0]["json"]["actions"][0]
    assert action["actionType"] == "sanity.action.document.unpublish"
    assert result.operation == "unpublish"


# ── error handling ──────────────────────────────────────────────────

@pytest.mark.parametrize("status_code,expected_exc", [
    (400, sc.SanityInvalidRequestError),
    (401, sc.SanityAuthError),
    (403, sc.SanityAuthError),
    (404, sc.SanityInvalidRequestError),
    (429, sc.SanityRateLimitError),
    (500, sc.SanityAPIError),
    (502, sc.SanityAPIError),
])
def test_non_2xx_response_becomes_typed_exception(monkeypatch, status_code, expected_exc):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=FakeResponse(status_code, {"error": "boom"}))

    with pytest.raises(expected_exc):
        sc.get_document("blog-post-1")


def test_timeout_raises_network_error(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, exc=httpx.TimeoutException("timed out"))

    with pytest.raises(sc.SanityNetworkError):
        sc.get_document("blog-post-1")


def test_connection_error_raises_network_error(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, exc=httpx.ConnectError("connection refused"))

    with pytest.raises(sc.SanityNetworkError):
        sc.get_document("blog-post-1")


def test_malformed_json_response_handled_safely(monkeypatch):
    _configure(monkeypatch)

    class BadJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("not json")

    _patch_request(monkeypatch, response=BadJsonResponse(200, text="<html>not json</html>"))

    with pytest.raises(sc.SanityAPIError):
        sc.get_document("blog-post-1")


# ── get_document ─────────────────────────────────────────────────────

def test_get_document_returns_none_when_absent(monkeypatch):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=FakeResponse(200, {"documents": []}))

    assert sc.get_document("blog-post-404") is None


def test_get_document_returns_first_document(monkeypatch):
    _configure(monkeypatch)
    doc = {"_id": "blog-post-1", "title": "Hi"}
    _patch_request(monkeypatch, response=FakeResponse(200, {"documents": [doc]}))

    assert sc.get_document("blog-post-1") == doc


# ── get_document document-id validation ─────────────────────────────

@pytest.mark.parametrize("document_id", [
    "blog-post-123",
    "drafts.blog-post-123",
])
def test_get_document_accepts_valid_document_ids(monkeypatch, document_id):
    _configure(monkeypatch)
    _patch_request(monkeypatch, response=FakeResponse(200, {"documents": []}))

    assert sc.get_document(document_id) is None


@pytest.mark.parametrize("document_id", [
    "../secret",
    "../../secret",
    "foo/bar",
    "foo?x=1",
    "foo#fragment",
    "https://example.com",
    "",
    "   ",
    "-leading-hyphen",
    ".leading-dot",
])
def test_get_document_rejects_invalid_document_ids(monkeypatch, document_id):
    _configure(monkeypatch)
    calls = []
    _patch_request(monkeypatch, response=FakeResponse(200, {"documents": []}), capture=calls)

    with pytest.raises(sc.SanityInvalidRequestError):
        sc.get_document(document_id)

    assert calls == []  # rejected before any network call


# ── sanity dataset environment isolation ────────────────────────────

def test_production_environment_with_production_dataset_allowed(monkeypatch):
    _configure(monkeypatch, dataset="production", environment="production")
    _patch_request(monkeypatch, response=FakeResponse(200, {"documents": []}))

    assert sc.get_document("blog-post-1") is None


def test_qa_environment_without_explicit_dataset_rejected(monkeypatch):
    _configure(monkeypatch, dataset="production", environment="qa")

    with pytest.raises(sc.SanityDatasetIsolationError):
        sc.get_document("blog-post-1")


def test_qa_environment_with_explicit_dataset_allowed(monkeypatch):
    _configure(monkeypatch, dataset="qa-blog", environment="qa")
    _patch_request(monkeypatch, response=FakeResponse(200, {"documents": []}))

    assert sc.get_document("blog-post-1") is None


def test_development_environment_without_configured_dataset_rejected(monkeypatch):
    _configure(monkeypatch, dataset="production", environment="development")

    with pytest.raises(sc.SanityDatasetIsolationError):
        sc.get_document("blog-post-1")


def test_dataset_isolation_error_does_not_leak_write_token(monkeypatch):
    _configure(monkeypatch, dataset="production", environment="qa", token="super-secret-token")

    with pytest.raises(sc.SanityDatasetIsolationError) as exc_info:
        sc.get_document("blog-post-1")

    assert "super-secret-token" not in str(exc_info.value)


def test_dataset_isolation_check_applies_to_write_operations(monkeypatch):
    _configure(monkeypatch, dataset="production", environment="qa")

    with pytest.raises(sc.SanityDatasetIsolationError):
        sc.create_or_replace_document(1, {"title": "x"})


# ── upload_image_asset (Module 1 Section 11) ────────────────────────

def _patch_post(monkeypatch, response=None, exc=None, capture=None):
    def fake_post(url, content=None, headers=None, timeout=None):
        if capture is not None:
            capture.append({"url": url, "content": content, "headers": headers, "timeout": timeout})
        if exc is not None:
            raise exc
        return response

    monkeypatch.setattr(httpx, "post", fake_post)


def test_upload_image_asset_rejects_unsupported_content_type(monkeypatch):
    _configure(monkeypatch)
    with pytest.raises(ValueError):
        sc.upload_image_asset(b"gifdata", "image/gif")


def test_upload_image_asset_posts_to_assets_endpoint(monkeypatch):
    _configure(monkeypatch)
    captured = []
    _patch_post(monkeypatch, response=FakeResponse(200, {"document": {"_id": "image-abc-100x100-jpg", "url": "https://cdn.sanity.io/x.jpg"}}), capture=captured)

    sc.upload_image_asset(b"\xff\xd8\xff...", "image/jpeg")

    req = captured[0]
    assert req["url"] == "https://proj123.api.sanity.io/v2026-07-01/assets/images/production"
    assert req["content"] == b"\xff\xd8\xff..."
    assert req["headers"]["Content-Type"] == "image/jpeg"
    assert req["headers"]["Authorization"] == "Bearer secret-token"


def test_upload_image_asset_returns_ref_and_url(monkeypatch):
    _configure(monkeypatch)
    _patch_post(monkeypatch, response=FakeResponse(200, {"document": {"_id": "image-abc-100x100-jpg", "url": "https://cdn.sanity.io/x.jpg"}}))

    result = sc.upload_image_asset(b"bytes", "image/png")

    assert result == {"ref": "image-abc-100x100-jpg", "url": "https://cdn.sanity.io/x.jpg"}


def test_upload_image_asset_missing_document_fields_raises_api_error(monkeypatch):
    _configure(monkeypatch)
    _patch_post(monkeypatch, response=FakeResponse(200, {"document": {}}))

    with pytest.raises(sc.SanityAPIError):
        sc.upload_image_asset(b"bytes", "image/png")


def test_upload_image_asset_malformed_json_raises_api_error(monkeypatch):
    _configure(monkeypatch)

    class BadJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("not json")

    _patch_post(monkeypatch, response=BadJsonResponse(200, text="<html>"))

    with pytest.raises(sc.SanityAPIError):
        sc.upload_image_asset(b"bytes", "image/png")


@pytest.mark.parametrize("status_code,expected_exc", [
    (400, sc.SanityInvalidRequestError),
    (401, sc.SanityAuthError),
    (429, sc.SanityRateLimitError),
    (500, sc.SanityAPIError),
])
def test_upload_image_asset_non_2xx_becomes_typed_exception(monkeypatch, status_code, expected_exc):
    _configure(monkeypatch)
    _patch_post(monkeypatch, response=FakeResponse(status_code, {"error": "boom"}))

    with pytest.raises(expected_exc):
        sc.upload_image_asset(b"bytes", "image/jpeg")


def test_upload_image_asset_timeout_raises_network_error(monkeypatch):
    _configure(monkeypatch)
    _patch_post(monkeypatch, exc=httpx.TimeoutException("timed out"))

    with pytest.raises(sc.SanityNetworkError):
        sc.upload_image_asset(b"bytes", "image/jpeg")


def test_upload_image_asset_missing_config_raises_config_error(monkeypatch):
    _configure(monkeypatch, project_id="", token="")
    with pytest.raises(sc.SanityConfigError):
        sc.upload_image_asset(b"bytes", "image/jpeg")


def test_upload_image_asset_dataset_isolation_applies(monkeypatch):
    _configure(monkeypatch, dataset="production", environment="qa")
    with pytest.raises(sc.SanityDatasetIsolationError):
        sc.upload_image_asset(b"bytes", "image/jpeg")


def test_upload_image_asset_token_not_leaked_in_exception(monkeypatch):
    _configure(monkeypatch, token="super-secret-token")
    _patch_post(monkeypatch, response=FakeResponse(401, {"error": "unauthorized"}))

    with pytest.raises(sc.SanityAuthError) as exc_info:
        sc.upload_image_asset(b"bytes", "image/jpeg")

    assert "super-secret-token" not in str(exc_info.value)
