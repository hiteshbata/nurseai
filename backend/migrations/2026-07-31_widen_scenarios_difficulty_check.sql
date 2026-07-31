-- Live constraint only allowed easy/medium/hard, but scenario_generator.py
-- (AI card extraction) and admin.py (manual scenario form) both write
-- beginner/intermediate/advanced, causing 500s on save. Frontend already
-- normalizes both vocabularies (see frontend/app/practice/speaking/shared.ts),
-- so widen the constraint instead of touching either insert path.
ALTER TABLE scenarios DROP CONSTRAINT scenarios_difficulty_check;
ALTER TABLE scenarios ADD CONSTRAINT scenarios_difficulty_check
  CHECK (difficulty = ANY (ARRAY['easy'::text, 'medium'::text, 'hard'::text, 'beginner'::text, 'intermediate'::text, 'advanced'::text]));
