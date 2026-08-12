-- Phase D: Micro-Practice V2 foundation. Additive only -- no existing table
-- rewritten, no existing row touched (every new column has a DEFAULT so the
-- current 14 seeded micro_practices become valid V2 rows for free).
--
-- micro_practices already had no uniqueness constraint tying it to exactly
-- one row per technique_id, so "many practices per technique" already
-- worked at the schema level -- the only place that assumed a single
-- practice was the router's `.limit(1)` query. This migration adds the
-- three columns needed to make that multiplicity *useful*: difficulty,
-- stage (LEARN is the lesson itself, MASTERED is a derived per-user
-- mastery_level bucket -- neither is a practice-content property, so the
-- practice ladder only needs guided/independent/exam_style), and sort_order
-- to sequence practices within a technique (doubles as the overall
-- progression order across stages, so no separate stage-rank lookup is
-- needed).
--
-- No new table for progression: technique_progress.py already derives a
-- learner-facing mastery bucket from user_skill_stats (attempts, ema_score)
-- -- see mastery_level(). Phase D adds a second pure function,
-- recommended_stage(), that reuses those same buckets/thresholds to pick
-- which stage a learner should attempt next, instead of a new per-user
-- per-technique progress row.
--
-- No new column on practice_attempts: mistakes/feedback are already jsonb
-- and already flexible enough to carry mistake_type/explanation when a
-- micro_practice's expected_response supplies them (see
-- technique_grading.grade_rule_based).

ALTER TABLE public.micro_practices
    ADD COLUMN IF NOT EXISTS difficulty text NOT NULL DEFAULT 'beginner'
        CHECK (difficulty IN ('beginner', 'intermediate', 'exam')),
    ADD COLUMN IF NOT EXISTS stage text NOT NULL DEFAULT 'guided'
        CHECK (stage IN ('guided', 'independent', 'exam_style')),
    ADD COLUMN IF NOT EXISTS sort_order int NOT NULL DEFAULT 0;
