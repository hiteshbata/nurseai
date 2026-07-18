-- Per-call AI cost log: every speech-to-text, LLM, text-to-speech, and
-- realtime-voice call writes one row here. This is the only place cost is
-- tracked per call rather than per session -- it's what "cost per session/
-- user/plan" and margin reporting reads from.
-- Apply in Supabase SQL editor.

create table if not exists public.ai_usage_events (
  id bigserial primary key,
  user_id uuid,
  session_id bigint,
  call_type text not null check (call_type in ('stt', 'llm', 'tts', 'realtime')),
  provider text not null,
  model text,
  cost_usd numeric not null,
  is_estimate boolean not null default false,
  detail jsonb,
  created_at timestamptz not null default now()
);

-- user_id is nullable: the realtime pipeline's teardown path only always
-- has session_id reliably in scope (see speaking_realtime.py); user_id is
-- populated there too when available, but reporting can otherwise join
-- through session_usage.user_id via session_id.
create index if not exists ai_usage_events_user_id_idx on public.ai_usage_events (user_id);
create index if not exists ai_usage_events_session_id_idx on public.ai_usage_events (session_id);
create index if not exists ai_usage_events_created_at_idx on public.ai_usage_events (created_at);

-- Admin-only reporting, all access goes through the backend's service-role
-- client. RLS enabled with no policies means anon/authenticated roles get
-- zero access by default; only the service role (which bypasses RLS) can
-- read or write this table.
alter table public.ai_usage_events enable row level security;
