-- ============================================================
-- Fix: grant_subscription_period() fails on every real call with
-- "column reference plan_expires_at is ambiguous".
-- Run this in the Supabase SQL Editor.
--
-- Root cause: RETURNS TABLE(plan_expires_at timestamptz, ...) creates
-- an implicit OUT-parameter variable named plan_expires_at, which
-- collides with the identically-named column on public.user_profiles
-- in the SELECT ... FOR UPDATE below. Postgres refuses to guess which
-- one is meant, so the function has thrown on every invocation since
-- it was deployed -- discovered via a live concurrency test, not by
-- the pure-Python contract tests (which never execute the real SQL).
--
-- Fix: table-qualify the column reference. No other behavior, no
-- change to the function's name, parameters, or return shape, so no
-- Python caller changes are needed.
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
