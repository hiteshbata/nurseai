-- Per-user highlights + free-text notes on a reading passage. One row per
-- (user, passage): highlights is a JSON array of {start,end} character
-- offsets into reading_passages.body; note is a single free-text note.
-- Apply in Supabase SQL editor.

create table if not exists public.reading_notes (
  id bigserial primary key,
  user_id uuid not null,
  passage_id bigint not null references public.reading_passages(id) on delete cascade,
  highlights jsonb not null default '[]',
  note text,
  updated_at timestamptz not null default now(),
  unique (user_id, passage_id)
);

create index if not exists reading_notes_user_passage_idx on public.reading_notes (user_id, passage_id);

alter table public.reading_notes enable row level security;
