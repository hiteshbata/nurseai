-- ============================================================
-- Cleanup: drop stray plan_started_at column.
-- Run this in the Supabase SQL Editor.
--
-- An earlier, superseded draft of the subscription-lifecycle migration
-- added plan_started_at to public.user_profiles. The final migration
-- (supabase-subscription-lifecycle-migration.sql) does not use it --
-- plan_expires_at + subscription_status fully cover the lifecycle, so
-- this is dead schema left over from whichever draft actually got run.
-- No application code reads or writes plan_started_at.
-- ============================================================

ALTER TABLE public.user_profiles
  DROP COLUMN IF EXISTS plan_started_at;
