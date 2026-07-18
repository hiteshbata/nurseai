-- Log of admin "log in as user" (impersonation) sessions.
-- Apply in Supabase SQL editor.

create table if not exists public.impersonation_log (
  id uuid primary key default gen_random_uuid(),
  admin_id uuid not null,
  admin_email text not null,
  target_user_id uuid not null,
  target_email text not null,
  started_at timestamptz not null default now(),
  ended_at timestamptz
);

create index if not exists impersonation_log_target_user_id_idx on public.impersonation_log (target_user_id);
create index if not exists impersonation_log_admin_id_idx on public.impersonation_log (admin_id);

-- Admin-only feature, all access goes through the backend's service-role
-- client. RLS enabled with no policies means anon/authenticated roles get
-- zero access by default; only the service role (which bypasses RLS) can
-- read or write this table.
alter table public.impersonation_log enable row level security;
