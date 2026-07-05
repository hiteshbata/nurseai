-- ============================================================
-- Add missing columns for the Razorpay Subscriptions (auto-renew)
-- feature: /payments/create-subscription, /verify-subscription-payment,
-- /cancel-subscription (backend/app/routers/payments.py) and
-- /sessions/usage, /sessions/check-and-increment (backend/app/routers/
-- sessions.py) all reference these on public.user_profiles, but they
-- were never migrated -- every session-quota check has been failing
-- in production with "column user_profiles.auto_renew_enabled does
-- not exist" until this runs.
--
-- Purely additive, nullable/defaulted -- safe for existing rows.
-- ============================================================

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS razorpay_subscription_id TEXT;

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS auto_renew_enabled BOOLEAN NOT NULL DEFAULT false;
