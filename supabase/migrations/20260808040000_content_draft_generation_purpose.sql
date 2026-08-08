-- RC3.2 AI Draft Generator: one shared purpose for all six modules per CTO
-- review (do not split into six purposes now -- split later if a module
-- genuinely needs a different model). Reuses the existing AI Model Registry;
-- no new UI, no new dispatch path.
--
-- Apply in Supabase SQL editor.

-- Free-tier model, not the paid gemini-3.5-flash -- draft generation is a
-- high-volume admin tool, keep it on the free tier by default.
insert into public.ai_model_purposes (purpose, model_id) values
  ('content_draft_generation', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest'))
on conflict (purpose) do nothing;
