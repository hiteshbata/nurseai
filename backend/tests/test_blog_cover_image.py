"""Module 1 Section 11: Blog cover-image upload endpoint
(admin_content_studio.upload_cover_image) and its pure helpers. Same style as
test_rbac.py -- the route function is called directly with mocked
draft_store/sanity_client/get_supabase, no live DB, no FastAPI TestClient, no
real Sanity project.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402

from app.routers import admin_content_studio as acs  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402
from app.services import sanity_client as sc  # noqa: E402

JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 20
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 20


class FakeUploadFile:
    def __init__(self, content_type, data):
        self.content_type = content_type
        self._data = data

    async def read(self):
        return self._data


def _draft(module="blog"):
    return {"id": 1, "module": module}


def _user():
    return UserInfo(id="u1", email="u1@example.com", name="U1")


# ── _sniff_image_type: pure, no mocking needed ──────────────────────────

class SniffImageTypeTests(unittest.TestCase):
    def test_valid_jpeg(self):
        self.assertEqual(acs._sniff_image_type(JPEG_BYTES), "image/jpeg")

    def test_valid_png(self):
        self.assertEqual(acs._sniff_image_type(PNG_BYTES), "image/png")

    def test_valid_webp(self):
        self.assertEqual(acs._sniff_image_type(WEBP_BYTES), "image/webp")

    def test_malformed_image_rejected(self):
        self.assertIsNone(acs._sniff_image_type(b"not an image at all"))

    def test_gif_not_in_allowed_set(self):
        self.assertIsNone(acs._sniff_image_type(b"GIF89a" + b"\x00" * 20))

    def test_empty_bytes_rejected(self):
        self.assertIsNone(acs._sniff_image_type(b""))


# ── _validate_cover_image_ref: "" clear sentinel ────────────────────────

class ValidateCoverImageRefTests(unittest.TestCase):
    def test_none_passes_through(self):
        self.assertIsNone(acs._validate_cover_image_ref(None))

    def test_empty_string_is_clear_sentinel(self):
        self.assertEqual(acs._validate_cover_image_ref(""), "")

    def test_valid_ref_passes(self):
        ref = "image-abc123-1200x630-jpg"
        self.assertEqual(acs._validate_cover_image_ref(ref), ref)

    def test_malformed_ref_rejected(self):
        with self.assertRaises(ValueError):
            acs._validate_cover_image_ref("not-a-sanity-ref")


# ── upload_cover_image route function ───────────────────────────────────

class UploadCoverImageTests(unittest.IsolatedAsyncioTestCase):
    async def _call(self, image, draft=None, draft_lookup=None, rate_limited=False,
                     upload_result=None, upload_exc=None):
        get_draft = MagicMock(return_value=draft if draft_lookup is None else draft_lookup)
        upload = MagicMock(side_effect=upload_exc) if upload_exc else MagicMock(return_value=upload_result)
        with patch.object(acs.draft_store, "get_draft", get_draft), \
             patch.object(acs._cover_image_rate_limiter, "is_rate_limited", return_value=rate_limited), \
             patch.object(acs.sanity_client, "upload_image_asset", upload), \
             patch.object(acs, "_write_audit_log") as audit, \
             patch.object(acs, "get_supabase", return_value=MagicMock()):
            result = await acs.upload_cover_image(draft_id=1, image=image, current_user=_user())
            return result, upload, audit

    async def test_draft_not_found_returns_404(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._call(FakeUploadFile("image/jpeg", JPEG_BYTES), draft=None)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_non_blog_module_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._call(FakeUploadFile("image/jpeg", JPEG_BYTES), draft=_draft(module="reading"))
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_rate_limited_returns_429(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._call(FakeUploadFile("image/jpeg", JPEG_BYTES), draft=_draft(), rate_limited=True)
        self.assertEqual(ctx.exception.status_code, 429)

    async def test_unsupported_content_type_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._call(FakeUploadFile("image/gif", b"GIF89a"), draft=_draft())
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_oversized_image_rejected(self):
        oversized = JPEG_BYTES + b"\x00" * acs.COVER_IMAGE_MAX_BYTES
        with self.assertRaises(HTTPException) as ctx:
            await self._call(FakeUploadFile("image/jpeg", oversized), draft=_draft())
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_mime_spoofing_rejected(self):
        """Declared image/png but the bytes are actually a JPEG -- the magic-byte
        sniff (Step 18) must catch this even though the header alone would pass."""
        with self.assertRaises(HTTPException) as ctx:
            await self._call(FakeUploadFile("image/png", JPEG_BYTES), draft=_draft())
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_valid_jpeg_upload_succeeds(self):
        result, upload, audit = await self._call(
            FakeUploadFile("image/jpeg", JPEG_BYTES), draft=_draft(),
            upload_result={"ref": "image-abc-100x100-jpg", "url": "https://cdn.sanity.io/x.jpg"},
        )
        self.assertEqual(result, {"cover_image_ref": "image-abc-100x100-jpg", "preview_url": "https://cdn.sanity.io/x.jpg"})
        upload.assert_called_once_with(JPEG_BYTES, "image/jpeg")
        audit.assert_called_once()

    async def test_valid_png_upload_succeeds(self):
        result, _, _ = await self._call(
            FakeUploadFile("image/png", PNG_BYTES), draft=_draft(),
            upload_result={"ref": "image-def-100x100-png", "url": "https://cdn.sanity.io/y.png"},
        )
        self.assertEqual(result["cover_image_ref"], "image-def-100x100-png")

    async def test_valid_webp_upload_succeeds(self):
        result, _, _ = await self._call(
            FakeUploadFile("image/webp", WEBP_BYTES), draft=_draft(),
            upload_result={"ref": "image-ghi-100x100-webp", "url": "https://cdn.sanity.io/z.webp"},
        )
        self.assertEqual(result["cover_image_ref"], "image-ghi-100x100-webp")

    async def test_sanity_config_error_returns_503(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._call(FakeUploadFile("image/jpeg", JPEG_BYTES), draft=_draft(), upload_exc=sc.SanityConfigError("x"))
        self.assertEqual(ctx.exception.status_code, 503)

    async def test_sanity_dataset_isolation_error_returns_503(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._call(FakeUploadFile("image/jpeg", JPEG_BYTES), draft=_draft(), upload_exc=sc.SanityDatasetIsolationError("x"))
        self.assertEqual(ctx.exception.status_code, 503)

    async def test_sanity_auth_error_returns_502(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._call(FakeUploadFile("image/jpeg", JPEG_BYTES), draft=_draft(), upload_exc=sc.SanityAuthError("x"))
        self.assertEqual(ctx.exception.status_code, 502)

    async def test_sanity_network_error_returns_502(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._call(FakeUploadFile("image/jpeg", JPEG_BYTES), draft=_draft(), upload_exc=sc.SanityNetworkError("x"))
        self.assertEqual(ctx.exception.status_code, 502)

    async def test_no_sanity_call_when_draft_missing(self):
        get_draft = MagicMock(return_value=None)
        upload = MagicMock()
        with patch.object(acs.draft_store, "get_draft", get_draft), \
             patch.object(acs.sanity_client, "upload_image_asset", upload):
            with self.assertRaises(HTTPException):
                await acs.upload_cover_image(draft_id=1, image=FakeUploadFile("image/jpeg", JPEG_BYTES), current_user=_user())
        upload.assert_not_called()

    async def test_no_sanity_call_when_module_not_blog(self):
        get_draft = MagicMock(return_value=_draft(module="reading"))
        upload = MagicMock()
        with patch.object(acs.draft_store, "get_draft", get_draft), \
             patch.object(acs.sanity_client, "upload_image_asset", upload):
            with self.assertRaises(HTTPException):
                await acs.upload_cover_image(draft_id=1, image=FakeUploadFile("image/jpeg", JPEG_BYTES), current_user=_user())
        upload.assert_not_called()


# ── save_draft route function: duplicate Blog slug -> 409 ───────────────
# Module 1 Section 15G. draft_store.create_draft is mocked directly to raise
# DuplicateSlugError -- the DB-level unique-index behavior itself is covered
# in test_draft_workflow.py; this only proves the router translates that
# service-layer exception into a safe 409, not a 500.

class SaveDraftDuplicateSlugTests(unittest.TestCase):
    def _req(self, **overrides):
        fields = dict(
            module="blog", draft_name="A Post", ai_title=None, metadata={}, prompt={},
            generated_content={"title": "A Post"}, validation_warnings=[], model_used=None,
            slug="a-post", excerpt=None, cover_image_ref=None,
        )
        fields.update(overrides)
        return acs.SaveDraftRequest(**fields)

    def test_duplicate_slug_returns_409_not_500(self):
        create = MagicMock(side_effect=acs.draft_store.DuplicateSlugError(
            'Blog slug "a-post" is already in use'
        ))
        with patch.object(acs.draft_store, "create_draft", create):
            with self.assertRaises(HTTPException) as ctx:
                acs.save_draft(self._req(), current_user=_user())
        self.assertEqual(ctx.exception.status_code, 409)

    def test_duplicate_slug_message_is_safe(self):
        create = MagicMock(side_effect=acs.draft_store.DuplicateSlugError(
            'Blog slug "a-post" is already in use'
        ))
        with patch.object(acs.draft_store, "create_draft", create):
            with self.assertRaises(HTTPException) as ctx:
                acs.save_draft(self._req(), current_user=_user())
        detail = str(ctx.exception.detail).lower()
        self.assertIn("already in use", detail)
        for leaky in ("constraint", "postgres", "sql", "traceback", "supabase.co", "uidx"):
            self.assertNotIn(leaky, detail)

    def test_distinct_slug_still_saves_successfully(self):
        created = {"id": 1, "module": "blog", "slug": "a-different-post"}
        create = MagicMock(return_value=created)
        with patch.object(acs.draft_store, "create_draft", create), \
             patch.object(acs, "_write_audit_log") as audit, \
             patch.object(acs, "get_supabase", return_value=MagicMock()):
            result = acs.save_draft(self._req(slug="a-different-post"), current_user=_user())
        self.assertEqual(result, created)
        audit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
