-- ============================================================
-- LB-8: Lock down direct public/anon access to scenarios and questions
-- ============================================================
-- Both tables contain examiner-only fields (interlocutor_card,
-- scoring_criteria, correct_answer) that must never be readable outside
-- the FastAPI backend. The backend connects to Supabase as service_role,
-- which has BYPASSRLS in this project, so none of this affects the app.
--
-- Audit performed before this migration (pg_policies, live prod):
--   - "Anyone can read active scenarios" (scenarios, SELECT, roles=public)
--   - "Anyone can read questions" (questions, SELECT, roles=anon,authenticated)
--   These two policies had no column restriction (RLS is row-level only)
--   and let the public anon key read every column of every row directly
--   via the PostgREST REST API, bypassing FastAPI entirely.
--   All other policies named "Service role can ..." across the schema
--   were already scoped TO service_role only — no changes needed there.
-- ============================================================

BEGIN;

-- 1. Drop the public-read RLS policies.
DROP POLICY IF EXISTS "Anyone can read active scenarios" ON public.scenarios;
DROP POLICY IF EXISTS "Anyone can read questions" ON public.questions;

-- 2. Revoke the blanket anon/authenticated table grants (Supabase's
--    default GRANT ALL ON ALL TABLES) so denial is an explicit
--    "permission denied for table" error at the SQL level, not just
--    an RLS-filtered empty result set.
REVOKE ALL PRIVILEGES ON public.scenarios FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON public.questions FROM anon, authenticated;

-- 3. Explicit service_role-only read policies. service_role already
--    bypasses RLS (BYPASSRLS) so this is defense-in-depth / documents
--    intent, matching the pattern already used for every other table
--    in this schema ("Service role can manage ...").
CREATE POLICY "Service role can read scenarios"
    ON public.scenarios FOR SELECT
    TO service_role
    USING (true);

CREATE POLICY "Service role can read questions"
    ON public.questions FOR SELECT
    TO service_role
    USING (true);

COMMIT;
