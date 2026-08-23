-- E2.4.4: Learner Brain -> Knowledge Graph bridge (public.user_skill_bridge).
--
-- Purely additive: one new table, no ALTER of any existing table, no data
-- mutation outside this table's own creation. This is a DERIVED READ-SIDE
-- BRIDGE, not a second source of truth: user_skill_stats (skill_graph.py's
-- EMA table) stays the only place scores are written. This table only maps
-- each (user_id, skill_tag) pair already written there onto the canonical
-- skills.skill_id from the E2.4.1 registry, via
-- app/services/skill_bridge_resolver.py's exact LEGACY_TAG_TO_CODE lookup
-- (no string transform, no fuzzy matching, no new skill ever created).
-- Populated by backend/app/services/user_skill_bridge_backfill.py -- never
-- written by skill_graph.py, technique_progress.py, or any router.
--
-- Same convention as skills/content_skill_map/skill_relationships: RLS
-- enabled, zero policies, service-role only, no direct client access.

CREATE TABLE IF NOT EXISTS public.user_skill_bridge (
    id bigserial PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    skill_tag text NOT NULL,
    skill_id uuid NOT NULL REFERENCES public.skills(skill_id) ON DELETE RESTRICT,
    resolved_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, skill_tag)
);

CREATE INDEX IF NOT EXISTS user_skill_bridge_user_id_skill_id_idx ON public.user_skill_bridge (user_id, skill_id);
CREATE INDEX IF NOT EXISTS user_skill_bridge_skill_id_idx ON public.user_skill_bridge (skill_id);

ALTER TABLE public.user_skill_bridge ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.user_skill_bridge IS
  'E2.4.4: derived read-side bridge from legacy user_skill_stats.skill_tag to canonical skills.skill_id. Not a second source of truth -- populated by backend/app/services/user_skill_bridge_backfill.py, never written by skill_graph.py.';
