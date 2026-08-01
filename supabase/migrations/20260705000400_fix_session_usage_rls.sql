-- ============================================================
-- Fix: "Users can read own session usage" RLS policy on
-- public.session_usage has no TO clause, defaulting to PUBLIC
-- (anon + authenticated) instead of TO authenticated.
-- Run this in the Supabase SQL Editor.
--
-- Not an active data leak today: the USING clause (auth.uid() = user_id)
-- still means an anon request matches zero rows, since auth.uid() is
-- null for anon. This is the same class of missing-TO-clause mistake
-- already fixed everywhere else in supabase-fix-rls-policies.sql --
-- this table was missed. Pinning it to TO authenticated for
-- consistency and to close the gap outright rather than rely on the
-- USING clause alone.
-- ============================================================

DROP POLICY IF EXISTS "Users can read own session usage" ON public.session_usage;
CREATE POLICY "Users can read own session usage"
  ON public.session_usage FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);
