"""MODULE 1 SECTION 9 self-check: Blog draft creation + validation.

Section 7A (test_draft_workflow.py) already proved slug/excerpt/
cover_image_ref plumbing, DB-uniqueness-error passthrough, and revision
snapshots. This file covers what Section 9 adds on top: title validation
(generated_content.title has no dedicated column, so it needs its own
service-layer check), the review/approve completeness gate, and that
authorization for Blog drafts is the same require_admin/require_analyst
tier every other module already uses -- no new auth mechanism.

Same no-live-DB style as test_draft_workflow.py (FakeSupabase) and the same
direct-dependency-call style as test_rc41_publish_permissions.py for the
authorization checks.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException, params as fastapi_params
from unittest.mock import MagicMock, patch

from app.routers import admin as admin_module
from app.routers import admin_content_studio
from app.routers.auth import UserInfo
from app.services import blog_publisher, draft_store, sanity_client

from test_draft_workflow import FakeSupabase, _draft, _patched  # noqa: E402


# ── title validation (create) ──────────────────────────────────────────

def test_blog_draft_creation_with_all_fields_succeeds(monkeypatch):
    fake = _patched(monkeypatch, [])
    created = draft_store.create_draft(
        module="blog", draft_name="My Post", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "Hello World", "body": "Some body text."},
        validation_warnings=[], model_used=None, created_by="admin-1",
        slug="hello-world", excerpt="A teaser.", cover_image_ref="image-abc123-800x600-jpg",
    )
    assert created["module"] == "blog"
    assert created["generated_content"]["title"] == "Hello World"
    del fake  # only used to construct the patched supabase


def test_blog_title_required(monkeypatch):
    _patched(monkeypatch, [])
    with pytest.raises(ValueError):
        draft_store.create_draft(
            module="blog", draft_name="No title", ai_title=None, metadata={}, prompt={},
            generated_content={"body": "b"}, validation_warnings=[],
            model_used=None, created_by="admin-1",
        )


def test_blog_empty_title_rejected(monkeypatch):
    _patched(monkeypatch, [])
    with pytest.raises(ValueError):
        draft_store.create_draft(
            module="blog", draft_name="Empty title", ai_title=None, metadata={}, prompt={},
            generated_content={"title": "", "body": "b"}, validation_warnings=[],
            model_used=None, created_by="admin-1",
        )


def test_blog_whitespace_title_rejected(monkeypatch):
    _patched(monkeypatch, [])
    with pytest.raises(ValueError):
        draft_store.create_draft(
            module="blog", draft_name="Whitespace title", ai_title=None, metadata={}, prompt={},
            generated_content={"title": "   \t  ", "body": "b"}, validation_warnings=[],
            model_used=None, created_by="admin-1",
        )


def test_blog_excessively_long_title_rejected(monkeypatch):
    _patched(monkeypatch, [])
    with pytest.raises(ValueError):
        draft_store.create_draft(
            module="blog", draft_name="Long title", ai_title=None, metadata={}, prompt={},
            generated_content={"title": "x" * 301, "body": "b"}, validation_warnings=[],
            model_used=None, created_by="admin-1",
        )


def test_blog_title_at_max_length_accepted(monkeypatch):
    _patched(monkeypatch, [])
    created = draft_store.create_draft(
        module="blog", draft_name="Max title", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "x" * 300, "body": "b"}, validation_warnings=[],
        model_used=None, created_by="admin-1",
    )
    assert len(created["generated_content"]["title"]) == 300


def test_blog_body_may_be_empty_at_creation(monkeypatch):
    """Step 4: AI generation may produce a title before a body exists yet."""
    _patched(monkeypatch, [])
    created = draft_store.create_draft(
        module="blog", draft_name="No body yet", ai_title=None, metadata={}, prompt={},
        generated_content={"title": "Hello", "body": ""}, validation_warnings=[],
        model_used=None, created_by="admin-1",
    )
    assert created["generated_content"]["body"] == ""


def test_non_blog_draft_creation_still_works_without_title(monkeypatch):
    _patched(monkeypatch, [])
    created = draft_store.create_draft(
        module="speaking", draft_name="A scenario", ai_title=None, metadata={}, prompt={},
        generated_content={"setting": "ward"}, validation_warnings=[],
        model_used=None, created_by="admin-1",
    )
    assert created["module"] == "speaking"


# ── title validation (update) ────────────────────────────────────────────

def test_blog_update_rejects_blanked_title(monkeypatch):
    rows = [_draft(module="blog", status="draft", generated_content={"title": "Hello", "body": "b"})]
    _patched(monkeypatch, rows)
    with pytest.raises(ValueError):
        draft_store.update_content(1, generated_content={"title": "", "body": "b"}, editor_id="a1")


def test_blog_update_accepts_valid_title_change(monkeypatch):
    rows = [_draft(module="blog", status="draft", generated_content={"title": "Hello", "body": "b"})]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, generated_content={"title": "New title", "body": "b"}, editor_id="a1")
    assert updated["generated_content"]["title"] == "New title"


def test_non_blog_update_unaffected_by_title_rule(monkeypatch):
    rows = [_draft(module="writing", status="draft", generated_content={"title": "v1"})]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, generated_content={"body": "no title key at all"}, editor_id="a1")
    assert updated["generated_content"] == {"body": "no title key at all"}


# ── review/approve completeness gate (Step 10) ───────────────────────────

def _complete_blog_draft(status="draft", **overrides):
    base = dict(
        module="blog", status=status,
        generated_content={"title": "Hello", "body": "Some body text."},
        slug="hello-world", excerpt="A teaser.", cover_image_ref=None,
    )
    base.update(overrides)
    return _draft(**base)


def test_blog_submit_for_review_succeeds_when_complete(monkeypatch):
    rows = [_complete_blog_draft(status="draft")]
    _patched(monkeypatch, rows)
    updated = draft_store.submit_for_review(1)
    assert updated["status"] == "review"


def test_blog_submit_for_review_rejected_missing_body(monkeypatch):
    rows = [_complete_blog_draft(status="draft", generated_content={"title": "Hello", "body": ""})]
    _patched(monkeypatch, rows)
    with pytest.raises(draft_store.InvalidTransitionError):
        draft_store.submit_for_review(1)


def test_blog_submit_for_review_rejected_missing_slug(monkeypatch):
    rows = [_complete_blog_draft(status="draft", slug=None)]
    _patched(monkeypatch, rows)
    with pytest.raises(draft_store.InvalidTransitionError):
        draft_store.submit_for_review(1)


def test_blog_submit_for_review_rejected_missing_excerpt(monkeypatch):
    rows = [_complete_blog_draft(status="draft", excerpt=None)]
    _patched(monkeypatch, rows)
    with pytest.raises(draft_store.InvalidTransitionError):
        draft_store.submit_for_review(1)


def test_blog_submit_for_review_allows_missing_cover_image(monkeypatch):
    """cover_image_ref stays optional even at the review gate (Step 10)."""
    rows = [_complete_blog_draft(status="draft", cover_image_ref=None)]
    _patched(monkeypatch, rows)
    updated = draft_store.submit_for_review(1)
    assert updated["status"] == "review"


def test_blog_approve_rejected_when_incomplete(monkeypatch):
    rows = [_complete_blog_draft(status="review", excerpt=None)]
    _patched(monkeypatch, rows)
    with pytest.raises(draft_store.InvalidTransitionError):
        draft_store.approve(1, "admin-1")


def test_blog_approve_succeeds_when_complete(monkeypatch):
    rows = [_complete_blog_draft(status="review")]
    _patched(monkeypatch, rows)
    updated = draft_store.approve(1, "admin-1")
    assert updated["status"] == "approved"


def test_non_blog_submit_for_review_unaffected_by_completeness_gate(monkeypatch):
    """Speaking/writing/etc. drafts have no slug/excerpt -- the blog gate
    must not leak onto them."""
    rows = [_draft(module="writing", status="draft", generated_content={"title": "t"})]
    _patched(monkeypatch, rows)
    updated = draft_store.submit_for_review(1)
    assert updated["status"] == "review"


# ── get/list responses expose blog fields (Step 12) ──────────────────────

def test_blog_fields_survive_get_draft(monkeypatch):
    rows = [_complete_blog_draft(status="draft")]
    fake = _patched(monkeypatch, rows)
    fetched = draft_store.get_draft(1)
    assert fetched["slug"] == "hello-world"
    assert fetched["excerpt"] == "A teaser."
    assert fetched["generated_content"]["title"] == "Hello"
    del fake


def test_blog_slug_survives_list_drafts(monkeypatch):
    rows = [_complete_blog_draft(status="draft")]
    _patched(monkeypatch, rows)
    listed = draft_store.list_drafts(module="blog")
    assert listed["drafts"][0]["slug"] == "hello-world"


# ── authorization: same require_admin/require_analyst tier as every other
# module (Step 13 -- no new mechanism). Style matches
# test_rc41_publish_permissions.py's direct-dependency-call approach.

def _fake_supabase(role):
    supabase = MagicMock()
    result = MagicMock()
    result.data = [{"role": role}] if role is not None else []
    supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = result
    return supabase


def _dependency_of(fn, param_name):
    default = inspect.signature(fn).parameters[param_name].default
    assert isinstance(default, fastapi_params.Depends)
    return default.dependency


def _call_dependency(dep, role):
    user = UserInfo(id="u1", email="u1@example.com", name="U1")
    with patch.object(admin_module, "get_supabase", return_value=_fake_supabase(role)):
        return dep(current_user=user)


def test_save_draft_dependency_is_require_admin():
    dep = _dependency_of(admin_content_studio.save_draft, "current_user")
    assert dep is admin_module.require_admin


def test_update_draft_dependency_is_require_analyst():
    dep = _dependency_of(admin_content_studio.update_draft, "current_user")
    assert dep is admin_module.require_analyst


def test_unauthorized_user_cannot_create_blog_draft():
    """A plain 'user' role (below analyst) is rejected by the same gate
    every module's draft creation already sits behind."""
    with pytest.raises(HTTPException) as ctx:
        _call_dependency(admin_module.require_admin, "user")
    assert ctx.value.status_code == 403


