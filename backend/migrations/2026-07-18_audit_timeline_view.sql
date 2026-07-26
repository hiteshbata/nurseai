-- Fixes admin_get_audit_log (backend/app/routers/admin.py): it merged
-- audit_log + moderation_log + impersonation_log in Python with no
-- offset support at all (the admin panel could only ever see the most
-- recent page, never page back further). Two problems, two fixes:
--
-- 1. moderation_log and impersonation_log had no index on the column the
--    endpoint sorts by (created_at / started_at) -- audit_log already had
--    one (see 2026-07-18_audit_log.sql), these two didn't, so every call
--    was an unindexed full-table sort on those two.
-- 2. Three separate REST round-trips merged/sorted in Python, with no way
--    to express OFFSET across a union of three tables. Replaced with one
--    view the endpoint queries directly with real ORDER BY + LIMIT/OFFSET.
--
-- Apply in Supabase SQL editor.

create index if not exists moderation_log_created_at_idx on public.moderation_log (created_at);
create index if not exists impersonation_log_started_at_idx on public.impersonation_log (started_at);

create or replace view public.admin_audit_timeline as
  select
    created_at,
    admin_email,
    action,
    target_type,
    coalesce(target_label, target_id) as target_label,
    detail
  from public.audit_log
  union all
  select
    created_at,
    admin_email,
    action,
    'user' as target_type,
    target_email as target_label,
    jsonb_build_object('reason', reason, 'expires_at', expires_at) as detail
  from public.moderation_log
  union all
  select
    started_at as created_at,
    admin_email,
    'impersonated' as action,
    'user' as target_type,
    target_email as target_label,
    jsonb_build_object('ended_at', ended_at) as detail
  from public.impersonation_log;

-- No SECURITY DEFINER / RLS policy needed: every reader is the backend's
-- service-role client, which already bypasses RLS on all three
-- underlying tables directly -- the view carries the same access.
