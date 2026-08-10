-- Phase 1A.1: Technique Learning + Micro-Practice Engine foundation.
--
-- Additive only, no changes to any existing table. Mastery tracking
-- deliberately reuses the existing Weakness Graph (user_skill_stats /
-- skill_observations, see app/services/skill_graph.py) under a
-- "technique:<skill_tag>" tag namespace instead of a new progress table --
-- see the approved Phase 1A architecture report for the full rationale.
--
-- Three tables:
--   techniques        -- the catalog + short lesson content, admin-managed
--   micro_practices    -- one small practice exercise per technique
--   practice_attempts  -- one row per learner submission, feeds the skill graph
--
-- RLS: techniques/micro_practices are content tables -- RLS enabled, zero
-- policies, service-role only. This is the same convention as every other
-- content table added since RC4 (ai_models, generated_content_drafts,
-- reading_test_versions, ...) -- the learner catalog/lesson pages are always
-- served through the backend API, never a direct client-side Supabase read.
-- practice_attempts is modeled on the existing public.submissions table
-- (the closest existing per-user attempt record): learner reads/inserts only
-- their own row, service_role can do anything.

CREATE TABLE IF NOT EXISTS public.techniques (
    id bigserial PRIMARY KEY,
    module text NOT NULL CHECK (module IN ('reading', 'listening', 'writing', 'speaking')),
    -- The permanent skill-graph key ("technique:<skill_tag>" is what feeds
    -- user_skill_stats/skill_observations). Kept separate from `slug` so a
    -- future URL/display rename never orphans a learner's mastery history.
    skill_tag text NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    description text,
    learning_objective text,
    -- What it is / why it matters / when to use it / how to do it / common
    -- mistakes / example -- short and practical (Phase 1A.3), not a CMS. One
    -- jsonb blob, same convention as generated_content_drafts.metadata,
    -- instead of a separate lesson_content table.
    lesson_content jsonb NOT NULL DEFAULT '{}'::jsonb,
    difficulty text DEFAULT 'intermediate'
        CHECK (difficulty = ANY (ARRAY['easy', 'medium', 'hard', 'beginner', 'intermediate', 'advanced'])),
    estimated_minutes int,
    sort_order int NOT NULL DEFAULT 0,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (slug),
    UNIQUE (skill_tag)
);

CREATE INDEX IF NOT EXISTS techniques_module_active_sort_idx
    ON public.techniques (module, active, sort_order);

ALTER TABLE public.techniques ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.micro_practices (
    id bigserial PRIMARY KEY,
    technique_id bigint NOT NULL REFERENCES public.techniques(id) ON DELETE CASCADE,
    title text NOT NULL,
    instructions text,
    -- The practice prompt itself (passage excerpt, audio reference, case
    -- notes, patient statement, ...) -- genuinely different shape per
    -- technique, same jsonb-blob convention as scenarios.interlocutor_card.
    content jsonb NOT NULL DEFAULT '{}'::jsonb,
    expected_response jsonb NOT NULL DEFAULT '{}'::jsonb,
    scoring_type text NOT NULL DEFAULT 'rule_based' CHECK (scoring_type IN ('rule_based', 'ai')),
    scoring_config jsonb NOT NULL DEFAULT '{}'::jsonb,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS micro_practices_technique_active_idx
    ON public.micro_practices (technique_id, active);

ALTER TABLE public.micro_practices ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.practice_attempts (
    id bigserial PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    -- Nullable + ON DELETE SET NULL, same convention as
    -- submissions.question_id: a learner's attempt history must survive an
    -- admin later deleting the technique/micro-practice it was taken from.
    technique_id bigint REFERENCES public.techniques(id) ON DELETE SET NULL,
    micro_practice_id bigint REFERENCES public.micro_practices(id) ON DELETE SET NULL,
    response jsonb NOT NULL DEFAULT '{}'::jsonb,
    score numeric,
    feedback jsonb NOT NULL DEFAULT '{}'::jsonb,
    mistakes jsonb NOT NULL DEFAULT '[]'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS practice_attempts_user_id_idx ON public.practice_attempts (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS practice_attempts_technique_id_idx ON public.practice_attempts (technique_id);
CREATE INDEX IF NOT EXISTS practice_attempts_micro_practice_id_idx ON public.practice_attempts (micro_practice_id);

ALTER TABLE public.practice_attempts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own practice attempts"
    ON public.practice_attempts FOR SELECT
    TO authenticated
    USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can insert own practice attempts"
    ON public.practice_attempts FOR INSERT
    TO authenticated
    WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Service role can manage practice attempts"
    ON public.practice_attempts FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
