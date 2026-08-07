-- AI Model Management registry: DB-backed provider/model config + a
-- purpose -> model mapping, so switching which model serves a feature is
-- an admin-panel edit, not a deploy. See app/services/ai_registry.py and
-- ai_scoring.py's (soon purpose-driven) _call_ai.
--
-- Supersedes the old dead settings-table AI config: ai_scoring.py's
-- _get_setting() reads the 'ai_model'/'ai_patient_model' keys but nothing
-- ever calls it, so they've never actually controlled which model gets
-- used (deleted at the bottom of this file).
--
-- Apply in Supabase SQL editor.

create table if not exists public.ai_models (
  id bigserial primary key,
  provider text not null,
  model_name text not null,
  display_name text not null,
  api_base text,
  enabled boolean not null default true,
  is_default boolean not null default false,
  priority integer not null default 0,
  fallback_model_id bigint references public.ai_models(id) on delete set null,
  last_health_status text,
  last_health_latency_ms integer,
  last_health_checked_at timestamptz,
  last_health_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, model_name)
);

-- Admin-only feature, all access goes through the backend's service-role
-- client -- same lockdown as ai_usage_events (RLS enabled, no policies, so
-- anon/authenticated get zero access and only the service role can touch it).
alter table public.ai_models enable row level security;

create table if not exists public.ai_model_purposes (
  purpose text primary key,
  -- restrict (not cascade): deleting a model that's still wired to a
  -- purpose should fail loudly so an admin reassigns it first, not silently
  -- break the feature that purpose serves.
  model_id bigint not null references public.ai_models(id) on delete restrict,
  updated_at timestamptz not null default now()
);

alter table public.ai_model_purposes enable row level security;

-- Extend the existing per-call log (20260718000000_ai_usage_events.sql) so
-- it captures which feature/purpose made the call and whether it
-- succeeded -- today it only ever logs successes.
alter table public.ai_usage_events add column if not exists purpose text;
alter table public.ai_usage_events add column if not exists latency_ms integer;
alter table public.ai_usage_events add column if not exists success boolean not null default true;
alter table public.ai_usage_events add column if not exists error_message text;

create index if not exists ai_usage_events_purpose_idx on public.ai_usage_events (purpose);

-- Seed today's real, hardcoded model choices (ai_scoring.py's *_MODEL
-- constants, config.py's realtime/TTS defaults, plan_gating.py's TTS voice
-- literals) so this migration changes nothing about what actually gets
-- called -- it only makes the choice editable going forward.
insert into public.ai_models (provider, model_name, display_name, priority) values
  ('google', 'gemini-3.1-flash-lite', 'Gemini 3.1 Flash Lite (persona)', 0),
  ('google', 'gemini-flash-latest', 'Gemini Flash Latest (free-tier scoring)', 0),
  ('google', 'gemini-3.5-flash', 'Gemini 3.5 Flash (premium scoring)', 0),
  ('openrouter', 'google/gemini-flash-latest', 'Gemini Flash Latest via OpenRouter', 1),
  ('openrouter', 'google/gemini-3.5-flash', 'Gemini 3.5 Flash via OpenRouter', 1),
  ('openrouter', 'anthropic/claude-sonnet-5', 'Claude Sonnet 5 via OpenRouter (OCR)', 0),
  ('openai', 'gpt-realtime', 'GPT Realtime (Pro/Elite voice)', 0),
  ('openai', 'gpt-realtime-mini', 'GPT Realtime Mini (free/basic voice)', 0),
  ('google', 'models/gemini-3.1-flash-live-preview', 'Gemini Live (realtime voice)', 0),
  ('openai', 'gpt-4o-mini-tts', 'GPT-4o Mini TTS', 0),
  ('deepgram', 'nova-3', 'Deepgram Nova 3 (REST STT)', 0),
  ('deepgram', 'nova-2', 'Deepgram Nova 2 (streaming STT)', 0),
  ('google', 'en-GB-Chirp3-HD-Charon', 'Google TTS Chirp3 HD (male, premium)', 0),
  ('google', 'en-GB-Chirp3-HD-Aoede', 'Google TTS Chirp3 HD (female, premium)', 0),
  ('google', 'en-GB-Wavenet-A', 'Google TTS Wavenet A (standard)', 0)
