-- E2.4.2: content -> skill mapping.
--
-- Generic many-to-many join between the E2.4.1 skills registry
-- (public.skills, see 20260821000000_skill_registry.sql) and content rows
-- across the app. Purely additive: creates one new table, alters nothing
-- existing. Legacy skill_tag strings on techniques/user_skill_stats/etc.
-- are untouched -- see that migration's header comment for why.
--
-- content_type/content_id is a loose polymorphic reference (no DB-level FK,
-- since content lives across several tables: listening_sections, questions,
-- techniques, micro_practices). Which content_type values are valid, and
-- which content_id actually resolves to a row, is enforced at the service
-- layer (app/services/content_skill_map.py) and checked read-only by
-- app/services/content_skill_map_reconciliation.py, not by the DB.
--
-- Scope for this migration (E2.4.2): listening_section, listening_question,
-- technique, micro_practice only. Reading/Writing/Speaking content mapping,
-- prerequisite/parent-child graph, and Content Studio UI are explicitly
-- out of scope -- see docs/E2.4.2 plan.

CREATE TABLE IF NOT EXISTS public.content_skill_map (
  id bigserial PRIMARY KEY,
  skill_id uuid NOT NULL REFERENCES public.skills(skill_id) ON DELETE RESTRICT,
  content_type text NOT NULL,
  content_id bigint NOT NULL,
  relationship_type text NOT NULL CHECK (relationship_type IN ('teaches', 'practices')),
  source text NOT NULL CHECK (source IN ('manual', 'heuristic:part')),
  created_by uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_id, content_type, content_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS idx_content_skill_map_skill_id ON public.content_skill_map (skill_id);
CREATE INDEX IF NOT EXISTS idx_content_skill_map_content ON public.content_skill_map (content_type, content_id);

COMMENT ON TABLE public.content_skill_map IS
  'E2.4.2: content -> skill mapping. content_type/content_id is polymorphic (no DB FK); valid content_type values and existence are enforced/checked at the service layer, not here.';

-- Same convention as skills/techniques/micro_practices: RLS enabled,
-- zero policies -- service-role only, no direct client access.
ALTER TABLE public.content_skill_map ENABLE ROW LEVEL SECURITY;

-- ── backfill: listening_sections.part -> listening.part.<letter> ─────────
-- "teaches": a section is written to exercise that OET part's skill.
-- All sections mapped regardless of is_active -- active/inactive is a
-- display/publishing concern, not a taxonomy concern.
INSERT INTO public.content_skill_map (skill_id, content_type, content_id, relationship_type, source)
SELECT s.skill_id, 'listening_section', ls.id, 'teaches', 'heuristic:part'
FROM public.listening_sections ls
JOIN public.skills s ON s.code = 'listening.part.' || lower(ls.part)
ON CONFLICT (skill_id, content_type, content_id, relationship_type) DO NOTHING;

-- ── backfill: techniques.skill_tag -> technique.<skill_tag> ──────────────
-- Exact match against the skill registry's own generator
-- (skill_registry.py: code = f"technique.{tag}"), covers every module
-- (reading/listening/writing/speaking) since technique.* skills aren't
-- module-restricted mapping targets -- this is the technique catalog
-- itself, not new Reading/Writing/Speaking *content* tagging.
INSERT INTO public.content_skill_map (skill_id, content_type, content_id, relationship_type, source)
SELECT s.skill_id, 'technique', t.id, 'teaches', 'heuristic:part'
FROM public.techniques t
JOIN public.skills s ON s.code = 'technique.' || t.skill_tag
ON CONFLICT (skill_id, content_type, content_id, relationship_type) DO NOTHING;

-- ── backfill: micro_practices inherit their technique's mapped skill ─────
-- "practices": a micro-practice is the exercise, not the lesson.
INSERT INTO public.content_skill_map (skill_id, content_type, content_id, relationship_type, source)
SELECT csm.skill_id, 'micro_practice', mp.id, 'practices', 'heuristic:part'
FROM public.micro_practices mp
JOIN public.content_skill_map csm
  ON csm.content_type = 'technique'
 AND csm.content_id = mp.technique_id
 AND csm.relationship_type = 'teaches'
ON CONFLICT (skill_id, content_type, content_id, relationship_type) DO NOTHING;

-- No backfill for listening_question: skill cannot be safely inferred from
-- question.type (MCQ/short-answer says nothing about which skill it tests).
-- Manual/reviewed mappings go through app/services/content_skill_map.py's
-- add_mapping() with source='manual' -- no Content Studio UI yet.
