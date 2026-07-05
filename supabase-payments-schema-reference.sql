-- ============================================================
-- Reference snapshot of public.payments and process_payment().
-- This is NOT a migration to run -- it documents what is
-- ALREADY LIVE in production, captured via read-only inspection,
-- so the payment idempotency guarantee can be reviewed from
-- source control instead of being an unverifiable blind spot.
--
-- If you ever need to recreate this table from scratch, this is
-- the real definition -- not a guess.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.payments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES auth.users(id),
    order_id text NOT NULL,
    payment_id text NOT NULL,
    plan_id text NOT NULL DEFAULT 'pro_monthly',
    amount bigint NOT NULL,
    currency text NOT NULL DEFAULT 'INR',
    status text NOT NULL DEFAULT 'paid',
    verified_at timestamptz,
    created_at timestamptz DEFAULT now(),
    CONSTRAINT payments_payment_id_key UNIQUE (payment_id)
);

ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own payments"
    ON public.payments FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage payments"
    ON public.payments FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Atomic idempotent payment recording. The UNIQUE(payment_id)
-- constraint above + ON CONFLICT DO NOTHING is what makes a
-- concurrent verify_payment/webhook race for the same payment_id
-- safe: only one caller's INSERT actually lands, the other sees
-- inserted_rows = 0 and returns 'already_processed' without
-- touching user_profiles a second time.
CREATE OR REPLACE FUNCTION public.process_payment(
    p_user_id uuid,
    p_order_id text,
    p_payment_id text,
    p_plan_id text,
    p_amount bigint,
    p_profile_plan text,
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
        RAISE EXCEPTION 'process_payment: user_profiles update affected 0 rows for user_id %', p_user_id;
    END IF;

    RETURN 'ok';
END;
$function$;
