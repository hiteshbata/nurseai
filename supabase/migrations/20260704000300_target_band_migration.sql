-- ============================================================
-- NurseAI: Normalize target_band to TEXT (letter-grade string)
-- Run this in Supabase SQL Editor
-- ============================================================

-- Step 1: Add a temporary text column
ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS target_band_text TEXT;

-- Step 2: Convert existing float values to letter-grade strings
UPDATE public.user_profiles
  SET target_band_text = CASE
    WHEN target_band >= 4.5 THEN 'A'
    WHEN target_band >= 4.0 THEN 'B'
    WHEN target_band >= 3.5 THEN 'C+'
    WHEN target_band >= 3.0 THEN 'C'
    WHEN target_band >= 2.0 THEN 'D'
    WHEN target_band IS NOT NULL THEN 'E'
    ELSE NULL
  END;

-- Step 3: Drop the old FLOAT column
ALTER TABLE public.user_profiles
  DROP COLUMN IF EXISTS target_band;

-- Step 4: Rename the text column to target_band
ALTER TABLE public.user_profiles
  RENAME COLUMN target_band_text TO target_band;
