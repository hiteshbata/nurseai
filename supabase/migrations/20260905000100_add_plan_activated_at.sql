-- ============================================================
-- Fix QA schema drift: user_profiles.plan_activated_at is written by
-- process_payment_and_grant (20260905000000_atomic_payment_grant.sql)
-- and already exists on production, but was never created by a
-- tracked migration -- it was added out-of-band. QA (and any other
-- environment provisioned from the migration history alone) is
-- missing it, which makes process_payment_and_grant fail there.
--
-- Additive, idempotent, non-destructive: safe to run on production
-- (no-op, column already present) and on any environment missing it.
-- ============================================================

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS plan_activated_at TIMESTAMPTZ;
