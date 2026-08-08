# AI System

How SpeakOET dispatches, routes, and observes every AI call. Governed by
ADR-003 in [DECISIONS.md](DECISIONS.md): all AI dispatch goes through the
AI Model Registry — no hardcoded model IDs at call sites. Full handover
detail lives in [docs/ai-model-registry.md](ai-model-registry.md); this
file is the architectural summary that ties it to the rest of the system.

---

## OpenAI Realtime

**Status: V1**

Real-time voice for the Speaking module's live AI patient roleplay.
Dispatched via purposes `realtime_voice_openai_standard` (`gpt-realtime`)
and `realtime_voice_openai_mini` (`gpt-realtime-mini`), no fallback
configured (single provider per purpose today). `VOICE_PROVIDER` is
currently OpenAI — a Gemini Live adapter purpose
(`realtime_voice_gemini`) exists in the registry schema but is unused; no
Gemini API key is provisioned (see [BACKLOG.md](BACKLOG.md) → Never).
Realtime/TTS/STT purposes bypass the generic `ai_registry.py` dispatcher —
they're plain `purpose → model_name` string lookups feeding existing
separate call code (OpenAI/Gemini realtime WS, Deepgram REST/WS, Google
Cloud TTS).

## AI Registry

**Status: V1**

`ai_registry.py` is the dispatcher for every non-realtime, non-TTS/STT AI
call. `PROVIDER_CONFIG` maps `openai` / `openrouter` / `google` to
`{family, base_url, key_env}`. Two dispatch families exist:

- **`gemini`** — native REST, for Google-hosted models.
- **`openai_compatible`** — generic chat-completions shape, covers both
  OpenAI and OpenRouter today, and any future provider that speaks the
  same wire format (Groq, DeepSeek, Mistral, xAI, Together, Fireworks,
  Ollama, Azure — all addable with zero code change, see "Model Routing"
  below).

No `api_key` column exists anywhere in the schema — keys stay in env vars
(`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, or
`{PROVIDER}_API_KEY` by convention for anything new). This is a deliberate
boundary: the registry controls *routing*, never *secrets*.

## Model Routing

**Status: V1**

`ai_scoring._call_ai(messages, purpose, ...)`:

1. Resolve `purpose` → model config (60-second in-process cache, so admin
   panel changes take effect without a deploy or restart).
2. Try the primary model.
3. On failure, try `fallback_model_id` once.
4. Log every attempt (success or failure) to `ai_usage_events`
   (`purpose, latency_ms, success, error_message`).
5. If both primary and fallback fail, return a graceful
   `provider_failure` response. **Never raises to the caller** — an AI
   outage degrades a feature, it does not 500 the endpoint.

**Fallback pattern**: every `google`-native text purpose falls back to the
same model via `openrouter` (native is ~10-30% cheaper; OpenRouter is the
safety net). OCR/vision purposes only ever use `openrouter` (needs
multimodal support) — no native-Gemini fallback exists for those. Realtime
voice, TTS, and STT purposes have no fallback — single provider per
purpose today; adding one is real work (these bypass the generic
dispatcher, see "OpenAI Realtime" above), not a config change.

**Adding a new provider**:
1. If it speaks OpenAI chat-completions format: zero code change. Add a
   model row in `/admin/ai-models` with that `provider` string, real
   `model_name`, and `api_base`. Set `{PROVIDER}_API_KEY` in env —
   `ai_registry._api_key_for()` picks it up by naming convention alone.
2. If it needs a genuinely different wire format (AWS Bedrock's SigV4,
   true Anthropic-native): add a new family function in `ai_registry.py`
   (mirror `_call_openai_compatible`'s shape), register it in
   `_DISPATCH`, add the provider to `PROVIDER_CONFIG`. Bedrock is
   currently a stub for exactly this reason — see
   [BACKLOG.md](BACKLOG.md) → Never.

**Adding a new purpose**: either via `/admin/ai-models` → Purpose Mapping
→ "+ Add purpose" (no migration — purpose is free text), or by adding
`purpose="your_new_purpose"` to a `_call_ai(...)` call site and mapping it
in the admin panel *before* that code path runs. An unmapped purpose logs
`AI_PURPOSE_NOT_CONFIGURED` and returns the graceful-failure response — it
never guesses a default model.

**Rollback**: no separate versioning table. Reuses the existing
`audit_log` (ADR-007 pattern) — every create/update/delete on `ai_models`
or `ai_model_purposes` writes a `{before, after}` snapshot. "Restore this
version" re-applies the `before` snapshot (or deletes the row if `before`
is null, undoing a create) via
`POST /admin/ai-models/history/{id}/rollback`, and logs that rollback
itself as a new audit entry — reversible, and itself visible in history.

## Future LangGraph

**Status: Future (Post PMF, Phase 5)**

Evaluated for multi-step AI workflows — only where a purpose genuinely
needs multi-step reasoning rather than one scoring call. Every purpose
today is single-call (primary → fallback → graceful failure) and that has
been sufficient for scoring, OCR, and content generation so far. Do not
introduce this ahead of a concrete purpose that needs it. See
[ARCHITECTURE.md](ARCHITECTURE.md) → AI Orchestrator.

## Future LiteLLM

**Status: Future (Post PMF, Phase 5)**

Candidate replacement for the hand-rolled `ai_registry.py` dispatcher, if
provider surface area grows enough to justify the dependency. Today's
two-family dispatch (`gemini`, `openai_compatible`) covers every live
provider with a small amount of code; this is not currently justified.

## Observation Pipeline

**Status: V1 (cost/usage observability) / Future (scoring observation
contract)**

Two different things share the word "observation" here — keep them
separate:

- **`ai_usage_events`** (V1): every `_call_ai` attempt, success or
  failure, with `purpose, latency_ms, success, error_message`. This is
  cost/reliability telemetry, feeds the admin cost dashboard and health
  checks. Live today.
- **The Observation Contract** (`skill_observations`, ADR-001, Future):
  the append-only log of *graded learner results* (score per skill per
  module), not AI-call telemetry. Schema exists, no writers yet — see
  [ARCHITECTURE.md](ARCHITECTURE.md) → Observation Contract.

## Learner Brain Integration

**Status: Future (Phase 3)**

Not built. When it exists, the Learner Brain reads from the Observation
Contract (`skill_observations`) and the current-state rollup
(`user_skill_stats`) — it does not call AI models directly for
personalization decisions in V1 scope; it's a query/rollup layer over
scores the Learning Engine already produced. Whether a future
recommendation surface itself needs an AI call (e.g. to phrase a
recommendation) is undecided — do not assume it does.
