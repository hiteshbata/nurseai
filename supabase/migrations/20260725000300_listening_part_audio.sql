-- Listening audio moved from per-section to per-PART: each test has one audio per
-- part (A/B/C), which includes the narrator + all that part's extracts, and plays
-- once when the student enters that part. Stored as {"A": url, "B": url, "C": url}.
-- (listening_sections.audio_url is left in place but unused by the player now.)
-- Apply in the Supabase SQL editor.

alter table public.listening_tests
  add column if not exists part_audio jsonb not null default '{}'::jsonb;

-- A whole-part clip is far larger than a single extract; raise the bucket cap
-- (was 25MB from the original track migration) so a long Part C fits.
update storage.buckets set file_size_limit = 62914560 where id = 'listening-audio';