on conflict (provider, model_name) do nothing;

-- Wire the google-native rows' fallback to their OpenRouter twin,
-- reproducing _call_ai's existing "try Gemini native first (10-30% cheaper),
-- OpenRouter as backup" behavior as pure data instead of code.
update public.ai_models set fallback_model_id = (
  select id from public.ai_models where provider = 'openrouter' and model_name = 'google/gemini-flash-latest'
) where provider = 'google' and model_name = 'gemini-flash-latest';

update public.ai_models set fallback_model_id = (
  select id from public.ai_models where provider = 'openrouter' and model_name = 'google/gemini-3.5-flash'
) where provider = 'google' and model_name = 'gemini-3.5-flash';

-- writing_ocr's existing fallback chain: Claude via OpenRouter, then Gemini
-- via OpenRouter -- OCR has always gone through OpenRouter only, never
-- native Gemini, so this is not the google-native row above.
update public.ai_models set fallback_model_id = (
  select id from public.ai_models where provider = 'openrouter' and model_name = 'google/gemini-flash-latest'
) where provider = 'openrouter' and model_name = 'anthropic/claude-sonnet-5';

insert into public.ai_model_purposes (purpose, model_id) values
  ('patient_roleplay', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-3.1-flash-lite')),
  ('speaking_scoring_free', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest')),
  ('speaking_scoring_premium', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-3.5-flash')),
  ('writing_scoring', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-3.5-flash')),
  ('writing_ocr', (select id from public.ai_models where provider = 'openrouter' and model_name = 'anthropic/claude-sonnet-5')),
  ('reading_ocr', (select id from public.ai_models where provider = 'openrouter' and model_name = 'google/gemini-flash-latest')),
  ('listening_ocr', (select id from public.ai_models where provider = 'openrouter' and model_name = 'google/gemini-flash-latest')),
  ('scenario_vision', (select id from public.ai_models where provider = 'openrouter' and model_name = 'google/gemini-flash-latest')),
  ('grammar_tutor', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest')),
  ('progress_comparison', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-flash-latest')),
  ('coach', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-3.5-flash')),
  ('scenario_library_generation', (select id from public.ai_models where provider = 'google' and model_name = 'gemini-3.5-flash')),
  ('realtime_voice_openai_standard', (select id from public.ai_models where provider = 'openai' and model_name = 'gpt-realtime')),
  ('realtime_voice_openai_mini', (select id from public.ai_models where provider = 'openai' and model_name = 'gpt-realtime-mini')),
  ('realtime_voice_gemini', (select id from public.ai_models where provider = 'google' and model_name = 'models/gemini-3.1-flash-live-preview')),
  ('tts_openai', (select id from public.ai_models where provider = 'openai' and model_name = 'gpt-4o-mini-tts')),
  ('stt_deepgram_rest', (select id from public.ai_models where provider = 'deepgram' and model_name = 'nova-3')),
  ('stt_deepgram_stream', (select id from public.ai_models where provider = 'deepgram' and model_name = 'nova-2')),
  ('tts_google_chirp_male', (select id from public.ai_models where provider = 'google' and model_name = 'en-GB-Chirp3-HD-Charon')),
  ('tts_google_chirp_female', (select id from public.ai_models where provider = 'google' and model_name = 'en-GB-Chirp3-HD-Aoede')),
  ('tts_google_wavenet', (select id from public.ai_models where provider = 'google' and model_name = 'en-GB-Wavenet-A'))
on conflict (purpose) do nothing;

delete from public.settings where key in ('ai_model', 'ai_patient_model');
