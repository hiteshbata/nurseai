-- Log of admin suspend/ban/reinstate/delete actions on user accounts.
-- Apply in Supabase SQL editor.

create table if not exists public.moderation_log (
  id uuid primary key default gen_random_uuid(),
  admin_id uuid not null,
  admin_email text not null,
  target_user_id uuid not null,
  target_email text not null,
  action text not null check (action in ('suspend', 'ban', 'reinstate', 'delete')),
  reason text not null,
  expires_at timestamptz,
  created_at timestamptz not null default now()
);

-- target_user_id is deliberately NOT a foreign key to auth.users: a 'delete'
-- row must remain readable as a historical record after the account it
-- refers to is gone.
create index if not exists moderation_log_target_user_id_idx on public.moderation_log (target_user_id);
create index if not exists moderation_log_admin_id_idx on public.moderation_log (admin_id);

-- Admin-only feature, all access goes through the backend's service-role
-- client. RLS enabled with no policies means anon/authenticated roles get
-- zero access by default; only the service role (which bypasses RLS) can
-- read or write this table.
alter table public.moderation_log enable row level security;
