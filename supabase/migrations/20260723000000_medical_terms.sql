-- Global medical-term dictionary cache for the Reading double-click lookup.
-- Keyed by normalized term text (not per-user, not per-passage) so the same
-- term is defined once ever and reused across every passage and every
-- student. Apply in Supabase SQL editor.

create table if not exists public.medical_terms (
  term text primary key,
  definition text not null,
  created_at timestamptz not null default now()
);

-- Service-role only, same posture as every other content table.
alter table public.medical_terms enable row level security;
