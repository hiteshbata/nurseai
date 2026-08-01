-- Supabase advisor fixes, 2026-07-13 audit. Apply in Supabase SQL editor.

-- 1. Lock down event-trigger helper (was executable by anon/authenticated)
revoke execute on function public.rls_auto_enable() from public, anon, authenticated;

-- 2. Pin search_path on payment functions
alter function public.process_payment(uuid, text, text, text, bigint, text, text, text, timestamptz)
  set search_path = public, pg_catalog;
alter function public.grant_subscription_period(uuid, text, text, integer, integer, timestamptz)
  set search_path = public, pg_catalog;

-- 3. RLS initplan: evaluate auth.uid() once per query, not per row
alter policy "Users can read own payments" on public.payments
  using ((select auth.uid()) = user_id);
alter policy "Users can read own session usage" on public.session_usage
  using ((select auth.uid()) = user_id);
alter policy "Users can read own submissions" on public.submissions
  using ((select auth.uid()) = user_id);
alter policy "Users can insert own submissions" on public.submissions
  with check ((select auth.uid()) = user_id);
alter policy "Users can read own profile" on public.user_profiles
  using ((select auth.uid()) = user_id);
alter policy "Users can insert own profile" on public.user_profiles
  with check ((select auth.uid()) = user_id);
alter policy "Users can update own profile" on public.user_profiles
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
alter policy "Users can read own role" on public.user_roles
  using ((select auth.uid()) = user_id);
alter policy "Users can read own realtime session metrics" on public.realtime_session_metrics
  using (exists (
    select 1 from public.session_usage su
    where su.id = realtime_session_metrics.session_usage_id
      and su.user_id = (select auth.uid())
  ));

-- 4. Covering indexes for foreign keys
create index if not exists idx_payments_user_id on public.payments (user_id);
create index if not exists idx_session_usage_user_id on public.session_usage (user_id);
create index if not exists idx_submissions_question_id on public.submissions (question_id);
