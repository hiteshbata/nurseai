-- ============================================================
-- Fix: submissions.question_id foreign-keys to questions(id), but
-- speaking/writing submissions actually store a scenarios.id there.
-- Run this in the Supabase SQL Editor.
--
-- Why this hasn't already broken: scenarios currently spans ids 4-18
-- and questions spans 1-18 -- pure coincidence of two independent
-- id sequences happening to overlap so far. The moment either table
-- grows past the other's current max (e.g. the next scenario an
-- admin adds), every speaking/writing submission for it will fail
-- with "insert or update on table submissions violates foreign key
-- constraint submissions_question_id_fkey".
--
-- question_id is genuinely overloaded: for module IN ('speaking',
-- 'writing') the app writes a scenarios.id; for module = 'test' (the
-- /mock-test flow, see frontend/app/mock-test/page.tsx) it writes a
-- real questions.id. A single FK column cannot correctly reference
-- two different tables depending on a sibling column's value, so
-- this adds a separate, correctly-typed column instead of repointing
-- the existing FK (which would just break the 'test' module instead).
--
-- Purely additive: no existing column is touched or backfilled away,
-- so there is no risk to the 'test' module's existing use of
-- question_id -> questions(id).
-- ============================================================

ALTER TABLE public.submissions
  ADD COLUMN IF NOT EXISTS scenario_id BIGINT REFERENCES public.scenarios(id) ON DELETE SET NULL;

-- Backfill: most existing speaking/writing rows' question_id happens to
-- already be a valid scenarios.id (the coincidence above), so this
-- recovers scenario_id for historical rows instead of leaving them null.
-- The EXISTS guard skips the rare row where question_id predates the
-- scenarios table's current id range (confirmed: exactly one such row,
-- from initial test data) -- those are left with scenario_id = NULL
-- rather than violating the new FK.
UPDATE public.submissions
SET scenario_id = question_id
WHERE module IN ('speaking', 'writing')
  AND question_id IS NOT NULL
  AND scenario_id IS NULL
  AND EXISTS (
    SELECT 1 FROM public.scenarios WHERE scenarios.id = submissions.question_id
  );

CREATE INDEX IF NOT EXISTS idx_submissions_scenario_id
  ON public.submissions (scenario_id);
