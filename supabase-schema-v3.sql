-- ============================================================
-- NurseAI Supabase Schema v3 — Run in Supabase SQL Editor
-- Creates the missing user_profiles table
-- ============================================================

CREATE TABLE IF NOT EXISTS public.user_profiles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    onboarding_completed BOOLEAN DEFAULT FALSE,
    exam_date TIMESTAMPTZ,
    target_band FLOAT,
    baseline_score FLOAT,
    has_taken_oet BOOLEAN DEFAULT FALSE,
    previous_band FLOAT,
    destination_country TEXT,
    days_per_week INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

-- Users can read their own profile
CREATE POLICY "Users can read own profile"
    ON public.user_profiles FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own profile
CREATE POLICY "Users can insert own profile"
    ON public.user_profiles FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own profile
CREATE POLICY "Users can update own profile"
    ON public.user_profiles FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Service role can manage all profiles
CREATE POLICY "Service role can manage profiles"
    ON public.user_profiles FOR ALL
    USING (true)
    WITH CHECK (true);
