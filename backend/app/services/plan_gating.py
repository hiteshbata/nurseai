from datetime import datetime, timezone, timedelta
from typing import Literal, Optional

from app.core.plans import GRACE_PERIOD_DAYS, PLAN_PERIOD_DAYS

PlanType = Literal["free", "basic", "pro", "elite"]

PREMIUM_PLANS = ["pro", "elite"]
WRITING_PLANS = ["pro", "elite"]
PRONUNCIATION_PLANS = ["elite"]
MOCK_TEST_PLANS = ["elite"]
STUDY_PLAN_PLANS = ["elite"]
READING_PLANS = ["basic", "pro", "elite"]
LISTENING_PLANS = ["basic", "pro", "elite"]


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
    A free-plan profile with no plan_expires_at (legacy row, migration not
    yet backfilled) is treated as active — there's nothing to expire it
    against, and the backfill migration is expected to have run first.
    A PAID plan with no plan_expires_at is treated as expired instead: that
    shape only occurs if process_payment committed the plan change but the
    grant_subscription_period call that sets the expiry failed right after
    (see grant_subscription_period's docstring in payments.py) — failing
    closed here turns that into a visible/support-fixable gap rather than
    permanent free access to a paid plan."""
    expires_at = parse_timestamp(profile.get("plan_expires_at"))
    if expires_at is None:
        return profile.get("plan", "free") == "free"
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


def get_scoring_purpose(plan: str) -> str:
    """Which ai_model_purposes row scores a speaking attempt -- Admin > AI
    Models controls the actual model behind each tier."""
    if plan in PREMIUM_PLANS:
        return "speaking_scoring_premium"
    return "speaking_scoring_free"


def get_realtime_purpose(plan: str) -> str:
    """OpenAI realtime (STS) model tier -- free/basic get the cheaper mini
    model, Pro/Elite get flagship gpt-realtime. Only applies when
    VOICE_PROVIDER=openai; Gemini has no mini tier wired up yet. Returns an
    ai_model_purposes key -- resolve via ai_registry.get_model_config()."""
    if plan in PREMIUM_PLANS:
        return "realtime_voice_openai_standard"
    return "realtime_voice_openai_mini"


async def get_tts_voice(plan: str, gender: Optional[str] = None) -> str:
    from app.services import ai_registry
    if plan in PREMIUM_PLANS:
        purpose = "tts_google_chirp_male" if gender == "male" else "tts_google_chirp_female"
    else:
        purpose = "tts_google_wavenet"
    return (await ai_registry.get_model_config(purpose)).model_name


def is_premium_voice(voice_name: str) -> bool:
    """True for the higher-cost Chirp3-HD voice tier — gated to Pro/Elite
    so a free/basic client can't request it directly to run up TTS costs."""
    return "Chirp3-HD" in (voice_name or "")


def has_writing_access(plan: str) -> bool:
    return plan in WRITING_PLANS


def has_reading_access(plan: str) -> bool:
    return plan in READING_PLANS


def has_listening_access(plan: str) -> bool:
    return plan in LISTENING_PLANS


def has_free_module_attempt(supabase, user_id: str, module: str) -> bool:
    """True if a free-plan student hasn't yet spent their one lifetime free
    standalone attempt at `module` ("reading" or "listening") -- i.e. no
    `submissions` row for it yet. Mock test content is granted separately via
    has_mock_section_access in mock.py, so a spent mock attempt never eats
    this, and vice versa."""
    res = supabase.table("submissions").select("id", count="exact").eq("user_id", user_id).eq("module", module).execute()
    return (res.count or 0) == 0


def has_pronunciation_access(plan: str) -> bool:
    return plan in PRONUNCIATION_PLANS


def has_mock_test_access(plan: str) -> bool:
    return plan in MOCK_TEST_PLANS


def has_study_plan_access(plan: str) -> bool:
    return plan in STUDY_PLAN_PLANS


def get_scoring_criteria_count(plan: str) -> int:
    """All plans now score against the full 9 OET criteria — differentiation
    between tiers is the scoring model (see get_scoring_purpose), not criteria
    depth. Kept as a function (rather than inlining 9 at call sites) so a
    future tier change has one place to edit. Historical submissions scored
    before this change may still carry the old 3-criteria shape; callers that
    render past feedback must keep handling both (see score_speaking)."""
    return 9


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
