-- ============================================================
-- NurseAI: Subscription Lifecycle — expiry, status, grace period
-- Run this in the Supabase SQL Editor.
--
-- Scope note: this migration ONLY adds new columns to
-- public.user_profiles. It does NOT touch public.payments,
-- public.logs, or the process_payment RPC — those are not in
-- source control (see supabase-fix-rls-policies.sql's comment
-- "Table exists in live DB") and this migration is written to be
-- safe to apply without needing to see or modify them.
-- ============================================================

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS plan_started_at TIMESTAMPTZ;

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS plan_expires_at TIMESTAMPTZ;

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'none';

ALTER TABLE public.user_profiles
  DROP CONSTRAINT IF EXISTS user_profiles_subscription_status_check;

ALTER TABLE public.user_profiles
  ADD CONSTRAINT user_profiles_subscription_status_check
  CHECK (subscription_status IN ('none', 'active', 'expired', 'canceled'));

-- One-time backfill: existing paying users get a fresh 30-day period
-- starting now, instead of being retroactively treated as expired the
-- instant this migration runs. All payments from this point forward
-- set a real plan_expires_at via the backend (see grant_subscription_period
-- in backend/app/routers/payments.py).
UPDATE public.user_profiles
SET
  subscription_status = 'active',
  plan_started_at = COALESCE(plan_started_at, now()),
  plan_expires_at = COALESCE(plan_expires_at, now() + interval '30 days')
WHERE plan <> 'free'
  AND subscription_status = 'none';

-- Supports the admin expiry-sweep endpoint (GET candidates past grace)
-- and is a reasonable index for any future per-user expiry lookups.
CREATE INDEX IF NOT EXISTS idx_user_profiles_plan_expiry
  ON public.user_profiles (plan_expires_at)
  WHERE subscription_status = 'active';
