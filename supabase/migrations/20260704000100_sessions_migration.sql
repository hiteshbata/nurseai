-- ============================================================
-- NurseAI Session Counting Migration
-- Run this in Supabase SQL Editor
-- ============================================================

-- Add session columns to user_profiles
ALTER TABLE public.user_profiles 
  ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'free';

ALTER TABLE public.user_profiles 
  ADD COLUMN IF NOT EXISTS sessions_used_this_month INT4 DEFAULT 0;

ALTER TABLE public.user_profiles 
  ADD COLUMN IF NOT EXISTS sessions_reset_date TIMESTAMPTZ DEFAULT now();

-- Create session_usage log table
CREATE TABLE IF NOT EXISTS public.session_usage (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) NOT NULL,
  session_type TEXT NOT NULL DEFAULT 'speaking',
  tokens_used INT4 DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.session_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own session usage"
  ON public.session_usage FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage session usage"
  ON public.session_usage FOR ALL
  USING (true)
  WITH CHECK (true);
