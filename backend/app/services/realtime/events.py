"""
Canonical realtime voice events shared by every provider adapter.

These are plain, frozen dataclasses -- NOT Pydantic models. They only ever
travel from an adapter to the router, inside one FastAPI process; nothing
here crosses a process boundary or needs JSON-schema validation on the way
out. Pydantic's validation/coercion overhead buys nothing on that path and
these fire once per transcript chunk / turn boundary for the life of a
session, so allocation cost matters.

Only external, untrusted input (raw provider websocket JSON) gets validated
-- that happens inline in each adapter with plain dict.get() calls, and the
adapter is responsible for translating a valid provider event into one of
the types below before it ever reaches the router.

Raw PCM16 audio is deliberately NOT modeled here. Audio bytes flow through
`ProviderAdapter.receive_events()` as bare `bytes` objects alongside these
events (see base.py) so the router can forward them to the client with zero
extra wrapping, copying, or (de)serialization.
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionReady:
    """Emitted once by the adapter after the *provider's own* setup
    handshake completes (OpenAI's `session.updated` ack / Gemini's
    `setupComplete`).

    This is an internal, adapter-to-router signal only -- it is NOT the
    same thing as the `session.ready` message the router sends to the
    frontend. The router sends its client-facing `session.ready` (carrying
    the billing session_id and the audio config from the adapter's *static*
    ProviderCapabilities) immediately after minting/validating the quota
    session, before the provider connection even starts, so a slow or
    failed provider handshake can never cause a duplicate quota charge on
    client retry. This event exists purely so the router can start
    provider-specific timers/metrics from the moment the upstream actually
    confirmed it's ready, rather than from `connect()` returning (which for
    some transports races the handshake).
    """
    provider: str


@dataclass(frozen=True, slots=True)
class TranscriptDelta:
    """Incremental chunk of the patient's (assistant's) spoken reply being
    transcribed. role is always "patient" today but kept explicit rather
    than assumed, since some providers could in principle transcribe both
    sides incrementally."""
    role: str
    delta: str


@dataclass(frozen=True, slots=True)
class TranscriptFinal:
    """A finalized transcript segment for one conversational turn. For the
    nurse (student) side this is the only transcript event ever emitted --
    neither provider's student-side (input) transcription is forwarded to
    the frontend as partials today, see ProviderCapabilities.supports_partial_transcripts."""
    role: str
    transcript: str


@dataclass(frozen=True, slots=True)
class ResponseDone:
    """The assistant's turn (audio + transcript) has fully finished.

    usage is the provider's raw per-response token accounting when it
    reports one (OpenAI's response.done carries response.usage, including
    the cached_tokens that make realtime affordable -- see
    app.services.realtime.pricing). None for providers that don't report
    it (Gemini today), which is what makes the router fall back to
    wall-clock cost estimation instead."""
    usage: dict | None = None


@dataclass(frozen=True, slots=True)
class Interrupted:
    """The nurse started talking while the patient's reply was still
    playing. The router forwards this to the client (which stops local
    playback) and calls adapter.cancel_response() -- safe to call for every
    provider, including ones (Gemini) that already auto-cancelled
    server-side before this event was even raised."""


@dataclass(frozen=True, slots=True)
class ProviderError:
    """A provider-reported or transport-level error.

    recoverable=False tells the router this connection cannot continue and
    fallback logic should engage (see app.services.realtime.base for what
    "fallback" means at the adapter boundary).
    """
    message: str
    code: str | None = None
    recoverable: bool = False


# Every control event an adapter can hand back to the router. Deliberately
# not used as a type union anywhere performance-sensitive -- isinstance()
# dispatch in the router is enough and keeps this file free of behavior.
RealtimeEvent = (
    SessionReady
    | TranscriptDelta
    | TranscriptFinal
    | ResponseDone
    | Interrupted
    | ProviderError
)
