-- Mirrors id/email/name out of Supabase Auth into a queryable table.
-- Fixes the hard scaling blocker in admin_search_users and
-- _emails_by_user_id (backend/app/routers/admin.py): both used to call
-- auth.admin.list_users(per_page=1000) and filter/sort/paginate in
-- Python, which silently drops results past 1000 total users and pulls
-- the whole list over the network on every request regardless of page
-- size or search term.
--
-- Kept in sync two ways:
--   1. Lazily, on every authenticated request (see get_current_user in
--      auth.py) -- same cache-gated upsert already used for user_roles,
--      extended to also refresh this table. Self-healing for anyone who
--      logs in after this migration runs.
--   2. POST /admin/users/backfill-mirror -- one-time backfill for
--      existing users (who won't get an upsert until their next login)
--      and periodic drift correction (an email changed but the user
--      hasn't made an authenticated request since). Safe to re-run.
-- Apply in Supabase SQL editor.

create table if not exists public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  name text,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz,
  synced_at timestamptz not null default now()
);

-- lower() so search (ILIKE) and exact lookups are case-insensitive and
-- can still use the index for equality/prefix matches. A full '%needle%'
-- contains-search still sequential-scans -- fine at the scale this fixes
-- for; add pg_trgm if search latency ever actually shows up as a problem.
create index if not exists users_email_idx on public.users (lower(email));
create index if not exists users_created_at_idx on public.users (created_at);

-- Admin-only, service-role client only, same convention as audit_log /
-- moderation_log / impersonation_log: RLS enabled, no policies.
alter table public.users enable row level security;
