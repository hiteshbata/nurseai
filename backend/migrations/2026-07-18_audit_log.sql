-- General admin action history: role changes, plan changes, content and
-- settings edits. Ban/suspend/delete already have their own richer log
-- (moderation_log), impersonation its own (impersonation_log) -- this
-- table covers everything else an admin can change.
-- Apply in Supabase SQL editor.

create table if not exists public.audit_log (
  id uuid primary key default gen_random_uuid(),
  admin_id uuid not null,
  admin_email text not null,
  action text not null,
  target_type text not null,
  target_id text,
  target_label text,
  detail jsonb,
  created_at timestamptz not null default now()
);

create index if not exists audit_log_target_idx on public.audit_log (target_type, target_id);
create index if not exists audit_log_admin_id_idx on public.audit_log (admin_id);
create index if not exists audit_log_created_at_idx on public.audit_log (created_at);

-- Admin-only feature, all access goes through the backend's service-role
-- client. RLS enabled with no policies means anon/authenticated roles get
-- zero access by default; only the service role (which bypasses RLS) can
-- read or write this table.
alter table public.audit_log enable row level security;
