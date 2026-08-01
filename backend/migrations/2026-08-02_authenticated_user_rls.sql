-- ============================================================
-- Authenticated-role RLS hardening. Apply in Supabase SQL editor.
-- Two independent fixes -- read both sections before running.
-- ============================================================


-- ============================================================
-- PART 1 (URGENT): close a live privilege-escalation hole on
-- user_profiles.
--
-- "Users can update own profile" and "Users can insert own profile"
-- (supabase-schema-v3.sql) are row-scoped (auth.uid() = user_id) but
-- have NO column restriction. Supabase's default GRANT ALL ON ALL
-- TABLES TO authenticated was never revoked for this table (LB-8 only
-- revoked it on scenarios/questions). Since SUPABASE_URL and the anon
-- key are necessarily public in the frontend bundle, and every logged
-- -in user already holds their own valid access token, ANY authenticated
-- user can right now PATCH their own user_profiles row directly via the
-- PostgREST REST API -- no FastAPI bug required -- and set:
--   plan='elite', subscription_status='active', plan_expires_at=<future>,
--   sessions_used_this_month=0, bonus_sessions=999999,
--   auto_renew_enabled=true
-- i.e. grant themselves free premium access and unlimited sessions,
-- bypassing Razorpay entirely. This is independent of anything the
-- backend's Python client does -- fix it here regardless of whether
-- the rest of this migration (Part 2) is applied.
--
-- Column-level GRANT is orthogonal to RLS: RLS still gates which ROW,
-- this restricts which COLUMNS authenticated may write on that row.
-- service_role bypasses both RLS and column grants, so no backend code
-- path is affected.
-- ============================================================

REVOKE UPDATE, INSERT ON public.user_profiles FROM authenticated;

GRANT INSERT (
    user_id, onboarding_completed, exam_date, target_band,
    baseline_score, has_taken_oet, previous_band, destination_country,
    days_per_week, state, qualification, years_of_experience,
    nursing_specialty, created_at, updated_at
) ON public.user_profiles TO authenticated;

GRANT UPDATE (
    onboarding_completed, exam_date, target_band,
    baseline_score, has_taken_oet, previous_band, destination_country,
    days_per_week, state, qualification, years_of_experience,
    nursing_specialty, updated_at
) ON public.user_profiles TO authenticated;

-- Deliberately NOT granted to authenticated (service_role-write-only):
-- plan, plan_expires_at, sessions_used_this_month, sessions_reset_date,
-- subscription_status, auto_renew_enabled, bonus_sessions,
-- razorpay_subscription_id.


-- ============================================================
-- PART 2: new authenticated policies for tables that had RLS enabled
-- but zero policies (previously: nobody but service_role could touch
-- them at all, including the app's own user-scoped requests -- these
-- were simply never queried by anything but the service_role client).
-- Needed for get_user_scoped_client() (backend/app/core/supabase.py)
-- to work against them. No column-sensitivity concerns here -- every
-- column on these four tables is student-owned data, not an
-- entitlement.
-- ============================================================

CREATE POLICY "Users can manage own reading notes"
    ON public.reading_notes FOR ALL
    TO authenticated
    USING ((select auth.uid()) = user_id)
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can manage own skill stats"
    ON public.user_skill_stats FOR SELECT
    TO authenticated
    USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can manage own vocab cards"
    ON public.vocab_cards FOR ALL
    TO authenticated
    USING ((select auth.uid()) = user_id)
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can manage own goal completions"
    ON public.daily_goal_completions FOR ALL
    TO authenticated
    USING ((select auth.uid()) = user_id)
    WITH CHECK ((select auth.uid()) = user_id);
