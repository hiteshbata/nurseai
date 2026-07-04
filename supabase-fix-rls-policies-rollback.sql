-- ============================================================
-- NurseAI: Rollback RLS Policy Fix
-- Reverses supabase-fix-rls-policies.sql — restores original
-- policies without any TO clause (defaulting to TO PUBLIC).
-- Run ONLY if the forward migration causes issues.
-- ============================================================

-- ============================================================
-- 1. Restore "Service role" policies WITHOUT TO clause
--    (defaults to PUBLIC — matches pre-migration state)
-- ============================================================

-- 1a. questions: "Service role can insert questions"
DROP POLICY IF EXISTS "Service role can insert questions" ON public.questions;
CREATE POLICY "Service role can insert questions"
    ON public.questions FOR INSERT
    WITH CHECK (true);

-- 1b. submissions: "Service role can manage submissions"
DROP POLICY IF EXISTS "Service role can manage submissions" ON public.submissions;
CREATE POLICY "Service role can manage submissions"
    ON public.submissions FOR ALL
    USING (true)
    WITH CHECK (true);

-- 1c. scenarios: "Service role can manage scenarios"
DROP POLICY IF EXISTS "Service role can manage scenarios" ON public.scenarios;
CREATE POLICY "Service role can manage scenarios"
    ON public.scenarios FOR ALL
    USING (true)
    WITH CHECK (true);

-- 1d. settings: "Service role can manage settings"
DROP POLICY IF EXISTS "Service role can manage settings" ON public.settings;
CREATE POLICY "Service role can manage settings"
    ON public.settings FOR ALL
    USING (true)
    WITH CHECK (true);

-- 1e. user_roles: "Service role can manage roles"
DROP POLICY IF EXISTS "Service role can manage roles" ON public.user_roles;
CREATE POLICY "Service role can manage roles"
    ON public.user_roles FOR ALL
    USING (true)
    WITH CHECK (true);

-- 1f. user_profiles: "Service role can manage profiles"
DROP POLICY IF EXISTS "Service role can manage profiles" ON public.user_profiles;
CREATE POLICY "Service role can manage profiles"
    ON public.user_profiles FOR ALL
    USING (true)
    WITH CHECK (true);

-- 1g. session_usage: "Service role can manage session usage"
DROP POLICY IF EXISTS "Service role can manage session usage" ON public.session_usage;
CREATE POLICY "Service role can manage session usage"
    ON public.session_usage FOR ALL
    USING (true)
    WITH CHECK (true);


-- ============================================================
-- 2. Remove payments table policies (pre-migration had none)
-- ============================================================

DROP POLICY IF EXISTS "Users can read own payments" ON public.payments;
DROP POLICY IF EXISTS "Service role can manage payments" ON public.payments;


-- ============================================================
-- 3. Remove logs table policy (pre-migration had none)
-- ============================================================

DROP POLICY IF EXISTS "Service role can manage logs" ON public.logs;


-- ============================================================
-- 4. Restore public-read policies WITHOUT TO clause
-- ============================================================

DROP POLICY IF EXISTS "Anyone can read questions" ON public.questions;
CREATE POLICY "Anyone can read questions"
    ON public.questions FOR SELECT
    USING (true);

DROP POLICY IF EXISTS "Anyone can read settings" ON public.settings;
CREATE POLICY "Anyone can read settings"
    ON public.settings FOR SELECT
    USING (true);
