-- Store each audio clip's cut range so the admin can see the time frame per section
-- and per part intro (display only; playback uses the URL). Set when cutting from a
-- full recording; left null for a directly-uploaded clip. Apply in the Supabase SQL editor.

alter table public.listening_sections
  add column if not exists audio_start double precision,
  add column if not exists audio_end double precision;

-- Per-part intro cut ranges: {"A": {"start": 0, "end": 52}, ...}. Sits alongside
-- listening_tests.part_audio (which holds the URLs).
alter table public.listening_tests
  add column if not exists part_audio_times jsonb not null default '{}'::jsonb;
