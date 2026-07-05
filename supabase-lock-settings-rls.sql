-- ============================================================
-- Fix: public.settings is readable by anyone with just the anon key
-- (no login required), never locked down the way scenarios/questions
-- were in supabase-lock-scenarios-questions-rls.sql.
-- Run this in the Supabase SQL Editor.
--
-- Checked before writing this: no frontend code reads `settings`
-- directly via the Supabase client (grep found zero matches), and
-- the one backend helper that reads it (ai_scoring.py's _get_setting)
-- is dead code, never called. The only real consumer is the admin
-- panel via the service-role client, which "Service role can manage
-- settings" already covers. Dropping the anon/authenticated grant
-- entirely rather than narrowing it, since nothing needs it.
-- ============================================================

DROP POLICY IF EXISTS "Anyone can read settings" ON public.settings;
