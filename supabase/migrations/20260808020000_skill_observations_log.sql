-- Learner Brain Foundation, part 2: raw observation history.
--
-- user_skill_stats only ever stores the current EMA -- each new score
-- overwrites the last one (skill_graph.py._record_sync upserts in place).
-- That's correct and cheap for "what's my weakest skill right now", which
-- is all the Study Hub needs today, so it is NOT being replaced.
--
-- But a rollup with no history behind it can't be replayed, can't have its
-- EMA_ALPHA tuned retroactively, and can't feed a future mastery-decay or
-- band-prediction model -- those all need the individual data points, not
-- just their moving average. This table is that raw log: one append-only
-- row per graded observation, written alongside (not instead of) the
-- existing upsert. No trigger, no backfill, no worker -- writing to it and
-- rolling it up into user_skill_stats is service-layer work for a later
-- milestone. This migration only prepares the table to write into.
CREATE TABLE IF NOT EXISTS public.skill_observations (
    id bigserial PRIMARY KEY,
    user_id uuid NOT NULL,
    product text NOT NULL DEFAULT 'OET',
    skill_tag text NOT NULL,
    score numeric NOT NULL,
    source_module text,
    observed_at timestamptz NOT NULL DEFAULT now()
);

-- Matches the read pattern user_skill_stats already uses: one user's
-- history for one product, newest first.
CREATE INDEX IF NOT EXISTS skill_observations_user_product_idx
    ON public.skill_observations (user_id, product, observed_at DESC);

ALTER TABLE public.skill_observations ENABLE ROW LEVEL SECURITY;

-- Same shape as the existing "Users can manage own skill stats" policy:
-- read-only for the owning user, writes stay service_role-only (the
-- backend is the only writer, same as user_skill_stats today).
CREATE POLICY "Users can view own skill observations"
    ON public.skill_observations FOR SELECT
    TO authenticated
    USING ((select auth.uid()) = user_id);
