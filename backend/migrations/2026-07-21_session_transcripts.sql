-- Full conversation transcripts for OpenAI/Gemini realtime voice sessions,
-- captured for account safety review (background-check use, admin/owner
-- only -- see privacy policy 2026-07-21 update disclosing 90-day retention).
-- One row per session, turns stored as an ordered jsonb array
-- ([{role, text}, ...]). Apply in Supabase SQL editor.

create table if not exists public.session_transcripts (
  id bigint generated always as identity primary key,
  session_usage_id bigint not null references public.session_usage(id),
  user_id uuid not null references auth.users(id),
  scenario_id bigint references public.scenarios(id),
  transcript jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists session_transcripts_session_usage_id_idx on public.session_transcripts (session_usage_id);
create index if not exists session_transcripts_user_id_idx on public.session_transcripts (user_id);
create index if not exists session_transcripts_created_at_idx on public.session_transcripts (created_at);

-- Admin-only feature, all access goes through the backend's service-role
-- client. RLS enabled with no policies means anon/authenticated roles get
-- zero access by default; only the service role (which bypasses RLS) can
-- read or write this table. Matches audit_log.
alter table public.session_transcripts enable row level security;
