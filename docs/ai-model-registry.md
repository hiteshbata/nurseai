# AI Model Management — Handover

Built 2026-08-07/08. DB-backed registry replacing every hardcoded AI model ID in the backend. Admin panel at `/admin/ai-models`.

## Seeded purposes (live as of 2026-08-08)

| Purpose | Model | Fallback |
|---|---|---|
| `patient_roleplay` | google / gemini-3.1-flash-lite | none |
| `speaking_scoring_free` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `speaking_scoring_premium` | google / gemini-3.5-flash | openrouter / google/gemini-3.5-flash |
| `writing_scoring` | google / gemini-3.5-flash | openrouter / google/gemini-3.5-flash |
| `writing_ocr` | openrouter / anthropic/claude-sonnet-5 | openrouter / google/gemini-flash-latest |
| `writing_content_extraction` | openrouter / google/gemini-flash-latest | none |
| `reading_ocr` | openrouter / google/gemini-flash-latest | none |
| `reading_explanation` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `reading_content_rewrite` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `dictionary_definition` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `listening_ocr` | openrouter / google/gemini-flash-latest | none |
| `listening_audio_segmentation` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `explanation_mcq` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `scenario_vision` | openrouter / google/gemini-flash-latest | none |
| `scenario_card_generation` | google / gemini-3.5-flash | openrouter / google/gemini-3.5-flash |
| `scenario_library_generation` | google / gemini-3.5-flash | openrouter / google/gemini-3.5-flash |
| `grammar_tutor` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `progress_comparison` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `progress_summary` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `coach` | google / gemini-3.5-flash | openrouter / google/gemini-3.5-flash |
| `open_ended_grading` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `study_plan_generation` | google / gemini-flash-latest | openrouter / google/gemini-flash-latest |
| `realtime_voice_openai_standard` | openai / gpt-realtime | none |
| `realtime_voice_openai_mini` | openai / gpt-realtime-mini | none |
| `realtime_voice_gemini` | google / models/gemini-3.1-flash-live-preview | none |
| `tts_openai` | openai / gpt-4o-mini-tts | none |
| `tts_google_chirp_male` | google / en-GB-Chirp3-HD-Charon | none |
| `tts_google_chirp_female` | google / en-GB-Chirp3-HD-Aoede | none |
| `tts_google_wavenet` | google / en-GB-Wavenet-A | none |
| `stt_deepgram_rest` | deepgram / nova-3 | none |
| `stt_deepgram_stream` | deepgram / nova-2 | none |
| `stt_deepgram_content_rest` | deepgram / nova-2 | none |

Pattern: every `google`-native text purpose falls back to the same model via `openrouter` (native is ~10-30% cheaper, OpenRouter is the safety net). OCR/vision purposes only ever use `openrouter` (multimodal), no native-Gemini fallback. Realtime/TTS/STT have no fallback — single provider per purpose today.

## Database schema

**`ai_models`** — `id, provider, model_name, display_name, api_base, enabled, is_default, priority, fallback_model_id (self-FK), last_health_status, last_health_latency_ms, last_health_checked_at, last_health_error, created_at, updated_at`. Unique on `(provider, model_name)`. RLS on, no policies — service-role only.

**`ai_model_purposes`** — `purpose (PK, free text), model_id (FK -> ai_models, on delete restrict), updated_at`.

**`ai_usage_events`** (existing table, extended) — added `purpose, latency_ms, success, error_message`. Every `_call_ai` attempt (success or failure) writes a row here.

No `api_key` column anywhere — keys stay in env vars (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, or `{PROVIDER}_API_KEY` for anything new).

## How it dispatches

`ai_registry.py`: `PROVIDER_CONFIG` maps `openai`/`openrouter`/`google` to `{family, base_url, key_env}`. Two families: `gemini` (native REST) and `openai_compatible` (generic chat-completions, covers openai + openrouter today). `deepgram` and TTS voice purposes don't go through this dispatcher at all — they're plain `purpose -> model_name` string lookups feeding existing separate call code (Deepgram REST/WS, Google Cloud TTS, OpenAI/Gemini realtime WS).

`ai_scoring._call_ai(messages, purpose, ...)`: resolves purpose -> model config (60s in-process cache) -> tries primary -> tries `fallback_model_id` once on failure -> logs every attempt -> returns a graceful `provider_failure` response if both fail. Never raises to the caller.

## How to add a new provider

1. If it speaks the OpenAI chat-completions wire format (Groq, DeepSeek, Mistral, xAI, Together, Fireworks, Ollama, Azure all do): no code change. In the admin panel, add a model with that `provider` string, its real `model_name`, and `api_base` set to the provider's chat-completions URL. Set an env var named `{PROVIDER}_API_KEY` (e.g. `GROQ_API_KEY`) — `ai_registry._api_key_for()` picks it up automatically via that naming convention.
2. If it needs a genuinely different request/response shape (e.g. AWS Bedrock's SigV4 signing, a true Anthropic-native integration): add a new family function in `ai_registry.py` (copy `_call_openai_compatible`'s shape), register it in `_DISPATCH`, add the provider to `PROVIDER_CONFIG`. Bedrock is currently a stub — `cfg.family` falls through to `openai_compatible` and fails cleanly since Bedrock isn't wire-compatible; it needs this treatment before it'll actually work.

## How to add a new purpose

Two ways:
- **Admin panel**: `/admin/ai-models` → Purpose Mapping → "+ Add purpose" → type the key, pick a model. No migration needed, purpose is free text.
- **Code**: add `purpose="your_new_purpose"` to whatever `_call_ai(...)` (or `ai_registry.get_model_config(...)`) call site needs it, then map it in the admin panel before that code path runs. If it has no mapping, `_call_ai` logs `AI_PURPOSE_NOT_CONFIGURED` and returns the graceful-failure response — it does not guess a default.

## How to change a model

Admin panel → AI Models → Edit on the row → change `model_name`/`provider`/`api_base` → Test → Save. Takes effect for every purpose using that row within ~60s (cache TTL), no deploy/restart. To swap which model serves one specific feature without touching the model itself, use Purpose Mapping instead — point the purpose at a different existing (or new) model row.

## How rollback works

No separate versioning table — reuses `audit_log` (already existed for the rest of the admin panel). Every create/update/delete on `ai_models` or `ai_model_purposes` writes a row there with `detail = {"before": ..., "after": ...}`. The model/purpose's History panel queries that by `(target_type, target_id)`. "Restore this version" on an entry re-applies its `before` snapshot (or deletes the row, if `before` is null — i.e. undoing a create) via `POST /admin/ai-models/history/{id}/rollback`, then logs *that* as a new `action="rollback"` audit entry — so a rollback is itself visible in history and itself reversible. No special undo stack.

## Known gaps

- Bedrock: selectable in theory, not wired (see "add a new provider" above).
- 6 OCR/vision purposes (`writing_ocr`, `reading_ocr`, `listening_ocr`, `scenario_vision`, `writing_content_extraction`) use `extra_payload` to pass OpenRouter's `mistral-ocr` file-parser plugin — that plugin engine string is still hardcoded at each call site (it's a parser flag, not a model ID, out of this refactor's scope).
- Browser click-through of the admin UI wasn't done this session (no test admin credentials on hand) — backend logic and endpoints were verified directly against live Supabase instead; frontend verified via clean `tsc --noEmit` + successful production build.
