"""Server-side analytics events (PostHog) — used for funnel steps that must
not depend on the client staying on the page after redirect, e.g. payment
completion after a Razorpay checkout handoff."""
import logging
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None
_disabled = False


def _get_client():
    global _client, _disabled
    if _disabled:
        return None
    if _client is not None:
        return _client
    if not settings.POSTHOG_API_KEY:
        _disabled = True
        return None
    try:
        import posthog as posthog_module

        posthog_module.api_key = settings.POSTHOG_API_KEY
        posthog_module.host = settings.POSTHOG_HOST
        _client = posthog_module
        return _client
    except Exception:
        logger.warning("posthog package not available — server-side analytics disabled")
        _disabled = True
        return None


def track_event(distinct_id: str, event: str, properties: Optional[Dict[str, Any]] = None) -> None:
    """Fire-and-forget — PostHog's client queues events on a background
    thread, so this never blocks the request. Failures are logged, never
    raised, since analytics must never break the request it's attached to."""
    client = _get_client()
    if not client:
        return
    try:
        # One PostHog project for every deployment target -- SENTRY_ENVIRONMENT
        # (reused, not PostHog-specific) is what tells rc1/local apart from
        # production in it, same as the frontend's environment super-property.
        event_properties = {"environment": settings.SENTRY_ENVIRONMENT, **(properties or {})}
        client.capture(distinct_id=distinct_id, event=event, properties=event_properties)
    except Exception as e:
        logger.warning("PostHog capture failed for event=%s: %s", event, str(e)[:200])
