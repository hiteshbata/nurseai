-- ============================================================
-- NurseAI: Auto-renew subscriptions via Razorpay Subscriptions.
-- Run this in the Supabase SQL Editor.
--
-- Adds the columns needed to track a recurring Razorpay Subscription
-- alongside the existing one-off order flow (payments/process_payment
-- untouched — recurring charges still land in that same table via the
-- subscription.charged webhook, using the existing idempotency
-- guarantee). auto_renew_enabled is purely informational for the UI
-- and cancel flow; it does not gate access — plan_expires_at +
-- subscription_status (from supabase-subscription-lifecycle-migration.sql)
-- remain the sole source of truth for whether a plan is active.
-- ============================================================

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS razorpay_subscription_id TEXT;

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS auto_renew_enabled BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_user_profiles_razorpay_subscription_id
  ON public.user_profiles (razorpay_subscription_id)
  WHERE razorpay_subscription_id IS NOT NULL;
