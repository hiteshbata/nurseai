-- Step 13: persisted Semantic Verification State (app.services.patient_state.
-- SemanticHints), so hidden-information verification survives realtime
-- disconnect/reconnect, session completion, and admin inspection without
-- re-running (paid) semantic checks. One authoritative row per speaking
-- session -- session_usage_id is both PK and the UPSERT conflict target, so
-- retries/reconnects never create duplicates.
--
-- RLS enabled with NO policies (same posture as session_transcripts /
-- impersonation_log): only the backend's service-role client can read or
-- write this table. Required because semantic_state can reveal whether a
-- scenario's hidden information was disclosed -- a student must never be
-- able to query that during an active exam.
create table if not exists public.session_semantic_state (
  session_usage_id bigint primary key references public.session_usage(id) on delete cascade,
  user_id uuid not null references auth.users(id),
  purpose text not null default 'speaking_semantic_evidence',
  state_version int not null default 1,
  semantic_state jsonb not null,
  updated_at timestamptz not null default now()
);

create index if not exists session_semantic_state_user_id_idx on public.session_semantic_state (user_id);

alter table public.session_semantic_state enable row level security;
