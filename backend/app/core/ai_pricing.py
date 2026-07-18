"""
Cost estimation for LLM and Deepgram STT calls, the two call types with no
existing pricing anywhere in the codebase (TTS and realtime-voice pricing
already live in app.services.realtime.pricing -- reused as-is, not
duplicated here).

Same honesty as that module: these are estimates for cost/margin
dashboards, not invoices. Rates below are ballpark as of 2026-07 -- verify
against each provider's current pricing page before trusting a margin
number that hinges on them:
  https://ai.google.dev/gemini-api/docs/pricing        (Gemini)
  https://openai.com/api/pricing                       (OpenAI)
  https://openrouter.ai/models                         (OpenRouter, per-model)
  https://deepgram.com/pricing                         (Deepgram)
"""
from __future__ import annotations

# $ per 1K tokens: (input_rate, output_rate). Keyed on the exact model
# string each call site already uses (see ai_scoring.py's *_MODEL constants).
LLM_USD_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "google/gemini-3.1-flash-lite": (0.00004, 0.00015),
    "google/gemini-2.5-flash": (0.00008, 0.00030),
    "google/gemini-3.5-flash": (0.00012, 0.00045),
    "gpt-5.4-mini": (0.00015, 0.00060),
    "openai/gpt-5.4-mini": (0.00015, 0.00060),
}
# Any model not listed above (e.g. scenario_generator's vision calls) falls
# back to this rather than silently logging $0 -- an admitted rough guess
# is more useful for spotting a cost regression than a false zero.
_LLM_FALLBACK_USD_PER_1K_TOKENS = (0.0001, 0.0004)

# $ per minute of audio processed. Deepgram bills pre-recorded (REST) and
# streaming slightly differently; the two models in use map 1:1 to that split.
DEEPGRAM_USD_PER_MINUTE: dict[str, float] = {
    "nova-3": 0.0043,   # REST /transcribe
    "nova-2": 0.0059,   # streaming /stt/stream
}
_DEEPGRAM_FALLBACK_USD_PER_MINUTE = 0.0059

# For converting AI cost (USD, from ai_usage_events) into the same currency
# as MRR/plan price (INR) so the admin panel's margin dashboard can show
# "price minus cost-to-serve" as one number. Same honesty as the rates
# above -- a flat estimate, not a live rate; update if it drifts far from
# the real one (no live FX call here, this is a reporting dashboard, not
# a checkout).
USD_TO_INR_RATE = 87.0


def estimate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = LLM_USD_PER_1K_TOKENS.get(model, _LLM_FALLBACK_USD_PER_1K_TOKENS)
    cost = (input_tokens / 1000.0) * in_rate + (output_tokens / 1000.0) * out_rate
    return round(cost, 6)


def estimate_deepgram_cost(model: str, audio_seconds: float) -> float:
    rate = DEEPGRAM_USD_PER_MINUTE.get(model, _DEEPGRAM_FALLBACK_USD_PER_MINUTE)
    return round((audio_seconds / 60.0) * rate, 6)


if __name__ == "__main__":
    # ponytail: smoke-check the cost math itself, not a full test suite.
    assert estimate_llm_cost("gpt-5.4-mini", 1000, 1000) == round(0.00015 + 0.00060, 6)
    assert estimate_llm_cost("unknown/model-x", 1000, 1000) == round(sum(_LLM_FALLBACK_USD_PER_1K_TOKENS), 6)
    assert estimate_llm_cost("gpt-5.4-mini", 0, 0) == 0.0
    assert estimate_deepgram_cost("nova-2", 60) == DEEPGRAM_USD_PER_MINUTE["nova-2"]
    assert estimate_deepgram_cost("unknown-model", 60) == _DEEPGRAM_FALLBACK_USD_PER_MINUTE
    print("ai_pricing self-check OK")
