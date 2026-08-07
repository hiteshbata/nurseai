-- listening_audio.py's deepgram_transcribe (admin content-creation
-- transcription, pre-recorded) uses nova-2 for its en-IN locale support,
-- same reason speaking.py's live streaming STT uses nova-2 -- but it's a
-- REST call, not streaming, so it isn't "stt_deepgram_stream". It also
-- isn't "stt_deepgram_rest" (nova-3, used for live per-user chat STT,
-- no locale requirement) -- reusing that purpose would silently swap this
-- call's model and lose the en-IN locale support. Distinct purpose.
-- Apply in Supabase SQL editor.

insert into public.ai_model_purposes (purpose, model_id) values
  ('stt_deepgram_content_rest', (select id from public.ai_models where provider = 'deepgram' and model_name = 'nova-2'))
on conflict (purpose) do nothing;
