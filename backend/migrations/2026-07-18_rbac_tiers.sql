-- Widens public.user_roles.role from a binary user/admin flag to an
-- ordered staff ladder: user < support < analyst < admin < owner.
-- Backend enforcement lives in backend/app/routers/admin.py (ROLE_RANK,
-- require_role) -- this migration only needs to stop the DB from
-- rejecting the new values. No existing row changes: every current
-- 'user'/'admin' row is still valid under the new constraint.
-- Apply in Supabase SQL editor.

alter table public.user_roles
  drop constraint if exists user_roles_role_check;

alter table public.user_roles
  add constraint user_roles_role_check
  check (role in ('user', 'support', 'analyst', 'admin', 'owner'));
