import logging
from datetime import datetime

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, html: str) -> bool:
    """Fire via Resend's REST API (httpx is already a dependency, no SDK
    needed). No-ops and logs if RESEND_API_KEY isn't set, so reminder crons
    stay safe to run before an account exists -- callers should only mark a
    reminder as sent when this returns True."""
    if not settings.RESEND_API_KEY:
        logger.info("RESEND_API_KEY not set -- skipping email to %s (%s)", to, subject)
        return False
    try:
        resp = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={"from": settings.EMAIL_FROM, "to": [to], "subject": subject, "html": html},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("send_email failed | to=%s subject=%s", to, subject)
        return False


def _format_date(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y")


def render_expiry_reminder(plan: str, plan_expires_at: str) -> str:
    return (
        f"<p>Hi,</p>"
        f"<p>Your <strong>{plan.capitalize()}</strong> plan on SpeakOET expires on "
        f"<strong>{_format_date(plan_expires_at)}</strong>.</p>"
        f'<p>Renew now to keep your access: <a href="{settings.FRONTEND_URL}/pricing">{settings.FRONTEND_URL}/pricing</a></p>'
        f"<p>-- The SpeakOET Team</p>"
    )


def render_failed_payment_reminder(plan_id: str | None, reason: str | None) -> str:
    plan_line = f" for your {plan_id} plan" if plan_id else ""
    reason_line = f"<p>Reason given by your bank: {reason}</p>" if reason else ""
    return (
        f"<p>Hi,</p>"
        f"<p>We tried to charge your card{plan_line} on SpeakOET and it didn't go through.</p>"
        f"{reason_line}"
        f'<p>Please update your payment method to keep your access: <a href="{settings.FRONTEND_URL}/pricing">{settings.FRONTEND_URL}/pricing</a></p>'
        f"<p>-- The SpeakOET Team</p>"
    )
