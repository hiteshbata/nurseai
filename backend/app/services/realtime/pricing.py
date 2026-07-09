"""
Cost estimation for realtime voice sessions.

These are estimates for internal cost dashboards and the OpenAI-vs-Gemini
comparison view, NOT invoices -- both providers meter usage in audio tokens
per fixed time slice (OpenAI: 1 input token/100ms, 1 output token/50ms;
Gemini: ~25 tokens/sec for both directions) and bill those tokens at
different per-million rates that change over time. Modeling the exact
token-boundary math would still only be as accurate as the $/token constant
underneath it, so this module instead works off wall-clock seconds of
audio actually sent/received, multiplied by a blended $/minute constant
from app.core.config -- good enough to compare providers against each
other and to catch a cost regression, not good enough to reconcile against
a provider invoice line-by-line.

Update the *_USD_PER_MIN_* settings whenever you check current pricing at:
  https://ai.google.dev/gemini-api/docs/pricing  (Gemini Live)
  https://developers.openai.com/api/docs/pricing (OpenAI Realtime)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings

# Google Cloud TTS, $/1M characters -- Standard/WaveNet vs Chirp3-HD tiers.
# Verify at https://cloud.google.com/text-to-speech/pricing.
GOOGLE_TTS_USD_PER_MILLION_CHARS_STANDARD = 4.0
GOOGLE_TTS_USD_PER_MILLION_CHARS_PREMIUM = 30.0

# Azure Speech pronunciation assessment bills as standard speech-to-text,
# $/audio-hour. Verify at https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/.
AZURE_PRONUNCIATION_USD_PER_AUDIO_HOUR = 1.0


@dataclass(frozen=True, slots=True)
class RealtimeCostEstimate:
    provider: str
    input_seconds: float
    output_seconds: float
    realtime_usd: float


def estimate_realtime_cost(provider: str, input_seconds: float, output_seconds: float) -> RealtimeCostEstimate:
    if provider == "openai":
        per_min_in = settings.OPENAI_REALTIME_USD_PER_MIN_INPUT
        per_min_out = settings.OPENAI_REALTIME_USD_PER_MIN_OUTPUT
    elif provider == "gemini":
        per_min_in = settings.GEMINI_LIVE_USD_PER_MIN_INPUT
        per_min_out = settings.GEMINI_LIVE_USD_PER_MIN_OUTPUT
    else:
        per_min_in = per_min_out = 0.0

    cost = (input_seconds / 60.0) * per_min_in + (output_seconds / 60.0) * per_min_out
    return RealtimeCostEstimate(
        provider=provider,
        input_seconds=input_seconds,
        output_seconds=output_seconds,
        realtime_usd=round(cost, 6),
    )


def estimate_tts_cost(character_count: int, is_premium_voice: bool) -> float:
    rate = GOOGLE_TTS_USD_PER_MILLION_CHARS_PREMIUM if is_premium_voice else GOOGLE_TTS_USD_PER_MILLION_CHARS_STANDARD
    return round((character_count / 1_000_000.0) * rate, 6)


def estimate_azure_pronunciation_cost(audio_seconds: float) -> float:
    return round((audio_seconds / 3600.0) * AZURE_PRONUNCIATION_USD_PER_AUDIO_HOUR, 6)
