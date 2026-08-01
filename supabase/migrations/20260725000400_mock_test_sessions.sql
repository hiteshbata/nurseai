-- Full Mock Test (phase 1: Listening -> Reading -> Writing).
-- One row = one student's mock sitting. The mock chains the existing per-module
-- test sessions; it does NOT store answers/grades itself (each module still owns
-- its own submission row). We keep only: which content was picked, when each
-- section started (for the strict deadline), a per-section result summary, and
-- the overall status. Scores stay hidden until status='complete' (after the
-- Speaking mock, phase 2) -- matching real OET, where results come later.

create table if not exists mock_test_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  -- Frozen picks for this attempt (auto-assembled at start). SET NULL on content
  -- delete so removing a test/scenario never destroys a student's mock history.
  listening_test_id bigint references listening_tests(id) on delete set null,
  reading_test_id bigint references reading_tests(id) on delete set null,
  writing_scenario_id bigint references scenarios(id) on delete set null,
  -- 'listening' | 'reading' | 'writing' | null (LRW answering phase finished).
  current_section text,
  -- {section: iso8601} -- stamped when a section is first opened, so the strict
  -- countdown is anchored server-side (a refresh can't reset the clock).
  section_started_at jsonb not null default '{}'::jsonb,
  -- {section: result summary} -- captured per section, revealed only once the
  -- whole mock is complete.
  results jsonb not null default '{}'::jsonb,
  -- 'in_progress' -> 'awaiting_speaking' (LRW done, Speaking pending) -> 'complete'.
  status text not null default 'in_progress',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists mock_test_sessions_user_idx
  on mock_test_sessions (user_id, created_at desc);

-- Backend talks to this table only via the service-role key (bypasses RLS).
-- Enable RLS with no policies so the anon/authenticated keys can never read one
-- student's mock session from another's browser -- all access goes through the API.
alter table mock_test_sessions enable row level security;
