"""Phase 7A: Content Studio draft audio generation
(admin_content_studio.generate_draft_audio) and its listening_audio helpers
(transcript_hash, get_audio_status). Same style as test_blog_cover_image.py --
the route function is called directly with mocked draft_store/listening_audio/
storage, no live DB, no OpenAI, no ffmpeg, no FastAPI TestClient.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402

from app.routers import admin_content_studio as acs  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402
from app.services import draft_publisher, listening_audio  # noqa: E402


def _turns(n=2, speaker="Nurse"):
    return [{"speaker": speaker, "text": f"line {i}"} for i in range(n)]


def _extract(**overrides):
    base = {"title": "Extract 1", "transcript": _turns(), "questions": []}
    base.update(overrides)
    return base


def _content(extracts):
    return {"part": "B", "audio_mode": "dialogue", "extracts": extracts}


def _draft(module="listening", status="draft", extracts=None, **overrides):
    base = {
        "id": 1, "module": module, "status": status,
        "generated_content": _content(extracts if extracts is not None else [_extract()]),
    }
    base.update(overrides)
    return base


def _user():
    return UserInfo(id="u1", email="u1@example.com", name="U1")


# ── listening_audio.transcript_hash / get_audio_status: pure, no mocking ──

class TranscriptHashTests(unittest.TestCase):
    def test_deterministic(self):
        turns = _turns(3)
        self.assertEqual(listening_audio.transcript_hash(turns), listening_audio.transcript_hash(turns))

    def test_order_matters(self):
        a = [{"speaker": "A", "text": "1"}, {"speaker": "B", "text": "2"}]
        b = [{"speaker": "B", "text": "2"}, {"speaker": "A", "text": "1"}]
        self.assertNotEqual(listening_audio.transcript_hash(a), listening_audio.transcript_hash(b))

    def test_speaker_label_matters(self):
        a = [{"speaker": "A", "text": "hi"}]
        b = [{"speaker": "B", "text": "hi"}]
        self.assertNotEqual(listening_audio.transcript_hash(a), listening_audio.transcript_hash(b))

    def test_text_matters(self):
        a = [{"speaker": "A", "text": "hi"}]
        b = [{"speaker": "A", "text": "bye"}]
        self.assertNotEqual(listening_audio.transcript_hash(a), listening_audio.transcript_hash(b))

    def test_empty_list(self):
        self.assertEqual(listening_audio.transcript_hash([]), listening_audio.transcript_hash([]))


class AudioStatusTests(unittest.TestCase):
    def test_not_generated_no_audio_url(self):
        self.assertEqual(listening_audio.get_audio_status(_extract()), "NOT_GENERATED")

    def test_not_generated_no_hash(self):
        ex = _extract(audio_url="https://x/1.mp3")
        self.assertEqual(listening_audio.get_audio_status(ex), "NOT_GENERATED")

    def test_ready_when_hash_matches(self):
        turns = _turns()
        ex = _extract(transcript=turns, audio_url="https://x/1.mp3", audio_transcript_hash=listening_audio.transcript_hash(turns))
        self.assertEqual(listening_audio.get_audio_status(ex), "READY")

    def test_outdated_when_hash_differs(self):
        ex = _extract(transcript=_turns(), audio_url="https://x/1.mp3", audio_transcript_hash="stale-hash")
        self.assertEqual(listening_audio.get_audio_status(ex), "OUTDATED")


# ── generate_draft_audio route function ─────────────────────────────────

class GenerateDraftAudioTests(unittest.IsolatedAsyncioTestCase):
    async def _call(
        self, draft_id=1, extract_index=0, draft=None, rate_limited=False,
        tts_result=b"mp3-bytes", tts_exc=None, upload_result="https://cdn/x.mp3", upload_exc=None,
        update_content_result="__default__", update_content_exc=None, duration=1.5,
    ):
        req = acs.GenerateDraftAudioRequest(extract_index=extract_index)
        tts = AsyncMock(side_effect=tts_exc) if tts_exc else AsyncMock(return_value=tts_result)
        upload = AsyncMock(side_effect=upload_exc) if upload_exc else AsyncMock(return_value=upload_result)
        get_draft = MagicMock(return_value=draft)
        if update_content_exc:
            update_content = MagicMock(side_effect=update_content_exc)
        elif update_content_result == "__default__":
            update_content = MagicMock(side_effect=lambda draft_id, generated_content=None, **_k: {**draft, "generated_content": generated_content, "status": "review"})
        else:
            update_content = MagicMock(return_value=update_content_result)

        with patch.object(acs, "_upload_to_bucket", upload), \
             patch.object(acs.draft_store, "get_draft", get_draft), \
             patch.object(acs.draft_store, "update_content", update_content), \
             patch.object(acs._draft_audio_rate_limiter, "is_rate_limited", return_value=rate_limited), \
             patch.object(acs.listening_audio, "generate_two_speaker_audio", tts), \
             patch.object(acs.listening_audio, "probe_duration_seconds", AsyncMock(return_value=duration)), \
             patch.object(acs, "_write_audit_log") as audit, \
             patch.object(acs, "get_supabase", return_value=MagicMock()):
            result = await acs.generate_draft_audio(draft_id=draft_id, req=req, current_user=_user())
            return result, tts, upload, update_content, audit

    # 1. valid dialogue generation
    async def test_valid_dialogue_generation(self):
        draft = _draft(extracts=[_extract(transcript=_turns(2, "Nurse"))])
        result, tts, upload, update_content, audit = await self._call(draft=draft)
        self.assertEqual(result["audio_url"], "https://cdn/x.mp3")
        self.assertEqual(result["extract_index"], 0)
        tts.assert_awaited_once()
        upload.assert_awaited_once()
        audit.assert_called_once()

    # 2. valid monologue generation
    async def test_valid_monologue_generation(self):
        turns = [{"speaker": "Nurse", "text": "line 0"}, {"speaker": "Nurse", "text": "line 1"}]
        draft = _draft(extracts=[_extract(transcript=turns, audio_mode="monologue")])
        result, tts, upload, update_content, audit = await self._call(draft=draft)
        self.assertEqual(result["audio_url"], "https://cdn/x.mp3")
        tts.assert_awaited_once_with(turns, None, None)

    # 3. invalid draft id
    async def test_invalid_draft_id_404(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._call(draft=None)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail["code"], "draft_not_found")

    # 4. non-listening draft rejected
    async def test_non_listening_draft_rejected(self):
        draft = _draft(module="reading")
        with self.assertRaises(HTTPException) as ctx:
            await self._call(draft=draft)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["code"], "not_listening_draft")

    # 5. invalid extract index
    async def test_invalid_extract_index_rejected(self):
        draft = _draft(extracts=[_extract()])
        with self.assertRaises(HTTPException) as ctx:
            await self._call(draft=draft, extract_index=5)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["code"], "invalid_extract_index")

    # 6. empty transcript rejected
    async def test_empty_transcript_rejected(self):
        draft = _draft(extracts=[_extract(transcript=[])])
        with self.assertRaises(HTTPException) as ctx:
            await self._call(draft=draft)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["code"], "transcript_missing")

    # 7. TTS failure
    async def test_tts_failure_surfaced(self):
        draft = _draft(extracts=[_extract()])
        with self.assertRaises(HTTPException) as ctx:
            await self._call(draft=draft, tts_exc=listening_audio.TtsError("bad turn"))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["code"], "audio_generation_failed")

    async def test_tts_provider_failure_returns_502(self):
        draft = _draft(extracts=[_extract()])
        with self.assertRaises(HTTPException) as ctx:
            await self._call(draft=draft, tts_exc=RuntimeError("openai_tts_http_500"))
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertEqual(ctx.exception.detail["code"], "audio_generation_failed")

    # 8. storage upload failure
    async def test_storage_upload_failure(self):
        draft = _draft(extracts=[_extract()])
        with self.assertRaises(HTTPException) as ctx:
            await self._call(draft=draft, upload_exc=RuntimeError("bucket down"))
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertEqual(ctx.exception.detail["code"], "storage_upload_failed")

    # no partial mutation: update_content never called if upload fails
    async def test_no_draft_update_when_upload_fails(self):
        draft = _draft(extracts=[_extract()])
        update_content = MagicMock()
        with patch.object(acs, "_upload_to_bucket", AsyncMock(side_effect=RuntimeError("bucket down"))), \
             patch.object(acs.draft_store, "get_draft", MagicMock(return_value=draft)), \
             patch.object(acs.draft_store, "update_content", update_content), \
             patch.object(acs._draft_audio_rate_limiter, "is_rate_limited", return_value=False), \
             patch.object(acs.listening_audio, "generate_two_speaker_audio", AsyncMock(return_value=b"mp3")), \
             patch.object(acs.listening_audio, "probe_duration_seconds", AsyncMock(return_value=1.5)), \
             patch.object(acs, "get_supabase", return_value=MagicMock()):
            with self.assertRaises(HTTPException):
                await acs.generate_draft_audio(draft_id=1, req=acs.GenerateDraftAudioRequest(extract_index=0), current_user=_user())
        update_content.assert_not_called()

    # 9 / 10 / 11: only the selected extract changes, siblings preserved
    async def test_only_selected_extract_changes_siblings_preserved(self):
        sibling = _extract(title="Extract 2", transcript=_turns(2, "Doctor"), audio_url="https://old/sibling.mp3")
        target = _extract(title="Extract 1", transcript=_turns(2, "Nurse"))
        draft = _draft(extracts=[target, sibling])

        captured = {}

        def fake_update_content(draft_id, generated_content=None, **_k):
            captured["generated_content"] = generated_content
            return {**draft, "generated_content": generated_content}

        with patch.object(acs, "_upload_to_bucket", AsyncMock(return_value="https://cdn/x.mp3")), \
             patch.object(acs.draft_store, "get_draft", MagicMock(return_value=draft)), \
             patch.object(acs.draft_store, "update_content", MagicMock(side_effect=fake_update_content)), \
             patch.object(acs._draft_audio_rate_limiter, "is_rate_limited", return_value=False), \
             patch.object(acs.listening_audio, "generate_two_speaker_audio", AsyncMock(return_value=b"mp3")), \
             patch.object(acs.listening_audio, "probe_duration_seconds", AsyncMock(return_value=1.5)), \
             patch.object(acs, "_write_audit_log"), \
             patch.object(acs, "get_supabase", return_value=MagicMock()):
            await acs.generate_draft_audio(draft_id=1, req=acs.GenerateDraftAudioRequest(extract_index=0), current_user=_user())

        new_extracts = captured["generated_content"]["extracts"]
        self.assertEqual(new_extracts[1], sibling)  # sibling byte-for-byte unchanged
        self.assertEqual(new_extracts[0]["audio_url"], "https://cdn/x.mp3")
        self.assertEqual(new_extracts[0]["title"], "Extract 1")  # non-audio fields preserved

    # 12. transcript hash deterministic -- covered by TranscriptHashTests above

    # 13 / 14: duration + generated_at persisted
    async def test_duration_and_generated_at_in_response(self):
        draft = _draft(extracts=[_extract()])
        result, *_ = await self._call(draft=draft, duration=12.34)
        self.assertEqual(result["duration_seconds"], 12.34)
        self.assertTrue(result["audio_generated_at"])
        datetime.fromisoformat(result["audio_generated_at"])  # parses as ISO timestamp

    # 15. approved draft becomes review through update_content workflow
    async def test_approved_draft_demoted_to_review(self):
        draft = _draft(status="approved", extracts=[_extract()])
        real_update_content = MagicMock(side_effect=lambda draft_id, generated_content=None, **_k: {
            **draft, "generated_content": generated_content, "status": "review",
            "approved_by": None, "approved_at": None,
        })
        with patch.object(acs, "_upload_to_bucket", AsyncMock(return_value="https://cdn/x.mp3")), \
             patch.object(acs.draft_store, "get_draft", MagicMock(return_value=draft)), \
             patch.object(acs.draft_store, "update_content", real_update_content), \
             patch.object(acs._draft_audio_rate_limiter, "is_rate_limited", return_value=False), \
             patch.object(acs.listening_audio, "generate_two_speaker_audio", AsyncMock(return_value=b"mp3")), \
             patch.object(acs.listening_audio, "probe_duration_seconds", AsyncMock(return_value=1.5)), \
             patch.object(acs, "_write_audit_log"), \
             patch.object(acs, "get_supabase", return_value=MagicMock()):
            await acs.generate_draft_audio(draft_id=1, req=acs.GenerateDraftAudioRequest(extract_index=0), current_user=_user())
        real_update_content.assert_called_once()
        _, kwargs = real_update_content.call_args
        self.assertIn("generated_content", kwargs)

    # Phase 7K: Generate Voice has no status gate -- must work unchanged on
    # review and approved drafts (the two statuses content-team iteration
    # happens in), not just the 'draft' status the other tests above default to.
    async def test_generation_works_on_review_status_draft(self):
        draft = _draft(status="review", extracts=[_extract()])
        result, tts, upload, update_content, audit = await self._call(draft=draft)
        self.assertEqual(result["audio_url"], "https://cdn/x.mp3")
        tts.assert_awaited_once()

    async def test_generation_works_on_approved_status_draft(self):
        draft = _draft(status="approved", extracts=[_extract()])
        result, tts, upload, update_content, audit = await self._call(draft=draft)
        self.assertEqual(result["audio_url"], "https://cdn/x.mp3")
        tts.assert_awaited_once()

    # Phase 7K: same demote-to-review behavior as approved (test above), for
    # a published draft -- and audio generation only ever calls
    # draft_store.update_content (the draft table), never draft_publisher /
    # mark_published, so a published draft's live learner-facing row is never
    # touched by this endpoint.
    async def test_published_draft_demoted_to_review_via_audio_generation(self):
        draft = _draft(status="published", published_by="owner-1", published_at="2026-08-01T00:00:00Z",
                        extracts=[_extract()])
        real_update_content = MagicMock(side_effect=lambda draft_id, generated_content=None, **_k: {
            **draft, "generated_content": generated_content, "status": "review",
            "approved_by": None, "approved_at": None,
        })
        with patch.object(acs, "_upload_to_bucket", AsyncMock(return_value="https://cdn/x.mp3")), \
             patch.object(acs.draft_store, "get_draft", MagicMock(return_value=draft)), \
             patch.object(acs.draft_store, "update_content", real_update_content), \
             patch.object(acs._draft_audio_rate_limiter, "is_rate_limited", return_value=False), \
             patch.object(acs.listening_audio, "generate_two_speaker_audio", AsyncMock(return_value=b"mp3")), \
             patch.object(acs.listening_audio, "probe_duration_seconds", AsyncMock(return_value=1.5)), \
             patch.object(acs, "_write_audit_log"), \
             patch.object(acs, "draft_publisher") as publisher, \
             patch.object(acs, "get_supabase", return_value=MagicMock()):
            result = await acs.generate_draft_audio(draft_id=1, req=acs.GenerateDraftAudioRequest(extract_index=0), current_user=_user())
        real_update_content.assert_called_once()
        self.assertEqual(result["audio_url"], "https://cdn/x.mp3")
        publisher.publish.assert_not_called()

    # 16. no duplicate audio metadata fields
    async def test_updated_extract_has_single_set_of_audio_fields(self):
        captured = {}

        def fake_update_content(draft_id, generated_content=None, **_k):
            captured["generated_content"] = generated_content
            return {"generated_content": generated_content}

        draft = _draft(extracts=[_extract()])
        with patch.object(acs, "_upload_to_bucket", AsyncMock(return_value="https://cdn/x.mp3")), \
             patch.object(acs.draft_store, "get_draft", MagicMock(return_value=draft)), \
             patch.object(acs.draft_store, "update_content", MagicMock(side_effect=fake_update_content)), \
             patch.object(acs._draft_audio_rate_limiter, "is_rate_limited", return_value=False), \
             patch.object(acs.listening_audio, "generate_two_speaker_audio", AsyncMock(return_value=b"mp3")), \
             patch.object(acs.listening_audio, "probe_duration_seconds", AsyncMock(return_value=1.5)), \
             patch.object(acs, "_write_audit_log"), \
             patch.object(acs, "get_supabase", return_value=MagicMock()):
            await acs.generate_draft_audio(draft_id=1, req=acs.GenerateDraftAudioRequest(extract_index=0), current_user=_user())
        ex = captured["generated_content"]["extracts"][0]
        audio_keys = [k for k in ex if k.startswith("audio_")]
        self.assertEqual(sorted(audio_keys), ["audio_duration_seconds", "audio_generated_at", "audio_transcript_hash", "audio_url"])

    # 17. existing audio on siblings preserved -- see test_only_selected_extract_changes_siblings_preserved

    async def test_rate_limited_returns_429(self):
        draft = _draft(extracts=[_extract()])
        with self.assertRaises(HTTPException) as ctx:
            await self._call(draft=draft, rate_limited=True)
        self.assertEqual(ctx.exception.status_code, 429)

    async def test_draft_deleted_mid_flight_cleans_up_and_404s(self):
        draft = _draft(extracts=[_extract()])
        remove = MagicMock()
        supabase = MagicMock()
        supabase.storage.from_.return_value.remove = remove
        with patch.object(acs, "_upload_to_bucket", AsyncMock(return_value="https://cdn/x.mp3")), \
             patch.object(acs.draft_store, "get_draft", MagicMock(return_value=draft)), \
             patch.object(acs.draft_store, "update_content", MagicMock(return_value=None)), \
             patch.object(acs._draft_audio_rate_limiter, "is_rate_limited", return_value=False), \
             patch.object(acs.listening_audio, "generate_two_speaker_audio", AsyncMock(return_value=b"mp3")), \
             patch.object(acs.listening_audio, "probe_duration_seconds", AsyncMock(return_value=1.5)), \
             patch.object(acs, "get_supabase", return_value=supabase):
            with self.assertRaises(HTTPException) as ctx:
                await acs.generate_draft_audio(draft_id=1, req=acs.GenerateDraftAudioRequest(extract_index=0), current_user=_user())
        self.assertEqual(ctx.exception.status_code, 404)
        remove.assert_called_once()


# ── Phase 7E: publish gate on extracts[] audio readiness ─────────────────
# draft_publisher.build_preview/publish must block Listening Part A/B/C
# publish when any extract's audio is NOT_GENERATED or OUTDATED
# (listening_audio.get_audio_status). All supabase access is mocked --
# these tests never touch a real DB and assert zero writes on the blocked
# path. No TTS/Gemini call anywhere in this file.

def _fake_supabase_empty():
    """Every table()/select()/eq()/ilike()/limit() call chains back to the
    same mock and every execute().data is []. Lets build_preview/publish's
    existing-row + duplicate-title lookups run to completion (finding
    nothing) without a real Supabase client."""
    sb = MagicMock()
    tbl = MagicMock()
    for method in ("select", "eq", "ilike", "limit", "insert", "update", "delete"):
        getattr(tbl, method).return_value = tbl
    tbl.execute.return_value.data = []
    sb.table.return_value = tbl
    return sb


def _gate_extracts(n, ready_indexes=(), outdated_indexes=()):
    """n extracts, each with a distinct transcript. Extracts in
    ready_indexes get audio matching their current transcript hash
    (READY); extracts in outdated_indexes get audio whose hash no longer
    matches (OUTDATED, simulating a transcript edit after generation);
    everything else stays NOT_GENERATED (no audio_url at all)."""
    out = []
    for i in range(n):
        turns = _turns(2, f"Speaker{i}")
        ex = _extract(title=f"Extract {i}", transcript=turns)
        if i in ready_indexes:
            ex["audio_url"] = f"https://cdn/{i}.mp3"
            ex["audio_transcript_hash"] = listening_audio.transcript_hash(turns)
        if i in outdated_indexes:
            ex["audio_url"] = f"https://cdn/{i}.mp3"
            ex["audio_transcript_hash"] = "stale-hash-does-not-match-current-transcript"
        out.append(ex)
    return out


def _listening_draft(part, extracts, status="approved", draft_id=1):
    return {
        "id": draft_id, "module": "listening", "status": status,
        "generated_content": {"part": part, "audio_mode": "dialogue", "extracts": extracts},
    }


class PublishAudioGateTests(unittest.TestCase):
    """Service-level: draft_publisher.build_preview / .publish directly."""

    # 1. no audio at all -- Part B requires 6
    def test_part_b_no_audio_blocks_with_all_six_missing(self):
        draft = _listening_draft("B", _gate_extracts(6))
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb):
            with self.assertRaises(draft_publisher.AudioNotReadyError) as ctx:
                draft_publisher.build_preview(draft)
        self.assertEqual(ctx.exception.part, "B")
        self.assertEqual(ctx.exception.missing_indexes, [0, 1, 2, 3, 4, 5])
        self.assertEqual(ctx.exception.outdated_indexes, [])
        self.assertEqual(ctx.exception.reason, "audio_missing")
        sb.table.return_value.insert.assert_not_called()
        sb.table.return_value.update.assert_not_called()

    # same case, through publish() (POST /publish), not just the preview
    def test_part_b_no_audio_blocks_publish_with_zero_writes(self):
        draft = _listening_draft("B", _gate_extracts(6))
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb):
            with self.assertRaises(draft_publisher.AudioNotReadyError) as ctx:
                draft_publisher.publish(draft, published_by="admin-1")
        self.assertEqual(ctx.exception.missing_indexes, [0, 1, 2, 3, 4, 5])
        sb.table.return_value.insert.assert_not_called()
        sb.table.return_value.update.assert_not_called()

    # 2. partial audio -- only extract 0 ready, 1-5 missing
    def test_part_b_partial_audio_blocks_with_indexes_1_to_5(self):
        draft = _listening_draft("B", _gate_extracts(6, ready_indexes=[0]))
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb):
            with self.assertRaises(draft_publisher.AudioNotReadyError) as ctx:
                draft_publisher.build_preview(draft)
        self.assertEqual(ctx.exception.missing_indexes, [1, 2, 3, 4, 5])
        self.assertEqual(ctx.exception.outdated_indexes, [])
        self.assertEqual(ctx.exception.reason, "audio_missing")

    # 3. outdated audio -- extract 0 had current audio, transcript then
    # edited without regenerating
    def test_part_b_outdated_audio_blocks_with_audio_outdated_reason(self):
        extracts = _gate_extracts(6, ready_indexes=range(6))
        extracts[0]["transcript"] = _turns(3, "Nurse-edited-after-audio")  # edit, no regen
        draft = _listening_draft("B", extracts)
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb):
            with self.assertRaises(draft_publisher.AudioNotReadyError) as ctx:
                draft_publisher.build_preview(draft)
        self.assertEqual(ctx.exception.missing_indexes, [])
        self.assertEqual(ctx.exception.outdated_indexes, [0])
        self.assertEqual(ctx.exception.reason, "audio_outdated")
        sb.table.return_value.insert.assert_not_called()
        sb.table.return_value.update.assert_not_called()

    # 4. all audio ready -- gate passes, preview succeeds (pre-publish only,
    # never calls insert/update -- build_preview is a dry run by contract)
    def test_part_b_all_audio_ready_passes_gate(self):
        draft = _listening_draft("B", _gate_extracts(6, ready_indexes=range(6)))
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb):
            preview = draft_publisher.build_preview(draft)
        section_records = [r for r in preview["records"] if r.get("table") == "listening_sections"]
        self.assertEqual(len(section_records), 6)
        sb.table.return_value.insert.assert_not_called()
        sb.table.return_value.update.assert_not_called()

    # 5. extract isolation -- regenerating extract 0 must not touch siblings'
    # audio_url / audio_transcript_hash / other metadata
    def test_extract_isolation_regenerating_one_leaves_siblings_untouched(self):
        extracts = _gate_extracts(6, ready_indexes=range(6))
        original_siblings = [dict(e) for e in extracts[1:]]
        new_turns = _turns(3, "Nurse-v2")
        extracts[0] = {
            **extracts[0], "transcript": new_turns,
            "audio_url": "https://cdn/0-regenerated.mp3",
            "audio_transcript_hash": listening_audio.transcript_hash(new_turns),
        }
        draft_publisher._check_listening_audio_gate("B", extracts)  # all still READY, no raise
        for i, sibling in enumerate(extracts[1:], start=1):
            self.assertEqual(sibling, original_siblings[i - 1])

    # 6. Part A -- exact requirement is 2 extracts
    def test_part_a_exact_two_extract_requirement_no_audio(self):
        draft = _listening_draft("A", _gate_extracts(2))
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb):
            with self.assertRaises(draft_publisher.AudioNotReadyError) as ctx:
                draft_publisher.build_preview(draft)
        self.assertEqual(ctx.exception.part, "A")
        self.assertEqual(ctx.exception.missing_indexes, [0, 1])

    def test_part_a_all_ready_passes_gate(self):
        draft = _listening_draft("A", _gate_extracts(2, ready_indexes=[0, 1]))
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb):
            preview = draft_publisher.build_preview(draft)
        self.assertEqual(len([r for r in preview["records"] if r.get("table") == "listening_sections"]), 2)

    # 7. Part C -- exact requirement is 2 extracts
    def test_part_c_exact_two_extract_requirement_no_audio(self):
        draft = _listening_draft("C", _gate_extracts(2))
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb):
            with self.assertRaises(draft_publisher.AudioNotReadyError) as ctx:
                draft_publisher.build_preview(draft)
        self.assertEqual(ctx.exception.part, "C")
        self.assertEqual(ctx.exception.missing_indexes, [0, 1])

    def test_part_c_all_ready_passes_gate(self):
        draft = _listening_draft("C", _gate_extracts(2, ready_indexes=[0, 1]))
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb):
            preview = draft_publisher.build_preview(draft)
        self.assertEqual(len([r for r in preview["records"] if r.get("table") == "listening_sections"]), 2)

    # structural validation still wins over the audio gate: a draft missing
    # extracts[] entirely raises InvalidPartError, not AudioNotReadyError
    def test_missing_extracts_key_raises_invalid_part_not_audio_error(self):
        draft = _listening_draft("B", extracts=[])
        draft["generated_content"].pop("extracts")
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb):
            with self.assertRaises(draft_publisher.InvalidPartError):
                draft_publisher.build_preview(draft)


class LegacyListeningPublishUnaffectedTests(unittest.TestCase):
    """Legacy flat Listening drafts (no extracts[] contract) must never be
    routed through the new audio gate."""

    def test_legacy_flat_listening_never_calls_get_audio_status(self):
        draft = {
            "id": 9, "module": "listening", "status": "approved",
            "generated_content": {
                "part": None, "transcript": _turns(2), "questions": [],
                "audio_url": "https://cdn/legacy-section.mp3",
            },
        }
        sb = _fake_supabase_empty()
        with patch.object(draft_publisher, "get_supabase", return_value=sb), \
             patch.object(draft_publisher.listening_audio, "get_audio_status") as status_probe:
            preview = draft_publisher.build_preview(draft)
        status_probe.assert_not_called()
        self.assertEqual(preview["records"][0]["table"], "listening_sections")
        self.assertEqual(preview["records"][0]["fields"]["audio_url"], "https://cdn/legacy-section.mp3")


class PublishRouterAudioGateTests(unittest.TestCase):
    """Router-level: admin_content_studio.get_publish_preview / publish_draft
    surface AudioNotReadyError as an HTTP 409 identifying part + indexes."""

    def test_publish_preview_409_identifies_part_and_missing_indexes(self):
        draft = _draft(status="approved", extracts=_gate_extracts(6))  # part "B" via _content()
        sb = _fake_supabase_empty()
        with patch.object(acs.draft_store, "get_draft", return_value=draft), \
             patch.object(acs.draft_publisher, "get_supabase", return_value=sb):
            with self.assertRaises(HTTPException) as ctx:
                acs.get_publish_preview(draft_id=1, current_user=_user())
        self.assertEqual(ctx.exception.status_code, 409)
        detail = ctx.exception.detail
        self.assertEqual(detail["error"], "audio_missing")
        self.assertEqual(detail["part"], "B")
        self.assertEqual(detail["missing_audio_indexes"], [0, 1, 2, 3, 4, 5])
        self.assertEqual(detail["outdated_audio_indexes"], [])

    def test_publish_409_same_gate_zero_writes(self):
        draft = _draft(status="approved", extracts=_gate_extracts(6))
        sb = _fake_supabase_empty()
        with patch.object(acs.draft_store, "get_draft", return_value=draft), \
             patch.object(acs.draft_publisher, "get_supabase", return_value=sb):
            with self.assertRaises(HTTPException) as ctx:
                acs.publish_draft(draft_id=1, current_user=_user())
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["part"], "B")
        sb.table.return_value.insert.assert_not_called()
        sb.table.return_value.update.assert_not_called()

    def test_publish_preview_409_outdated_reason(self):
        extracts = _gate_extracts(6, ready_indexes=range(6))
        extracts[2]["transcript"] = _turns(3, "edited")
        draft = _draft(status="approved", extracts=extracts)
        sb = _fake_supabase_empty()
        with patch.object(acs.draft_store, "get_draft", return_value=draft), \
             patch.object(acs.draft_publisher, "get_supabase", return_value=sb):
            with self.assertRaises(HTTPException) as ctx:
                acs.get_publish_preview(draft_id=1, current_user=_user())
        detail = ctx.exception.detail
        self.assertEqual(detail["error"], "audio_outdated")
        self.assertEqual(detail["outdated_audio_indexes"], [2])
        self.assertEqual(detail["missing_audio_indexes"], [])


if __name__ == "__main__":
    unittest.main()
