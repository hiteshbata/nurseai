-- Listening cleanup: the original track-based listening module (2026-07-23) was
-- replaced by the reading-mirror tests/sections model. Remove its dead objects and
-- fix the audio bucket, which the old migration created PRIVATE -- the new code
-- serves audio via public URLs (get_public_url + <audio src>), so it must be public.
-- Apply in the Supabase SQL editor.

-- 1. Serve listening audio via public URLs.
update storage.buckets set public = true where id = 'listening-audio';

-- 2. Drop the dead questions.track_id (superseded by section_id). No rows reference it.
drop index if exists public.questions_track_id_idx;
alter table public.questions drop column if exists track_id;

-- 3. Drop the empty, unreferenced track table.
drop table if exists public.listening_tracks;
