-- ============================================================
-- Reference snapshot of public.logs.
-- This is NOT a migration to run -- it documents what is
-- ALREADY LIVE in production, captured via read-only inspection,
-- so this table stops being an unverifiable blind spot in the repo.
--
-- Verified live: RLS is enabled with a single service_role-only
-- policy (USING true / WITH CHECK true) and no policy grants
-- authenticated/anon access -- with RLS enabled and no matching
-- policy, those roles get zero rows by default. This matches how
-- backend/app/routers/admin.py reads it (via the service-role
-- client only). No changes needed; this is a correct default-deny
-- setup, just previously undocumented.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "timestamp" timestamptz DEFAULT now(),
    user_id text DEFAULT '',
    function_name text DEFAULT '',
    error_type text DEFAULT '',
    error_message text DEFAULT '',
    resolved boolean DEFAULT false
);

ALTER TABLE public.logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role can manage logs"
    ON public.logs FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
