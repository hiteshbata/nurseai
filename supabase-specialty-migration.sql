-- Add specialty column to scenarios table
ALTER TABLE public.scenarios ADD COLUMN IF NOT EXISTS specialty TEXT;
