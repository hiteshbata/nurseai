"""Shared Cloudflare Turnstile verification for public, unauthenticated
write/AI endpoints. No-op (allow) if TURNSTILE_SECRET_KEY unset, same as the
original /tools/study-plan implementation this was extracted from."""
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_captcha(token: Optional[str], client_ip: str) -> bool:
    if not settings.TURNSTILE_SECRET_KEY:
        return True
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": settings.TURNSTILE_SECRET_KEY, "response": token, "remoteip": client_ip},
            )
        return bool(resp.json().get("success"))
    except Exception as e:
        logger.warning("[CAPTCHA_VERIFY_FAILURE] error=%s", str(e)[:300])
        return False
