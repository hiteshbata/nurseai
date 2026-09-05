-- ============================================================
-- SpeakOET billing audit fix (Issue 2): atomic payment + entitlement
-- grant.
--
-- Problem: backend/app/routers/payments.py used to call process_payment
-- (records the payment row + sets user_profiles.plan) and then, as a
-- SEPARATE PostgREST round trip, grant_subscription_period (extends
-- plan_expires_at). Two independent RPC calls are two independent
-- Postgres transactions. If the first committed and the second then
-- failed, the payment stayed permanently recorded -- and because
-- process_payment's own idempotency check (payments.payment_id UNIQUE)
-- is what a retry looks at, every retry (client re-verify or a webhook
-- redelivery) would see "already_processed" and skip the grant call
-- forever. Net effect: a customer paid, but plan_expires_at was never
-- extended, with no automatic recovery path.
--
-- Fix: process_payment_and_grant wraps both steps in ONE plpgsql
-- function, so PostgREST executes them as ONE Postgres transaction.
-- The call to grant_subscription_period below is a plain nested
-- function call (not a second network round trip), so if it raises,
-- the whole transaction -- including the payment INSERT and the
-- user_profiles.plan UPDATE above it -- rolls back automatically. A
-- retry then sees no existing payment row and safely redoes the whole
-- operation, instead of short-circuiting on a half-applied payment.
--
-- Mirrors process_payment (see supabase-payments-schema-reference.sql)
-- for the payment-recording half, and calls the existing
-- grant_subscription_period (20260704000200_subscription_lifecycle_
-- migration.sql) unchanged for the entitlement half -- that function's
-- own SELECT ... FOR UPDATE row lock still applies correctly nested
-- inside this transaction.
--
-- Does NOT replace process_payment or grant_subscription_period --
-- admin.py's manual comp-plan endpoint (POST /admin/users/{id}/plan)
-- still calls grant_subscription_period directly, and is unaffected.
-- ============================================================

CREATE OR REPLACE FUNCTION public.process_payment_and_grant(
    p_user_id uuid,
    p_order_id text,
    p_payment_id text,
    p_plan_id text,
    p_amount bigint,
    p_profile_plan text,
    p_previous_plan text,
    p_period_days integer,
    p_grace_days integer,
    p_currency text DEFAULT 'INR',
    p_status text DEFAULT 'paid',
    p_verified_at timestamptz DEFAULT now()
)
RETURNS text
LANGUAGE plpgsql
AS $function$
DECLARE
    inserted_rows INT;
    updated_rows INT;
BEGIN
    INSERT INTO payments (user_id, order_id, payment_id, plan_id, amount, currency, status, verified_at)
    VALUES (p_user_id, p_order_id, p_payment_id, p_plan_id, p_amount, p_currency, p_status, p_verified_at)
    ON CONFLICT (payment_id) DO NOTHING;

    GET DIAGNOSTICS inserted_rows = ROW_COUNT;

    IF inserted_rows = 0 THEN
        RETURN 'already_processed';
    END IF;

    UPDATE user_profiles
    SET plan = p_profile_plan, plan_activated_at = p_verified_at
    WHERE user_id = p_user_id;

    GET DIAGNOSTICS updated_rows = ROW_COUNT;

    IF updated_rows = 0 THEN
        RAISE EXCEPTION 'process_payment_and_grant: user_profiles update affected 0 rows for user_id %', p_user_id;
    END IF;

    -- Nested call, same transaction as the INSERT/UPDATE above (not a
    -- separate PostgREST round trip) -- an exception here rolls back
    -- everything in this function, payment row included.
    PERFORM public.grant_subscription_period(
        p_user_id, p_profile_plan, p_previous_plan, p_period_days, p_grace_days, p_verified_at
    );

    RETURN 'ok';
END;
$function$;
