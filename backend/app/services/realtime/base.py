"""
Provider adapter interface.

An adapter's only job is to hide one provider's websocket wire protocol
behind five methods and one event stream. It must contain ZERO business
logic -- no auth, no quota checks, no plan gating, no cost persistence, no
5-minute session timer. All of that lives in the router
(app.routers.speaking_realtime), which is the only caller of this class.

Concretely an adapter:
  - owns exactly one upstream websocket connection to its provider
  - translates outbound audio/control calls into that provider's wire format
  - translates inbound provider messages into the canonical events.py types
  - never talks to Supabase, never knows about session_id/quota/plan

Audio is intentionally asymmetric: `send_audio` takes raw bytes directly
(no base64/JSON wrapping at this layer -- individual adapters do that
internally right before the wire send, since it's provider-specific), and
`receive_events` yields raw `bytes` for inbound audio interleaved with
typed control events, so the router can forward audio straight to the
client websocket with no intermediate allocation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, ClassVar

from app.services.realtime.capabilities import ProviderCapabilities
from app.services.realtime.events import RealtimeEvent


class ProviderConnectError(Exception):
    """Raised by connect() when the upstream handshake fails. The router
    treats this as an immediate fallback trigger -- it never retries a
    connect() call itself.

    Re-evaluated deliberately, not an oversight: connect() uses a 30s
    open_timeout (see openai_adapter.py / gemini_adapter.py), so a "short"
    retry isn't actually available without first shortening that timeout --
    doing so on a guess would slow down the (more common) real-outage case
    to speed up an (unmeasured) transient-blip case. Revisit only with
    production data on how often this actually fires and why."""


class RealtimeProviderAdapter(ABC):
    """One instance per websocket session. Not reused across sessions."""

    # Overridden by each concrete subclass. A *class* attribute -- the
    # router reads AdapterClass.capabilities directly (see factory.py) to
    # configure the frontend before ever constructing an instance, exactly
    # as the "no runtime negotiation" requirement specifies.
    capabilities: ClassVar[ProviderCapabilities]

    def __init__(self, *, system_prompt: str, voice: str, api_key: str) -> None:
        self.system_prompt = system_prompt
        self.voice = voice
        self.api_key = api_key

    @abstractmethod
    async def connect(self) -> None:
        """Open the upstream websocket and send whatever setup/session
        message the provider requires. Raises ProviderConnectError on
        failure -- never swallows connect failures."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Idempotent. Always safe to call, including after a failed or
        already-closed connect()."""

    @abstractmethod
    async def send_audio(self, pcm16_bytes: bytes) -> None:
        """Forward one chunk of raw PCM16 mono audio at
        capabilities.input_sample_rate to the provider."""

    @abstractmethod
    async def cancel_response(self) -> None:
        """Stop the provider's in-flight response, if any. Must be safe to
        call even when no response is in progress, and even for providers
        that don't need an explicit cancel call (no-op in that case)."""

    @abstractmethod
    def receive_events(self) -> AsyncIterator[RealtimeEvent | bytes]:
        """Async-iterate provider messages translated into canonical
        events.py types, with raw inbound audio yielded as plain `bytes`.
        Ends (StopAsyncIteration) when the upstream connection closes --
        the router always treats plain stream-end as an implicit,
        unrecoverable close if no explicit ProviderError was yielded
        first."""
