-- ============================================================
-- NurseAI Supabase Schema
-- Run this in your Supabase SQL Editor (https://supabase.com)
-- ============================================================

-- 1. QUESTIONS TABLE
-- Stores OET practice questions across all 4 modules
CREATE TABLE IF NOT EXISTS public.questions (
    id BIGSERIAL PRIMARY KEY,
    module TEXT NOT NULL CHECK (module IN ('speaking', 'writing', 'reading', 'listening')),
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    options TEXT,  -- JSON string of multiple choice options
    correct_answer TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE public.questions ENABLE ROW LEVEL SECURITY;

-- Allow all authenticated users to read questions
CREATE POLICY "Anyone can read questions"
    ON public.questions
    FOR SELECT
    USING (true);

-- Allow service role to insert questions (for seeding)
CREATE POLICY "Service role can insert questions"
    ON public.questions
    FOR INSERT
    WITH CHECK (true);

-- 2. SUBMISSIONS TABLE
-- Stores user practice submissions across all modules
CREATE TABLE IF NOT EXISTS public.submissions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    question_id BIGINT REFERENCES public.questions(id) ON DELETE SET NULL,
    module TEXT NOT NULL CHECK (module IN ('speaking', 'writing', 'reading', 'listening', 'test')),
    answer TEXT,  -- transcription or written response
    score FLOAT DEFAULT 0,
    feedback TEXT,  -- JSON string of AI feedback
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE public.submissions ENABLE ROW LEVEL SECURITY;

-- Users can read their own submissions
CREATE POLICY "Users can read own submissions"
    ON public.submissions
    FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own submissions
CREATE POLICY "Users can insert own submissions"
    ON public.submissions
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Service role can read/insert any submission
CREATE POLICY "Service role can manage submissions"
    ON public.submissions
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- 3. INDEXES
CREATE INDEX IF NOT EXISTS idx_submissions_user_id ON public.submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_submissions_module ON public.submissions(module);
CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON public.submissions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_questions_module ON public.questions(module);