def test_unauthorized_user_cannot_update_blog_draft():
    with pytest.raises(HTTPException) as ctx:
        _call_dependency(admin_module.require_analyst, "user")
    assert ctx.value.status_code == 403


def test_analyst_cannot_create_blog_draft_but_can_update():
    """save_draft is admin-only; update_draft is analyst+ -- analyst sits
    between the two, so it's the sharpest boundary check."""
    with pytest.raises(HTTPException):
        _call_dependency(admin_module.require_admin, "analyst")
    assert _call_dependency(admin_module.require_analyst, "analyst").id == "u1"


# ── slug/excerpt/cover_image_ref edits after approval/publish demote to
# 'review' (Module 1 Section 12D Step 15) -- same rule generated_content
# edits already get, extended to the other three fields Sanity actually
# publishes from.

def test_blog_slug_change_on_approved_draft_demotes_to_review(monkeypatch):
    rows = [_complete_blog_draft(status="approved", approved_by="admin-1", approved_at="2026-08-01T00:00:00Z")]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, slug="new-slug", editor_id="a1")
    assert updated["status"] == "review"
    assert updated["approved_by"] is None
    assert updated["approved_at"] is None


def test_blog_cover_image_change_on_published_draft_demotes_to_review(monkeypatch):
    rows = [_complete_blog_draft(status="published", approved_by="admin-1", approved_at="2026-08-01T00:00:00Z",
                                  published_by="owner-1", published_at="2026-08-02T00:00:00Z")]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, cover_image_ref="image-abc123-800x600-jpg", editor_id="a1")
    assert updated["status"] == "review"


