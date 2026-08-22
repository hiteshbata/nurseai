-- E2.4.3: skill-to-skill relationship graph (public.skill_relationships).
--
-- Purely additive: one new table, no ALTER of any existing table, no data
-- mutation outside this table's own creation/seeding. Same convention as
-- skills/content_skill_map (RLS enabled, zero policies, service-role only).
--
-- Every seeded edge below is backed by a specific line of existing code --
-- see the comment above each INSERT block for the source. Nothing here is
-- a name-match guess. In particular:
--   - reading.part.b / reading.part.c seed only the 5 comprehension skills
--     app/services/reading_skills.py:classify_reading_skill() can actually
--     return for part != "A" (detail, inference, vocabulary, main_idea,
--     writer_view). 'scanning' is NOT seeded for Part B/C: the classifier
--     returns 'scanning' only in the part == "A" branch, so seeding it for
--     B/C would be an invented relationship, not a code-evidenced one.
--   - no technique -> comprehension-skill trains_toward edges are seeded:
--     grepping technique_progress.py / seed_techniques.py / skill_graph.py
--     turned up no code path that links a technique's skill_tag to a
--     reading.skill.* code (technique_skill_tag() just prefixes the
--     technique's own tag, e.g. "technique:scanning" -- it never touches
--     reading.skill.scanning). Sharing an English name is not evidence.
--   - no prerequisite_of rows: out of scope for this phase per plan.

CREATE TABLE IF NOT EXISTS public.skill_relationships (
    id bigserial PRIMARY KEY,
    source_skill_id uuid NOT NULL REFERENCES public.skills(skill_id) ON DELETE RESTRICT,
    target_skill_id uuid NOT NULL REFERENCES public.skills(skill_id) ON DELETE RESTRICT,
    relationship_type text NOT NULL CHECK (relationship_type IN ('assesses', 'trains_toward', 'rolls_up_into', 'prerequisite_of')),
    weight real NULL,
    source text NOT NULL CHECK (source IN ('manual', 'heuristic:code_evidence')),
    created_by uuid NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (source_skill_id <> target_skill_id),
    UNIQUE (source_skill_id, target_skill_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS skill_relationships_source_skill_id_idx ON public.skill_relationships (source_skill_id);
CREATE INDEX IF NOT EXISTS skill_relationships_target_skill_id_idx ON public.skill_relationships (target_skill_id);

ALTER TABLE public.skill_relationships ENABLE ROW LEVEL SECURITY;

-- ── A. Reading Part A assesses scanning + detail ──────────────────────────
-- Evidence: reading_skills.classify_reading_skill(), part == "A" branch --
-- `return "scanning" if qtype == "mcq" else "detail"`.
INSERT INTO public.skill_relationships (source_skill_id, target_skill_id, relationship_type, source)
SELECT p.skill_id, s.skill_id, 'assesses', 'heuristic:code_evidence'
FROM public.skills p, public.skills s
WHERE p.code = 'reading.part.a' AND s.code IN ('reading.skill.scanning', 'reading.skill.detail')
ON CONFLICT (source_skill_id, target_skill_id, relationship_type) DO NOTHING;

-- ── B. Reading Part B/C assess the 5 skills the classifier can return for
-- non-A parts ────────────────────────────────────────────────────────────
-- Evidence: reading_skills.classify_reading_skill(), the part != "A" branch
-- -- keyword patterns for writer-view/vocabulary/main-idea/inference, plus
-- the "detail" fallback when no pattern matches. 'scanning' excluded: see
-- header comment.
INSERT INTO public.skill_relationships (source_skill_id, target_skill_id, relationship_type, source)
SELECT p.skill_id, s.skill_id, 'assesses', 'heuristic:code_evidence'
FROM public.skills p, public.skills s
WHERE p.code IN ('reading.part.b', 'reading.part.c')
  AND s.code IN (
    'reading.skill.detail', 'reading.skill.inference', 'reading.skill.vocabulary',
    'reading.skill.main_idea', 'reading.skill.writer_view'
  )
ON CONFLICT (source_skill_id, target_skill_id, relationship_type) DO NOTHING;

-- ── D. Speaking empathy rolls up into relationship_building ───────────────
-- Evidence: app/services/ai_scoring.py's 3-mode rubric prompt defines
-- "relationship_building: Did the nurse show empathy, respect, and build
-- rapport with the patient?" -- the 3-mode criterion's own description
-- names empathy (the 9-mode criterion) as one of its components.
INSERT INTO public.skill_relationships (source_skill_id, target_skill_id, relationship_type, source)
SELECT e.skill_id, r.skill_id, 'rolls_up_into', 'heuristic:code_evidence'
FROM public.skills e, public.skills r
WHERE e.code = 'speaking.criterion.empathy' AND r.code = 'speaking.criterion.relationship_building'
ON CONFLICT (source_skill_id, target_skill_id, relationship_type) DO NOTHING;
