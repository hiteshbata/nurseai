-- Listening module. Mirrors Reading exactly: a "test" = one full OET Listening
-- paper (Part A -> B -> C) taken as one session; a "section" = one extract within
-- it (Reading's passage analog). Questions themselves reuse the existing `questions`
-- table (module='listening', options JSON, correct_answer = exact option text for
-- Part B/C MCQ; type='short_answer' for Part A gap-fill notes) -- so all grading is
-- the shared grade_exact_match / grade_open_ended_answers path, nothing new.
-- This migration adds only the two grouping tables, the question link, and the
-- audio bucket. Apply in the Supabase SQL editor.

-- A test = one full paper grouping many sections. Draft by default (is_active=false)
-- so a half-built paper stays hidden until its sections + audio are ready.
create table if not exists public.listening_tests (
  id bigserial primary key,
  title text not null,
  is_active boolean not null default false,
  created_at timestamptz not null default now()
);

-- A section = one extract (Part A consult, Part B short extract, Part C interview).
-- audio_url is filled either by admin upload OR by TTS generation -- same column
-- both ways (hybrid). transcript holds the 2-speaker turns
-- ([{"speaker": "...", "text": "..."}]) used to GENERATE the TTS audio, and doubles
-- as the optional post-test transcript reveal. Both nullable: a section can be saved
-- (questions attached) before its audio exists yet. Standalone practice allowed with
-- test_id null, same as ungrouped reading passages.
create table if not exists public.listening_sections (
  id bigserial primary key,
  test_id bigint references public.listening_tests(id) on delete set null,
  title text not null,
  part text not null check (part in ('A', 'B', 'C')),
  difficulty text not null default 'intermediate',
  audio_url text,
  transcript jsonb,
  body text,  -- Part A note-completion template (headings + context bullets + numbered blanks); null for B/C
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

-- Defensive for DBs created before `body` existed (the create above is a no-op there).
alter table public.listening_sections add column if not exists body text;

create index if not exists listening_sections_test_id_idx on public.listening_sections (test_id);
create index if not exists listening_sections_active_idx on public.listening_sections (is_active);

-- Link each listening question to its section. Separate from Reading's passage_id
-- (that FK points at reading_passages) -- a listening question belongs to a
-- listening_section. ON DELETE CASCADE: dropping a section removes its questions.
alter table public.questions
  add column if not exists section_id bigint references public.listening_sections(id) on delete cascade;

create index if not exists questions_section_id_idx on public.questions (section_id);

-- Public bucket for extract audio (mp3). Public so a plain <audio src> works with
-- no expiring signed URLs to manage; the backend uploads with the service-role key,
-- which bypasses storage RLS. "Plays once" is a player-side rule (lock replay/seek),
-- not a storage concern -- the file itself is just a normal public object.
insert into storage.buckets (id, name, public)
values ('listening-audio', 'listening-audio', true)
on conflict (id) do nothing;

-- Service-role-only access (backend bypasses RLS). Enable RLS with no policies so
-- anon/authenticated get zero direct table access, matching every other content table.
alter table public.listening_tests enable row level security;
alter table public.listening_sections enable row level security;