def test_blog_excerpt_change_on_review_draft_stays_review(monkeypatch):
    """No regression: a Blog field edit while already in review just stays
    in review, same as a generated_content edit already does."""
    rows = [_complete_blog_draft(status="review")]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, excerpt="A different teaser.", editor_id="a1")
    assert updated["status"] == "review"


def test_non_blog_metadata_change_on_approved_draft_unaffected_by_blog_demote_rule(monkeypatch):
    """The blog-metadata demote condition is scoped to module=='blog' -- a
    non-blog approved draft's metadata-only edit must not demote it (that
    would be a new behavior change for every other module, which this
    section must not introduce)."""
    rows = [_draft(module="speaking", status="approved", approved_by="admin-1", approved_at="2026-08-01T00:00:00Z",
                    generated_content={"title": "t"}, metadata={"specialty": "cardiology"})]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, metadata={"specialty": "oncology"}, editor_id="a1")
    assert updated["status"] == "approved"


# ── publish (Module 1 Section 12D) ───────────────────────────────────────
# Sanity is Blog's production system, not a Supabase table -- draft_publisher
# has no 'blog' branch (test_blog_publish_still_blocked_not_publishable,
# test_draft_workflow.py) and stays that way. admin_content_studio._publish_blog_draft
# is the new glue: Sanity publish first, Supabase 'published' flip only after
# Sanity confirms. No real Sanity HTTP here -- blog_publisher.publish_sanity_draft
# and sanity_client.get_document are monkeypatched; Sanity's own HTTP/retry/
# idempotency behavior is already covered by test_blog_publisher.py.

