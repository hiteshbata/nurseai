-- Step 14: link legacy speaking submissions to session_usage, so the
-- Admin Speaking Evidence Inspector's legacy pipeline can reach persisted
-- session_semantic_state (Step 13) the same way the realtime pipeline
-- already does, instead of always recomputing semantic evidence from
-- scratch.
--
-- submissions is shared by speaking/writing/reading/listening/test
-- (see 20260628000000_schema.sql) -- this column is nullable and is only
-- ever populated by the speaking submission path (/speaking/score).
--
-- Nullable: no backfill is possible or needed -- as of this migration, QA
-- has zero speaking submissions rows (checked live), and there is no
-- deterministic way to infer a historical session_usage_id from a
-- submissions row alone (no shared timestamp/session column ever existed
-- between the two tables). Historical/unlinked rows stay NULL; the Admin
-- Inspector falls back to its existing recompute behavior for those.
--
-- ON DELETE CASCADE mirrors session_semantic_state's own FK to
-- session_usage: a session_usage row is only ever deleted by
-- release_session_charge() for a session that failed before scoring, i.e.
-- before any submissions row referencing it could exist, so this cascade
-- never actually fires against a real submission.
ALTER TABLE public.submissions
  ADD COLUMN IF NOT EXISTS session_usage_id BIGINT
    REFERENCES public.session_usage(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_submissions_session_usage_id
  ON public.submissions (session_usage_id);
