"""
Static, immutable per-provider capability declarations.

There is deliberately no runtime negotiation here -- the router reads one
of these constants once (via ProviderAdapter.capabilities on the adapter
*class*, not an instance) to decide how to configure frontend audio capture,
whether to enable interim captions, and which features to advertise. If a
provider's actual behavior can't be confirmed against current official
documentation, the field is still set to the best-known value but its name
is listed in `unverified` -- treat those as "assumed, needs a manual check
against a live session before relying on them," not as fact.
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider_name: str

    # Whether the provider supports the nurse interrupting the patient's
    # reply mid-playback (server-side VAD detects speech-over-speech).
    supports_barge_in: bool

    # Whether the *nurse's* (input) transcript arrives as incremental
    # partials the router could stream to the frontend as it's spoken, vs.
    # only as one finalized block per turn.
    supports_partial_transcripts: bool

    # Whether the provider accepts a named voice at session setup.
    supports_voice_selection: bool

    # Whether the provider exposes continuous control (pitch/rate/style)
    # over the synthesized voice, beyond picking a named preset.
    supports_fine_voice_control: bool

    # Whether cancelling an in-flight response requires the router to send
    # an explicit provider message (OpenAI) vs. the provider already having
    # auto-cancelled server-side by the time Interrupted is raised (Gemini).
    # ProviderAdapter.cancel_response() is safe to call unconditionally
    # either way -- this field is informational/for metrics only.
    explicit_cancel_required: bool

    # Whether ProviderAdapter.update_instructions() actually reaches the
    # live provider session (OpenAI: yes, via a follow-up session.update --
    # applies to future responses without touching one already in flight).
    # False means the provider's wire protocol has no documented mechanism
    # for replacing instructions after setup (Gemini's BidiGenerateContent
    # today) -- update_instructions() is still always safe to call, it's
    # just a documented no-op. Informational/for metrics only; the router
    # calls update_instructions() on every provider regardless.
    supports_live_instruction_update: bool

    # Audio the router must tell the frontend to capture at, and must
    # expect to receive back for playback. Sent to the client inside the
    # router's own `session.ready` message -- never hardcoded frontend-side.
    input_sample_rate: int
    output_sample_rate: int
    input_audio_encoding: str
    output_audio_encoding: str

    # Field names in this dataclass whose values are best-effort / could
    # not be confirmed against current official docs at implementation
    # time. See module docstring.
    unverified: tuple[str, ...] = ()


OPENAI_REALTIME_CAPABILITIES = ProviderCapabilities(
    provider_name="openai",
    supports_barge_in=True,
    supports_partial_transcripts=False,
    supports_voice_selection=True,
    supports_fine_voice_control=False,
    explicit_cancel_required=True,
    supports_live_instruction_update=True,
    input_sample_rate=24000,
    output_sample_rate=24000,
    input_audio_encoding="pcm16",
    output_audio_encoding="pcm16",
    # input transcription is whisper-1 running server-side on the completed
    # user turn -- it does not stream partials back over the realtime
    # socket, only conversation.item.input_audio_transcription.completed.
    unverified=("supports_fine_voice_control",),
)

GEMINI_LIVE_CAPABILITIES = ProviderCapabilities(
    provider_name="gemini",
    supports_barge_in=True,
    supports_partial_transcripts=False,
    supports_voice_selection=True,
    supports_fine_voice_control=False,
    explicit_cancel_required=False,
    # BidiGenerateContent's client envelope is exactly {"setup"|"clientContent"
    # |"realtimeInput"|"toolResponse"} (see gemini_adapter.py module docstring)
    # -- no documented message replaces systemInstruction after setup. Not
    # listed in `unverified` because this isn't a best-guess: it's the
    # absence of a documented mechanism, re-check if Google adds one.
    supports_live_instruction_update=False,
    input_sample_rate=16000,
    output_sample_rate=24000,
    input_audio_encoding="pcm16",
    output_audio_encoding="pcm16",
    unverified=(
        # Gemini streams inputTranscription/outputTranscription text as the
        # turn progresses, but whether that's word-by-word partials or a
        # small number of larger chunks isn't documented -- the adapter
        # currently buffers and only forwards on turnComplete either way,
        # so this doesn't change today's behavior, only a future
        # partial-nurse-caption feature.
        "supports_partial_transcripts",
        "supports_fine_voice_control",
        # The full prebuilt voice name catalog (Puck, Kore, Charon, Aoede,
        # Fenrir, ... ) isn't enumerated in the API reference -- confirm the
        # exact list (and any per-locale restrictions) in Google AI Studio
        # before adding more names to GEMINI_VOICE_BY_GENDER.
        "voice_name_catalog",
    ),
)


def capabilities_for(provider_name: str) -> ProviderCapabilities:
    if provider_name == "openai":
        return OPENAI_REALTIME_CAPABILITIES
    if provider_name == "gemini":
        return GEMINI_LIVE_CAPABILITIES
    raise ValueError(f"Unknown voice provider: {provider_name!r}")