def _approved_blog_draft(**overrides):
    return _complete_blog_draft(status="approved", **overrides)


def _shared_blog_fake(monkeypatch, rows):
    fake = FakeSupabase()
    fake.tables["generated_content_drafts"] = rows
    monkeypatch.setattr(draft_store, "get_supabase", lambda: fake)
    monkeypatch.setattr(admin_content_studio, "get_supabase", lambda: fake)
    return fake


_OWNER = UserInfo(id="owner-1", email="owner@example.com")


def _publish_result(**overrides):
    result = {
        "draft_id": 1, "sanity_document_id": "blog-post-1", "sanity_draft_id": "drafts.blog-post-1",
        "status": "published", "published_at": "2026-08-19T00:00:00Z", "transaction_id": "tx1",
        "already_published": False,
    }
    result.update(overrides)
    return result


def test_blog_publish_success_flips_supabase_after_sanity_confirms(monkeypatch):
    rows = [_approved_blog_draft()]
    fake = _shared_blog_fake(monkeypatch, rows)
    monkeypatch.setattr(sanity_client, "get_document", lambda doc_id: None)
    monkeypatch.setattr(blog_publisher, "publish_sanity_draft", lambda draft, **kw: _publish_result())

    result = admin_content_studio._publish_blog_draft(rows[0], _OWNER)

    assert result["status"] == "published"
    assert fake.tables["generated_content_drafts"][0]["status"] == "published"
    assert fake.tables["generated_content_drafts"][0]["published_by"] == "owner-1"
    audit_actions = [r["action"] for r in fake.tables["audit_log"]]
    assert "draft_published" in audit_actions


def test_blog_publish_first_time_uses_publish_time_not_existing(monkeypatch):
    """First publish (Case C): no Sanity document exists yet, so
    existing_published_at must be None -- publish_sanity_draft falls back to
    publish_time itself (build_blog_sanity_document's own rule, Section 12A)."""
    rows = [_approved_blog_draft()]
    _shared_blog_fake(monkeypatch, rows)
    monkeypatch.setattr(sanity_client, "get_document", lambda doc_id: None)
    captured = {}

    def fake_publish(draft, **kw):
        captured.update(kw)
        return _publish_result()

    monkeypatch.setattr(blog_publisher, "publish_sanity_draft", fake_publish)
    admin_content_studio._publish_blog_draft(rows[0], _OWNER)

    assert captured["existing_published_at"] is None
    assert captured["publish_time"]  # some ISO timestamp was supplied


def test_blog_republish_reuses_existing_published_at(monkeypatch):
    """Republish: a Sanity document already exists -- its publishedAt must be
    threaded through unchanged, not replaced with 'now', so a content edit
    never resets a post's original publish date."""
    rows = [_approved_blog_draft()]
    _shared_blog_fake(monkeypatch, rows)
    monkeypatch.setattr(sanity_client, "get_document", lambda doc_id: {"publishedAt": "2026-01-01T00:00:00Z"})
    captured = {}

    def fake_publish(draft, **kw):
        captured.update(kw)
        return _publish_result(published_at="2026-01-01T00:00:00Z", already_published=False)

    monkeypatch.setattr(blog_publisher, "publish_sanity_draft", fake_publish)
    admin_content_studio._publish_blog_draft(rows[0], _OWNER)

    assert captured["existing_published_at"] == "2026-01-01T00:00:00Z"


