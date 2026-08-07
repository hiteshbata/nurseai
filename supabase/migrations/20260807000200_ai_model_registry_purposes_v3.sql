-- One more purpose missed by the first two passes: open-ended reading/
-- listening answer grading (app/services/open_ended_grading.py) was also
-- defaulting to GEMINI_SCORING_FREE_MODEL but is a distinct feature from
-- MCQ explanation generation.
-- Apply in Supabase SQL editor.

insert into public.ai_model_purposes (purpose, model_id) values
  ('open_ended_grading', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest'))
on conflict (purpose) do nothing;
