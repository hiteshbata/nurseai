-- writing.py's admin PDF-import extraction (mistral-ocr, low-volume content
-- tool) is a different purpose from "writing_ocr" (handwritten-letter photo
-- OCR, seeded in the first pass -- high-volume, user-facing, has its real
-- anthropic-primary/gemini-fallback chain). Reading/listening's equivalent
-- admin PDF-import purposes were already seeded correctly in the first pass.
-- Apply in Supabase SQL editor.

insert into public.ai_model_purposes (purpose, model_id) values
  ('writing_content_extraction', (select id from public.ai_models where provider = 'openrouter' and model_name = 'google/gemini-flash-latest'))
on conflict (purpose) do nothing;
