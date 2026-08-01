-- Reading "tests" = one full OET paper (a group of passages across Part A/B/C
-- that a student takes as one continuous session). A passage optionally belongs
-- to one test; ungrouped passages (test_id null) still work as standalone practice.
-- Apply in Supabase SQL editor.

create table if not exists public.reading_tests (
  id bigserial primary key,
  title text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

alter table public.reading_passages
  add column if not exists test_id bigint references public.reading_tests(id) on delete set null;

create index if not exists reading_passages_test_id_idx on public.reading_passages (test_id);

-- Service-role-only access (backend), same pattern as every other content table.
alter table public.reading_tests enable row level security;
