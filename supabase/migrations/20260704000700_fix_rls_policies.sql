-- ============================================================
-- NurseAI: Fix RLS Policies — add missing TO role clauses
-- Apply to staging first, then production after verification.
-- ============================================================

-- ============================================================
-- 1. Fix existing "Service role" policies — add TO service_role
--    These were created without a TO clause, defaulting to
--    TO PUBLIC (anon + authenticated). Any user could bypass
--    user-scoped restrictions on these tables.
-- ============================================================

-- 1a. questions: "Service role can insert questions"
DROP POLICY IF EXISTS "Service role can insert questions" ON public.questions;
CREATE POLICY "Service role can insert questions"
    ON public.questions FOR INSERT
    TO service_role
    WITH CHECK (true);

-- 1b. submissions: "Service role can manage submissions"
DROP POLICY IF EXISTS "Service role can manage submissions" ON public.submissions;
CREATE POLICY "Service role can manage submissions"
    ON public.submissions FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 1c. scenarios: "Service role can manage scenarios"
DROP POLICY IF EXISTS "Service role can manage scenarios" ON public.scenarios;
CREATE POLICY "Service role can manage scenarios"
    ON public.scenarios FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 1d. settings: "Service role can manage settings"
DROP POLICY IF EXISTS "Service role can manage settings" ON public.settings;
CREATE POLICY "Service role can manage settings"
    ON public.settings FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 1e. user_roles: "Service role can manage roles"
DROP POLICY IF EXISTS "Service role can manage roles" ON public.user_roles;
CREATE POLICY "Service role can manage roles"
    ON public.user_roles FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 1f. user_profiles: "Service role can manage profiles"
DROP POLICY IF EXISTS "Service role can manage profiles" ON public.user_profiles;
CREATE POLICY "Service role can manage profiles"
    ON public.user_profiles FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 1g. session_usage: "Service role can manage session usage"
DROP POLICY IF EXISTS "Service role can manage session usage" ON public.session_usage;
CREATE POLICY "Service role can manage session usage"
    ON public.session_usage FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);


-- ============================================================
-- 2. payments table — add RLS policies
--    Table exists in live DB with RLS ON but zero policies
--    (all access blocked, including service_role).
-- ============================================================

ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;

-- Users can read their own payment records
CREATE POLICY "Users can read own payments"
    ON public.payments FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- Service role can manage all payments (backend webhooks + admin)
CREATE POLICY "Service role can manage payments"
    ON public.payments FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);


-- ============================================================
-- 3. logs table — add RLS policy
--    Internal/operational logging table. Admin-only reads via
--    backend service_role. AI scoring writes errors via
--    service_role. No end-user should access this table.
-- ============================================================

ALTER TABLE public.logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role can manage logs"
    ON public.logs FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);


-- ============================================================
-- 4. Public-read policies — make TO clause explicit
--    Previously relied on the default (TO PUBLIC). Explicit
--    TO anon, authenticated keeps the same behaviour while
--    making the intent clear and auditable.
-- ============================================================

DROP POLICY IF EXISTS "Anyone can read questions" ON public.questions;
CREATE POLICY "Anyone can read questions"
    ON public.questions FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS "Anyone can read settings" ON public.settings;
CREATE POLICY "Anyone can read settings"
    ON public.settings FOR SELECT
    TO anon, authenticated
    USING (true);
