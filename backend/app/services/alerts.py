import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_alert(event: str, detail: str) -> bool:
    """Fire a Slack message via an Incoming Webhook (httpx already a
    dependency, no SDK needed). No-ops and logs if SLACK_ALERT_WEBHOOK_URL
    isn't set -- same pattern as send_email/RESEND_API_KEY. Callers are the
    handful of failures a human should hear about same-day: payment amount
    mismatch, realtime provider connect failure, prune-cron failure. Never
    raises -- an alert failing must not break the caller's own error path."""
    if not settings.SLACK_ALERT_WEBHOOK_URL:
        logger.info("SLACK_ALERT_WEBHOOK_URL not set -- skipping alert: %s | %s", event, detail)
        return False
    try:
        resp = httpx.post(
            settings.SLACK_ALERT_WEBHOOK_URL,
            json={"text": f":rotating_light: *{event}*\n{detail}"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("send_alert failed | event=%s", event)
        return False
