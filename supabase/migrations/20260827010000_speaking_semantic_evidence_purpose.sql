-- Step 7 (Speaking semantic evidence layer): register the AI purpose
-- app/services/semantic_evidence.py uses for its 3 narrow classifiers
-- (hidden-info reveal verification, concern exploration/addressing,
-- patient resolution signal). Same pattern as every other purpose added
-- since 20260807000000_ai_model_registry.sql.
--
-- Points at the existing anthropic/claude-sonnet-5 (openrouter) row rather
-- than adding a new model -- it's already configured with a gemini fallback
-- for writing_ocr, which this purpose inherits for free. Semantic
-- interpretation (not creative generation) is exactly Sonnet 5's use case
-- per the Step 7 spec; escalate to a larger model only if a live QA pass
-- shows it's actually inadequate.

insert into public.ai_model_purposes (purpose, model_id) values
  ('speaking_semantic_evidence', (select id from public.ai_models where provider = 'openrouter' and model_name = 'anthropic/claude-sonnet-5'))
on conflict (purpose) do nothing;