def test_blog_publish_sanity_lookup_failure_leaves_draft_approved(monkeypatch):
    """Case A-equivalent: can't even look up existing Sanity state -- nothing
    was written, Supabase must stay untouched, and the error must not leak
    raw Sanity detail to the admin."""
    rows = [_approved_blog_draft()]
    fake = _shared_blog_fake(monkeypatch, rows)

    def boom(doc_id):
        raise sanity_client.SanityAuthError("token rejected: sk_live_SECRETVALUE")

    monkeypatch.setattr(sanity_client, "get_document", boom)

    with pytest.raises(HTTPException) as ctx:
        admin_content_studio._publish_blog_draft(rows[0], _OWNER)

    assert ctx.value.status_code == 502
    assert "SECRETVALUE" not in ctx.value.detail
    assert fake.tables["generated_content_drafts"][0]["status"] == "approved"


def test_blog_publish_definite_sanity_rejection_leaves_draft_approved(monkeypatch):
    rows = [_approved_blog_draft()]
    fake = _shared_blog_fake(monkeypatch, rows)
    monkeypatch.setattr(sanity_client, "get_document", lambda doc_id: None)

    def fake_publish(draft, **kw):
        raise blog_publisher.BlogPublicationError("Sanity rejected: token sk_live_SECRETVALUE")

    monkeypatch.setattr(blog_publisher, "publish_sanity_draft", fake_publish)

    with pytest.raises(HTTPException) as ctx:
        admin_content_studio._publish_blog_draft(rows[0], _OWNER)

    assert ctx.value.status_code == 502
    assert "not published" in ctx.value.detail.lower()
    assert "SECRETVALUE" not in ctx.value.detail
    assert fake.tables["generated_content_drafts"][0]["status"] == "approved"
    audit_actions = [r["action"] for r in fake.tables["audit_log"]]
    assert "draft_publish_failed" in audit_actions


def test_blog_publish_invalid_content_leaves_draft_approved(monkeypatch):
    """Case A: mapper rejects the draft before any Sanity call -- 400, not
    502, since this is a content problem the admin must fix, not an upstream
    failure."""
    rows = [_approved_blog_draft()]
    fake = _shared_blog_fake(monkeypatch, rows)
    monkeypatch.setattr(sanity_client, "get_document", lambda doc_id: None)

    def _raise_validation(*_a, **_kw):
        from app.services.blog_document_mapper import BlogDocumentValidationError
        raise BlogDocumentValidationError("Blog document requires a non-empty slug")

    monkeypatch.setattr(blog_publisher, "publish_sanity_draft", _raise_validation)

    with pytest.raises(HTTPException) as ctx:
        admin_content_studio._publish_blog_draft(rows[0], _OWNER)

    assert ctx.value.status_code == 400
    assert fake.tables["generated_content_drafts"][0]["status"] == "approved"


def test_blog_publish_uncertain_outcome_leaves_draft_approved_not_false_published(monkeypatch):
    """Case E/F: Sanity publish outcome unknown -- draft must NOT be marked
    published on a guess."""
    rows = [_approved_blog_draft()]
    fake = _shared_blog_fake(monkeypatch, rows)
    monkeypatch.setattr(sanity_client, "get_document", lambda doc_id: None)

    def fake_publish(draft, **kw):
        raise blog_publisher.BlogPublicationUncertainError("confirmation timed out")

    monkeypatch.setattr(blog_publisher, "publish_sanity_draft", fake_publish)

    with pytest.raises(HTTPException) as ctx:
        admin_content_studio._publish_blog_draft(rows[0], _OWNER)

    assert ctx.value.status_code == 502
    assert "reconciliation" in ctx.value.detail.lower()
    assert fake.tables["generated_content_drafts"][0]["status"] == "approved"
    audit_actions = [r["action"] for r in fake.tables["audit_log"]]
    assert "draft_publish_uncertain" in audit_actions


