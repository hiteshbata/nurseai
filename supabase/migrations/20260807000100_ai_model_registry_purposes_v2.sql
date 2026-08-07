-- Follow-up to 20260807000000_ai_model_registry.sql: the first pass under-
-- counted distinct _call_ai purposes (several genuinely different features
-- -- reading dictionary lookup, MCQ explanations, study-plan generation,
-- admin content-regeneration tools -- were all defaulting to the same
-- GEMINI_SCORING_FREE_MODEL constant in code, which isn't the same as them
-- being the same purpose). Adds the missing purposes and splits
-- progress.py's per-submission AI summary from compare_attempts' two-
-- attempt comparison, which the first pass conflated under one name.
-- Apply in Supabase SQL editor.

insert into public.ai_model_purposes (purpose, model_id) values
  ('explanation_mcq', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest')),
  ('reading_explanation', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest')),
  ('dictionary_definition', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest')),
  ('reading_content_rewrite', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest')),
  ('study_plan_generation', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest')),
  ('listening_audio_segmentation', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest')),
  ('progress_summary', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest')),
  ('scenario_card_generation', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-3.5-flash'))
on conflict (purpose) do nothing;
