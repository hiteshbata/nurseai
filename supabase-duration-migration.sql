-- Migration: Add duration_seconds to submissions table
-- Stores how long each speaking session actually took
-- Go forward only; existing rows get NULL

ALTER TABLE public.submissions
ADD COLUMN IF NOT EXISTS duration_seconds INT;