def test_blog_publish_case_d_sanity_published_supabase_write_fails(monkeypatch):
    """Case D, the core distributed-inconsistency this section exists for:
    Sanity publish succeeds and is confirmed, but the Supabase write then
    fails. Draft must stay 'approved' (never a fabricated 'published'), and
    the admin must see the uncertain/reconciliation message, not a silent
    success or a raw DB error."""
    rows = [_approved_blog_draft()]
    fake = _shared_blog_fake(monkeypatch, rows)
    monkeypatch.setattr(sanity_client, "get_document", lambda doc_id: None)
    monkeypatch.setattr(blog_publisher, "publish_sanity_draft", lambda draft, **kw: _publish_result())

    def boom(draft_id, owner_id):
        raise Exception("connection reset")

    monkeypatch.setattr(draft_store, "mark_published", boom)

    with pytest.raises(HTTPException) as ctx:
        admin_content_studio._publish_blog_draft(rows[0], _OWNER)

    assert ctx.value.status_code == 502
    assert "reconciliation" in ctx.value.detail.lower()
    assert fake.tables["generated_content_drafts"][0]["status"] == "approved"
    audit_actions = [r["action"] for r in fake.tables["audit_log"]]
    assert "draft_publish_uncertain" in audit_actions


def test_blog_publish_retry_after_case_d_reconciles_via_idempotent_publish(monkeypatch):
    """Step 11 manual retry: admin clicks Publish again after Case D. Sanity
    is already published and matches (blog_publisher's own idempotency
    handles that -- simulated here via already_published=True), so this
    retry only needs to catch Supabase up, not write Sanity a second time."""
    rows = [_approved_blog_draft()]
    fake = _shared_blog_fake(monkeypatch, rows)
    monkeypatch.setattr(sanity_client, "get_document", lambda doc_id: {"publishedAt": "2026-01-01T00:00:00Z"})
    monkeypatch.setattr(blog_publisher, "publish_sanity_draft",
                         lambda draft, **kw: _publish_result(already_published=True, published_at="2026-01-01T00:00:00Z"))

    result = admin_content_studio._publish_blog_draft(rows[0], _OWNER)

    assert result["already_published"] is True
    assert fake.tables["generated_content_drafts"][0]["status"] == "published"


def test_blog_concurrent_publish_second_request_reconciles_without_error(monkeypatch):
    """Step 14: two admins click Publish at nearly the same time. Both pass
    the router's approved-status check; the second request's Sanity call
    still confirms consistent content, but its draft_store.mark_published
    finds the draft already 'published' by the first request. That must not
    surface as a failure -- Supabase is already correct."""
    rows = [_approved_blog_draft()]
    fake = _shared_blog_fake(monkeypatch, rows)
    monkeypatch.setattr(sanity_client, "get_document", lambda doc_id: None)
    monkeypatch.setattr(blog_publisher, "publish_sanity_draft", lambda draft, **kw: _publish_result())

    real_mark_published = draft_store.mark_published

    def racing_mark_published(draft_id, owner_id):
        rows[0]["status"] = "published"  # simulate the other request winning first
        return real_mark_published(draft_id, owner_id)

    monkeypatch.setattr(draft_store, "mark_published", racing_mark_published)

    result = admin_content_studio._publish_blog_draft(rows[0], _OWNER)

    assert result["status"] == "published"
    audit_details = [r["detail"] for r in fake.tables["audit_log"] if r["action"] == "draft_published"]
    assert any(d.get("concurrent_publish") for d in audit_details)


# ── slug immutability after first publish (Module 1 Section 15) ─────────
# published_at is the source of truth for "has this draft ever published":
# mark_published() is the only writer, and nothing ever clears it back to
# None afterward -- not archive(), not the review-demote branch a later
# content/blog-field edit triggers (see update_content above). So a Blog
# draft currently sitting in 'review' or 'approved' after a first publish
# still has published_at set, and its slug must stay locked through that
# whole edit-and-republish cycle, not just while status == 'published'.

def test_blog_slug_editable_on_new_never_published_draft(monkeypatch):
    rows = [_complete_blog_draft(status="draft")]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, slug="new-slug", editor_id="a1")
    assert updated["slug"] == "new-slug"


def test_blog_slug_editable_when_approved_but_never_published(monkeypatch):
    rows = [_complete_blog_draft(status="approved", approved_by="admin-1", approved_at="2026-08-01T00:00:00Z")]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, slug="new-slug", editor_id="a1")
    assert updated["slug"] == "new-slug"


