-- Phase 2: Weakness Graph + Study Hub + Vocab SRS. Apply in Supabase SQL editor.

-- The Weakness Graph: every module (reading/listening part, speaking/writing
-- criterion) writes a 0-6 band observation here under a skill_tag. ema_score
-- is an exponential moving average on the same 0-6 scale everything else
-- already uses, so any module's signal is directly comparable to any other's.
create table if not exists public.user_skill_stats (
  id bigserial primary key,
  user_id uuid not null,
  skill_tag text not null,
  attempts int not null default 0,
  ema_score numeric not null default 0,
  updated_at timestamptz not null default now(),
  unique (user_id, skill_tag)
);

create index if not exists user_skill_stats_user_idx on public.user_skill_stats (user_id);

alter table public.user_skill_stats enable row level security;

-- Vocab SRS deck (SM-2). Auto-filled from dictionary lookups in Reading and
-- Listening (a term someone looks up is, by definition, one they don't know
-- yet); source_module records where a card came from for later analytics.
create table if not exists public.vocab_cards (
  id bigserial primary key,
  user_id uuid not null,
  term text not null,
  definition text not null,
  source_module text,
  ease numeric not null default 2.5,
  interval_days int not null default 0,
  reps int not null default 0,
  due_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (user_id, term)
);

create index if not exists vocab_cards_due_idx on public.vocab_cards (user_id, due_at);

alter table public.vocab_cards enable row level security;

-- The daily plan itself is generated fresh on every GET from the Weakness
-- Graph (nothing to store) -- this table only tracks which of today's
-- suggested tasks the user has already ticked off, so a repeat visit the
-- same day doesn't re-show completed items.
create table if not exists public.daily_goal_completions (
  id bigserial primary key,
  user_id uuid not null,
  goal_date date not null,
  task_key text not null,
  completed_at timestamptz not null default now(),
  unique (user_id, goal_date, task_key)
);

alter table public.daily_goal_completions enable row level security;
