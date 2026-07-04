from datetime import datetime, timezone, timedelta
from typing import Literal, Optional

from app.core.plans import GRACE_PERIOD_DAYS, PLAN_PERIOD_DAYS

PlanType = Literal["free", "basic", "pro", "elite"]

PREMIUM_PLANS = ["pro", "elite"]
WRITING_PLANS = ["pro", "elite"]
PRONUNCIATION_PLANS = ["elite"]
MOCK_TEST_PLANS = ["elite"]


def parse_timestamp(value) -> Optional[datetime]:
    """Parse a Postgres/PostgREST timestamptz value (str or datetime) into
    an aware UTC datetime. Returns None for missing/unparseable values."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_subscription_active(profile: dict, now: Optional[datetime] = None) -> bool:
    """True if a paid plan is still within its paid period or grace window.
    A profile with no plan_expires_at recorded (legacy row, migration not
    yet backfilled) is treated as active — there's nothing to expire it
    against, and the backfill migration is expected to have run first."""
    expires_at = parse_timestamp(profile.get("plan_expires_at"))
    if expires_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    cutoff = expires_at + timedelta(days=GRACE_PERIOD_DAYS)
    return now <= cutoff


def compute_renewed_expiry(
    now: datetime,
    new_plan: str,
    current_plan: Optional[str],
    current_expires_at: Optional[datetime],
) -> tuple[datetime, bool]:
    """Compute the new plan_expires_at for a successful payment.
    Returns (new_expires_at, is_fresh_start).

    Renewing the same plan while still active/in-grace extends the
    remaining period instead of discarding unused time. Anything else
    (upgrade, downgrade, or renewing after a lapsed period) starts a
    fresh PLAN_PERIOD_DAYS window from now.
    """
    same_plan = current_plan == new_plan
    still_active = (
        current_expires_at is not None
        and now <= current_expires_at + timedelta(days=GRACE_PERIOD_DAYS)
    )
    if same_plan and still_active:
        base = max(now, current_expires_at)
        return base + timedelta(days=PLAN_PERIOD_DAYS), False
    return now + timedelta(days=PLAN_PERIOD_DAYS), True


def get_scoring_model(plan: str) -> str:
    if plan in PREMIUM_PLANS:
        return "google/gemini-3.5-flash"
    return "google/gemini-2.5-flash"


def get_tts_voice(plan: str) -> str:
    if plan in PREMIUM_PLANS:
        return "en-GB-Chirp3-HD-Aoede"
    return "en-GB-Wavenet-A"


def has_writing_access(plan: str) -> bool:
    return plan in WRITING_PLANS


def has_pronunciation_access(plan: str) -> bool:
    return plan in PRONUNCIATION_PLANS


def has_mock_test_access(plan: str) -> bool:
    return plan in MOCK_TEST_PLANS


def get_scoring_criteria_count(plan: str) -> int:
    return 9 if plan in PREMIUM_PLANS else 3


def get_history_limit(plan: str) -> int:
    if plan in PREMIUM_PLANS:
        return 999
    elif plan == "basic":
        return 10
    return 3


def get_plan_from_profile(profile: dict, now: Optional[datetime] = None) -> str:
    """The plan to actually apply for gating purposes. A stored paid plan
    whose period (plus grace) has lapsed is treated as free everywhere
    this is called — scoring model, TTS voice, session limits, feature
    access — without needing a cron job to have already run."""
    plan = profile.get("plan", "free")
    if plan == "free":
        return "free"
    if is_subscription_active(profile, now=now):
        return plan
    return "free"


def get_effective_subscription_status(profile: dict, now: Optional[datetime] = None) -> str:
    """The subscription_status to report to clients. The stored column is
    only updated by a new payment or the admin sweep job, so a lapsed
    subscription can sit as "active" in the database for days after it's
    actually expired — this recomputes it the same way get_plan_from_profile
    does, so /auth/me (or anything else surfacing status) never contradicts
    the plan it's reporting alongside it."""
    stored_status = profile.get("subscription_status", "none")
    plan = profile.get("plan", "free")
    if plan == "free" or stored_status in ("none", "canceled"):
        return stored_status
    return "active" if is_subscription_active(profile, now=now) else "expired"
