-- ============================================================
-- NurseAI Supabase Schema v2 — Run in Supabase SQL Editor
-- ============================================================

-- SCENARIOS TABLE
-- Stores OET role-play scenarios with interlocutor + nurse cards
CREATE TABLE IF NOT EXISTS public.scenarios (
    id BIGSERIAL PRIMARY KEY,
    module TEXT NOT NULL CHECK (module IN ('speaking', 'writing', 'reading', 'listening')),
    title TEXT NOT NULL,
    setting TEXT NOT NULL DEFAULT 'Hospital',
    
    -- Interlocutor card (what the AI patient follows)
    interlocutor_card JSONB NOT NULL DEFAULT '{}',
    
    -- Nurse card (what the student sees)
    nurse_card JSONB NOT NULL DEFAULT '{}',
    
    -- Scoring criteria specific to this scenario
    scoring_criteria JSONB NOT NULL DEFAULT '{}',
    
    is_active BOOLEAN DEFAULT true,
    difficulty TEXT DEFAULT 'intermediate' CHECK (difficulty IN ('beginner', 'easy', 'intermediate', 'medium', 'advanced', 'hard')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.scenarios ENABLE ROW LEVEL SECURITY;

-- Anyone can read active scenarios
CREATE POLICY "Anyone can read active scenarios" 
    ON public.scenarios FOR SELECT 
    USING (is_active = true);

-- Service role can manage scenarios (for seeding)
CREATE POLICY "Service role can manage scenarios" 
    ON public.scenarios FOR ALL 
    USING (true) WITH CHECK (true);


-- SETTINGS TABLE
-- Key-value store for app configuration (AI model, pricing, etc.)
CREATE TABLE IF NOT EXISTS public.settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.settings ENABLE ROW LEVEL SECURITY;

-- Anyone can read settings
CREATE POLICY "Anyone can read settings" 
    ON public.settings FOR SELECT 
    USING (true);

-- Service role can manage settings
CREATE POLICY "Service role can manage settings" 
    ON public.settings FOR ALL 
    USING (true) WITH CHECK (true);

-- Insert default settings (only if not exist)
INSERT INTO public.settings (key, value, description) VALUES
    ('ai_model', 'google/gemini-2.0-flash-001', 'AI model for scoring and patient chat'),
    ('ai_patient_model', 'google/gemini-2.0-flash-001', 'AI model for patient role-play'),
    ('speaking_price_monthly', '499', 'Monthly subscription price in INR'),
    ('free_sessions_count', '3', 'Number of free sessions before paywall')
ON CONFLICT (key) DO NOTHING;


-- USER ROLES TABLE
-- Track which users are admins
CREATE TABLE IF NOT EXISTS public.user_roles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;

-- Users can read their own role
CREATE POLICY "Users can read own role" 
    ON public.user_roles FOR SELECT 
    USING (auth.uid() = user_id);

-- Service role can manage roles
CREATE POLICY "Service role can manage roles" 
    ON public.user_roles FOR ALL 
    USING (true) WITH CHECK (true);


-- INDEXES for performance
CREATE INDEX IF NOT EXISTS idx_scenarios_module ON public.scenarios(module);
CREATE INDEX IF NOT EXISTS idx_scenarios_active ON public.scenarios(is_active);