def test_blog_slug_locked_after_publish(monkeypatch):
    rows = [_complete_blog_draft(status="published", published_by="owner-1", published_at="2026-08-02T00:00:00Z")]
    _patched(monkeypatch, rows)
    with pytest.raises(ValueError):
        draft_store.update_content(1, slug="new-slug", editor_id="a1")
    assert rows[0]["slug"] == "hello-world"


def test_blog_slug_locked_while_under_review_after_a_prior_publish(monkeypatch):
    """Content edit after a first publish demotes status to 'review' (existing
    behavior), but published_at survives that demotion -- the slug must stay
    locked through the whole edit-and-republish cycle, not just while the
    status happens to say 'published'."""
    rows = [_complete_blog_draft(status="review", published_by="owner-1", published_at="2026-08-02T00:00:00Z")]
    _patched(monkeypatch, rows)
    with pytest.raises(ValueError):
        draft_store.update_content(1, slug="new-slug", editor_id="a1")


def test_blog_republish_with_unchanged_slug_is_allowed(monkeypatch):
    """Re-publishing (or any other edit) that leaves the slug exactly as it
    was must not trip the lock -- only an actual change is rejected."""
    rows = [_complete_blog_draft(status="published", published_by="owner-1", published_at="2026-08-02T00:00:00Z")]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(1, slug="hello-world", excerpt="Updated teaser.", editor_id="a1")
    assert updated["slug"] == "hello-world"
    assert updated["excerpt"] == "Updated teaser."


def test_blog_title_excerpt_body_cover_still_editable_after_publish(monkeypatch):
    """Only the slug becomes immutable -- every other Blog field (including
    the ones that ride the same PATCH) stays editable post-publish."""
    rows = [_complete_blog_draft(status="published", published_by="owner-1", published_at="2026-08-02T00:00:00Z")]
    _patched(monkeypatch, rows)
    updated = draft_store.update_content(
        1,
        generated_content={"title": "New title", "body": "New body."},
        excerpt="New excerpt.",
        cover_image_ref="image-def456-800x600-jpg",
        editor_id="a1",
    )
    assert updated["generated_content"]["title"] == "New title"
    assert updated["excerpt"] == "New excerpt."
    assert updated["cover_image_ref"] == "image-def456-800x600-jpg"


def test_blog_slug_stays_editable_after_a_failed_publish_attempt(monkeypatch):
    """A definite/uncertain Sanity publish failure never calls mark_published
    (see test_blog_publish_definite_sanity_rejection_leaves_draft_approved /
    test_blog_publish_uncertain_outcome_leaves_draft_approved_not_false_published
    above) -- so published_at is still None and the slug must stay editable."""
    rows = [_approved_blog_draft()]
    fake = _shared_blog_fake(monkeypatch, rows)
    monkeypatch.setattr(sanity_client, "get_document", lambda doc_id: None)

    def fake_publish(draft, **kw):
        raise blog_publisher.BlogPublicationError("Sanity rejected")

    monkeypatch.setattr(blog_publisher, "publish_sanity_draft", fake_publish)
    with pytest.raises(HTTPException):
        admin_content_studio._publish_blog_draft(rows[0], _OWNER)
    assert fake.tables["generated_content_drafts"][0].get("published_at") is None

    updated = draft_store.update_content(1, slug="a-different-slug", editor_id="a1")
    assert updated["slug"] == "a-different-slug"


def test_non_blog_module_unaffected_by_slug_lock(monkeypatch):
    """The lock is scoped to module == 'blog' -- draft_store.update_content is
    shared by every module, none of which has a `slug` column populated, but
    the guard must not somehow reach a non-blog draft."""
    rows = [_draft(module="writing", status="published", published_at="2026-08-02T00:00:00Z",
                    generated_content={"title": "t"}, slug=None)]
    _patched(monkeypatch, rows)
    # writing has no slug field in practice, but the guard must key off module,
    # not merely "slug changed and published_at is set" -- prove that directly.
    updated = draft_store.update_content(1, slug="not-really-a-blog-slug", editor_id="a1")
    assert updated["slug"] == "not-really-a-blog-slug"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
