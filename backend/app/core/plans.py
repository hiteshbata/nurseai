PLANS = [
    {
        "id": "free",
        "name": "Free Trial",
        "price": 0,
        "period": "forever",
        "description": "Try SpeakOET's AI examiner, free",
        "features": [
            "3 speaking sessions / month",
            "1 free Reading test",
            "1 free Listening test",
            "1 free full Mock Test (Writing feedback locked)",
            "Full 9-criteria AI scoring",
            "AI patient conversation",
            "Standard British voice",
            "Last 3 attempts + progress tracking",
        ],
        "cta": "Start Free",
        "highlight": False,
        "disabled": False,
        "profile_plan": "free",
        "sessions_limit": 3,
    },
    {
        "id": "basic",
        "name": "Basic",
        "price": 299,
        "period": "month",
        "description": "Build confidence with Speaking, Reading & Listening",
        "features": [
            "20 speaking sessions / month",
            "Reading & Listening practice",
            "Full 9-criteria AI scoring",
            "AI patient conversation",
            "Standard British voice",
            "Last 10 attempts + progress tracking",
            "Email support",
        ],
        "cta": "Start Practicing",
        "highlight": False,
        "disabled": False,
        "profile_plan": "basic",
        "sessions_limit": 20,
    },
    {
        "id": "pro",
        "name": "Pro",
        "price": 799,
        "period": "month",
        "description": "Complete OET preparation, including Writing",
        "features": [
            "40 speaking sessions / month",
            "Reading, Listening & Writing practice",
            "Advanced AI feedback & premium conversation",
            "Natural British voice",
            "Handwriting OCR for Writing",
            "Unlimited attempt history",
            "Priority email support",
        ],
        "cta": "Get Pro",
        "highlight": True,
        "disabled": False,
        "profile_plan": "pro",
        "sessions_limit": 40,
    },
    {
        "id": "elite",
        "name": "Elite",
        "price": 1499,
        "period": "month",
        "description": "Everything you need for exam-day success",
        "features": [
            "80 speaking sessions / month",
            "Full Mock Tests (all 4 parts)",
            "Reading, Listening & Writing practice",
            "Pronunciation analysis + AI study plan",
            "Advanced AI feedback & premium conversation",
            "Natural British voice + Handwriting OCR",
            "Unlimited attempt history",
            "WhatsApp priority support",
        ],
        "cta": "Become Exam Ready",
        "highlight": False,
        "disabled": False,
        "profile_plan": "elite",
        "sessions_limit": 80,
    },
]

PLAN_LIMITS = {"free": 3, "basic": 20, "pro": 40, "elite": 80}

# Strict self-serve plan ordering (Free < Basic < Pro < Elite) -- the single
# source of truth for "is this a purchase or a downgrade". Used by both
# GET /plans/me (is_purchasable) and the payment endpoints (payments.py),
# so the rule can't drift between the UI hint and the server-side gate.
PLAN_RANK = {"free": 0, "basic": 1, "pro": 2, "elite": 3}


def is_strict_upgrade(current_plan: str, target_plan: str) -> bool:
    """True only if target_plan strictly outranks current_plan on the
    self-serve ladder. Free is never a valid purchase target regardless of
    current_plan -- self-serve plans are upgrade-only, so a same-plan
    re-purchase is also not an "upgrade" even though nothing here is a
    downgrade either."""
    return (
        target_plan in PLAN_RANK
        and target_plan != "free"
        and PLAN_RANK[target_plan] > PLAN_RANK.get(current_plan, 0)
    )

# Monthly INR price per plan, keyed by profile_plan -- single source of
# truth for anything that needs to turn a plan name into a rupee amount
# (MRR/ARR/ARPU calculations in admin.py and founder_metrics.py).
PLAN_PRICE_INR = {p["profile_plan"]: p["price"] for p in PLANS}

# Subscription lifecycle: how long a paid period lasts, and how much
# extra time past expiry still counts as active (covers renewal-payment
# friction without silently granting a free extra period).
PLAN_PERIOD_DAYS = 30
GRACE_PERIOD_DAYS = 3
