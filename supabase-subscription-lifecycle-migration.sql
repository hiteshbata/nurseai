-- ============================================================
-- NurseAI: Subscription Lifecycle — expiry, status, atomic grant.
-- Run this in the Supabase SQL Editor.
--
-- Scope note: this migration adds new columns to public.user_profiles
-- and one new function, grant_subscription_period. It does NOT touch
-- public.payments, public.logs, or the process_payment RPC — those
-- are not in source control (see supabase-fix-rls-policies.sql's
-- comment "Table exists in live DB") and this migration is written
-- to be safe to apply without needing to see or modify them.
--
-- grant_subscription_period is called from Python (see
-- backend/app/routers/payments.py) AFTER process_payment_rpc has
-- already verified and recorded a non-duplicate payment. It is
-- deliberately atomic (SELECT ... FOR UPDATE) so that two distinct
-- legitimate payments for the same user, processed close together,
-- both correctly extend plan_expires_at instead of racing in a
-- read-then-write from the application layer.
-- ============================================================

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
-- set a real plan_expires_at via grant_subscription_period below.
UPDATE public.user_profiles
SET
  subscription_status = 'active',
  plan_expires_at = COALESCE(plan_expires_at, now() + interval '30 days')
WHERE plan <> 'free'
  AND subscription_status = 'none';

-- Supports the admin expiry-sweep endpoint (GET candidates past grace)
-- and is a reasonable index for any future per-user expiry lookups.
CREATE INDEX IF NOT EXISTS idx_user_profiles_plan_expiry
  ON public.user_profiles (plan_expires_at)
  WHERE subscription_status = 'active';

-- ============================================================
-- Atomic subscription-period grant.
--
-- p_previous_plan MUST be captured by the caller BEFORE calling
-- process_payment_rpc, which unconditionally overwrites
-- user_profiles.plan on every successful payment — reading it
-- afterward (as an earlier, now-replaced version of this migration's
-- Python caller did) would always just echo back the new plan being
-- granted, making the same-plan-renewal check a tautology.
--
-- The SELECT ... FOR UPDATE row lock is what closes the lost-update
-- race: a concurrent call for the same user_id blocks here until this
-- transaction commits, then reads the just-committed plan_expires_at
-- — no retries needed, Postgres serializes the two calls for us.
-- ============================================================
CREATE OR REPLACE FUNCTION public.grant_subscription_period(
    p_user_id uuid,
    p_new_plan text,
    p_previous_plan text,
    p_period_days integer,
    p_grace_days integer,
    p_now timestamptz DEFAULT now()
)
RETURNS TABLE(plan_expires_at timestamptz, is_fresh_start boolean)
LANGUAGE plpgsql
AS $function$
DECLARE
    v_current_expires_at timestamptz;
    v_is_renewal boolean;
    v_new_expires_at timestamptz;
BEGIN
    -- Table-qualified: RETURNS TABLE(plan_expires_at, ...) makes
    -- plan_expires_at an implicit OUT-parameter variable in this scope,
    -- which collides with the identically-named column below unless
    -- qualified. An unqualified SELECT here throws AmbiguousColumn on
    -- every call -- see supabase-fix-grant-subscription-period-ambiguous-column.sql.
    SELECT user_profiles.plan_expires_at INTO v_current_expires_at
      FROM public.user_profiles
     WHERE user_id = p_user_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'grant_subscription_period: no user_profiles row for user_id %', p_user_id;
    END IF;

    v_is_renewal := (
        p_previous_plan = p_new_plan
        AND v_current_expires_at IS NOT NULL
        AND p_now <= v_current_expires_at + make_interval(days => p_grace_days)
    );

    IF v_is_renewal THEN
        v_new_expires_at := GREATEST(p_now, v_current_expires_at) + make_interval(days => p_period_days);
    ELSE
        v_new_expires_at := p_now + make_interval(days => p_period_days);
    END IF;

    UPDATE public.user_profiles
       SET plan_expires_at = v_new_expires_at,
           subscription_status = 'active'
     WHERE user_id = p_user_id;

    RETURN QUERY SELECT v_new_expires_at, NOT v_is_renewal;
END;
$function$;
