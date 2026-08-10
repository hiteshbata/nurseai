-- Phase B follow-up: register the AI purpose technique_grading.py's AI path
-- uses (grade_ai -> _call_ai(purpose="technique_micro_practice_feedback"))
-- with the existing AI Model Registry. Same pattern as every other purpose
-- added since 20260807000000_ai_model_registry.sql (e.g.
-- 20260807000100_ai_model_registry_purposes_v2.sql,
-- 20260808040000_content_draft_generation_purpose.sql) -- without this row,
-- ai_registry.get_model_config raises PurposeNotConfigured and every
-- AI-graded micro-practice submission would silently return
-- provider_failure forever, not just until an admin happens to notice.
--
-- Free-tier model, same default as most other purposes -- technique
-- micro-practice feedback is short, low-stakes, high-volume, not a case for
-- a paid model by default. An admin can repoint it in Admin > AI Models at
-- any time; this migration only ensures the purpose isn't left unconfigured.

insert into public.ai_model_purposes (purpose, model_id) values
  ('technique_micro_practice_feedback', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest'))
on conflict (purpose) do nothing;
