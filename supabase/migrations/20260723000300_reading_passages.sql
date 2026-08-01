-- Reading module: one passage holds many MCQs. Questions themselves reuse the
-- existing `questions` table (module='reading', options JSON, correct_answer =
-- exact option text) -- this migration only adds the passage grouping + link.
-- Apply in Supabase SQL editor.

create table if not exists public.reading_passages (
  id bigserial primary key,
  title text not null,
  part text not null default 'C' check (part in ('B', 'C')),
  difficulty text not null default 'intermediate',
  body text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists reading_passages_active_idx on public.reading_passages (is_active);

-- Link each reading MCQ back to its passage so the student page can fetch a
-- passage and all its questions in one group. ON DELETE CASCADE: dropping a
-- passage removes its orphaned questions too.
alter table public.questions
  add column if not exists passage_id bigint references public.reading_passages(id) on delete cascade;

create index if not exists questions_passage_id_idx on public.questions (passage_id);

-- All access goes through the backend's service-role client (which bypasses
-- RLS). Enable RLS with no policies so anon/authenticated get zero direct
-- access, matching every other content table.
alter table public.reading_passages enable row level security;
