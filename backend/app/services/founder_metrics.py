"""
Founder-dashboard SaaS metrics: MRR/ARR, subscriber counts, revenue,
churn, plan distribution, and month-over-month trend series for
GET /admin/analytics.

All plan-classification goes through plan_gating.get_plan_from_profile --
the same grace-period-aware logic used for feature gating everywhere else
in the app -- so this dashboard can never disagree with what a user
actually has access to right now.

No historical snapshot table exists yet, so "MRR/active subscribers as of
last month" are not measured, they're derived algebraically from the
standard SaaS MRR waterfall identity:

    mrr_end = mrr_start + new_mrr + expansion_mrr - contraction_mrr - churned_mrr

Given today's live mrr_end (computed directly from user_profiles) and this
month's movement (computed from the payments history), mrr_start falls
out by subtraction. Same idea for active-subscriber counts. This is exact
for the movement components (they're derived from real payment/expiry
timestamps) and exact for the current point -- the only approximation is
walking further back in time compounds each bucket's movement, so older
points in the monthly series drift slightly if a payment or expiry event
was missed by the classification below (see _flow_metrics_for_window).
A monthly snapshot cron + table would remove that drift if precision ever
matters more than the setup cost.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.plans import GRACE_PERIOD_DAYS, PLAN_PRICE_INR
from app.services.plan_gating import get_plan_from_profile, parse_timestamp

logger = logging.getLogger(__name__)

PAID_PLANS = ("basic", "pro", "elite")
PLAN_RANK = {"free": 0, "basic": 1, "pro": 2, "elite": 3}


# ── date bucketing helpers ───────────────────────────────────────────

def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(dt: datetime, delta: int) -> datetime:
    month_index = dt.month - 1 + delta
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    return dt.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


def _count_in_window(rows: List[dict], date_field: str, start: datetime, end: datetime) -> int:
    count = 0
    for row in rows:
        ts = parse_timestamp(row.get(date_field))
        if ts is not None and start <= ts < end:
            count += 1
    return count


# ── payment history classification ───────────────────────────────────

def _build_payment_history(paid_payments: List[dict]) -> Dict[str, List[dict]]:
    """Every successful payment, per user, oldest first -- lets each
    payment be compared against the one immediately before it to tell
    a fresh signup from an upgrade, downgrade, or plain renewal."""
    history: Dict[str, List[dict]] = defaultdict(list)
    for row in sorted(paid_payments, key=lambda r: r["created_at"] or ""):
        history[row["user_id"]].append(row)
    return history


def _flow_metrics_for_window(
    history: Dict[str, List[dict]],
    profiles_by_user: Dict[str, dict],
    start: datetime,
    end: datetime,
) -> Dict[str, float]:
    """New/expansion/contraction/churn MRR movement, cash collected, and
    subscriber counts for events that happened in [start, end).

    A payment is classified by comparing its plan to the same user's
    immediately preceding payment (none = brand-new subscriber; same plan
    = renewal; higher tier = expansion; lower tier = contraction).
    Churn is read from user_profiles.subscription_status/plan_expires_at
    rather than payments, since a lapsed user has no "next payment" to
    compare -- their last known plan comes from their most recent payment
    row instead, because the expiry sweep resets user_profiles.plan to
    'free' once it runs (see admin_sweep_expired_subscriptions).
    """
    new_mrr = expansion_mrr = contraction_mrr = churned_mrr = 0
    new_subscribers = renewed_subscribers = churned_subscribers = 0
    revenue_inr = 0

    for user_id, payments in history.items():
        for i, payment in enumerate(payments):
            ts = parse_timestamp(payment.get("created_at"))
            if ts is None or not (start <= ts < end):
                continue
            revenue_inr += (payment.get("amount") or 0) // 100

            plan = payment.get("plan_id")
            price = PLAN_PRICE_INR.get(plan, 0)
            prev_plan = payments[i - 1].get("plan_id") if i > 0 else None

            if prev_plan is None:
                new_mrr += price
                new_subscribers += 1
            elif prev_plan == plan:
                renewed_subscribers += 1
            elif PLAN_RANK.get(plan, 0) > PLAN_RANK.get(prev_plan, 0):
                expansion_mrr += price - PLAN_PRICE_INR.get(prev_plan, 0)
            else:
                contraction_mrr += PLAN_PRICE_INR.get(prev_plan, 0) - price

    for user_id, profile in profiles_by_user.items():
        if profile.get("subscription_status") != "expired":
            continue
        expires_at = parse_timestamp(profile.get("plan_expires_at"))
        if expires_at is None:
            continue
        lapsed_at = expires_at + timedelta(days=GRACE_PERIOD_DAYS)
        if not (start <= lapsed_at < end):
            continue
        churned_subscribers += 1
        last_paid_plan = history[user_id][-1]["plan_id"] if history.get(user_id) else profile.get("plan")
        churned_mrr += PLAN_PRICE_INR.get(last_paid_plan, 0)

    return {
        "new_mrr_inr": new_mrr,
        "expansion_mrr_inr": expansion_mrr,
        "contraction_mrr_inr": contraction_mrr,
        "churned_mrr_inr": churned_mrr,
        "net_mrr_growth_inr": new_mrr + expansion_mrr - contraction_mrr - churned_mrr,
        "new_subscribers": new_subscribers,
        "renewed_subscribers": renewed_subscribers,
        "churned_subscribers": churned_subscribers,
        "revenue_inr": revenue_inr,
    }


def _card(current: float, previous: float, invert: bool = False) -> Dict[str, Any]:
    """Uniform KPI-card shape: value + comparison vs the prior period.
    `invert` marks cards where a rise is bad news (e.g. churn rate) so the
    frontend can flip which trend direction it colors green/red."""
    delta = round(current - previous, 2)
    return {
        "value": current,
        "previous": previous,
        "delta": delta,
        "change_pct": _pct_change(current, previous),
        "trend": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
        "invert": invert,
    }


# ── insights ──────────────────────────────────────────────────────────

def generate_insights(m: Dict[str, Any]) -> List[str]:
    """Plain-English founder takeaways from the computed metrics. Pure
    function of the already-computed summary -- no I/O, easy to test."""
    insights: List[str] = []
    dist = m["plan_distribution"]
    paid_total = sum(v for k, v in dist.items() if k != "free")

    mrr_card = m["kpi_cards"]["mrr_inr"]
    if mrr_card["previous"] > 0 and mrr_card["change_pct"] != 0:
        direction = "increased" if mrr_card["change_pct"] > 0 else "decreased"
        insights.append(
            f"MRR {direction} {abs(mrr_card['change_pct']):.0f}% this month, to ₹{m['mrr_inr']:,}."
        )

    if paid_total:
        top_plan = max(PAID_PLANS, key=lambda p: dist.get(p, 0))
        if dist.get(top_plan, 0):
            pct = round(dist[top_plan] / paid_total * 100)
            insights.append(f"{top_plan.capitalize()} plan accounts for {pct}% of paid subscribers.")

    if m["mrr_inr"]:
        top_mrr_plan = max(PAID_PLANS, key=lambda p: dist.get(p, 0) * PLAN_PRICE_INR.get(p, 0))
        top_mrr_amount = dist.get(top_mrr_plan, 0) * PLAN_PRICE_INR.get(top_mrr_plan, 0)
        if top_mrr_amount:
            mrr_pct = round(top_mrr_amount / m["mrr_inr"] * 100)
            insights.append(f"{top_mrr_plan.capitalize()} plan contributes {mrr_pct}% of total MRR.")

    conv = m["kpi_cards"]["conversion_rate_pct"]
    if conv["previous"] > 0 and abs(conv["delta"]) >= 1:
        direction = "improved" if conv["delta"] > 0 else "dropped"
        insights.append(f"Conversion rate {direction} {abs(conv['delta']):.1f}pp vs last month.")

    churn = m["kpi_cards"]["churn_rate_pct"]
    if churn["delta"] < -0.5:
        insights.append("Churn is improving — renewals trending up.")
    elif churn["delta"] > 0.5:
        insights.append(f"Churn rate rose to {churn['value']:.1f}% this month — worth a look.")

    if not insights:
        insights.append("Not enough month-over-month data yet for trend insights.")
    return insights


# ── main computation ─────────────────────────────────────────────────

def compute_founder_metrics(
    profiles: List[dict],
    roles: List[dict],
    payments: List[dict],
    now: datetime,
    months: int = 6,
) -> Dict[str, Any]:
    """Pure function: takes already-fetched rows, returns the full
    founder-dashboard payload. No Supabase calls in here -- see
    get_founder_metrics for the I/O wrapper -- so this is unit-testable
    with plain lists of dicts."""
    months = max(2, min(months, 24))
    profiles_by_user = {p["user_id"]: p for p in profiles}
    paid_payments = [p for p in payments if p.get("status") == "paid" and p.get("amount") is not None]
    history = _build_payment_history(paid_payments)

    total_users = len(roles)
    effective_plan_by_user = {
        uid: get_plan_from_profile(profile, now=now) for uid, profile in profiles_by_user.items()
    }
    active_subscribers = sum(1 for plan in effective_plan_by_user.values() if plan in PAID_PLANS)
    free_users = total_users - active_subscribers
    mrr_inr = sum(
        PLAN_PRICE_INR.get(plan, 0) for plan in effective_plan_by_user.values() if plan in PAID_PLANS
    )
    arr_inr = mrr_inr * 12

    plan_distribution = {"free": free_users, "basic": 0, "pro": 0, "elite": 0}
    for plan in effective_plan_by_user.values():
        if plan in PAID_PLANS:
            plan_distribution[plan] += 1

    lifetime_revenue_inr = sum(p["amount"] for p in paid_payments) // 100

    conversion_rate_pct = round(active_subscribers / total_users * 100, 1) if total_users else 0.0
    arpu_inr = round(mrr_inr / total_users, 2) if total_users else 0.0
    arppu_inr = round(mrr_inr / active_subscribers, 2) if active_subscribers else 0.0

    # ── monthly buckets: one _flow_metrics_for_window call per month,
    # oldest first. This month is buckets[-1], last month buckets[-2].
    month_start = _month_start(now)
    bucket_bounds = []
    cursor = _add_months(month_start, -(months - 1))
    for _ in range(months):
        nxt = _add_months(cursor, 1)
        bucket_bounds.append((cursor, nxt))
        cursor = nxt
    # The current (most recent) bucket ends "now", not at the next
    # calendar month start, since that month isn't over yet.
    bucket_bounds[-1] = (bucket_bounds[-1][0], now)

    flows = [_flow_metrics_for_window(history, profiles_by_user, start, end) for start, end in bucket_bounds]
    this_month, last_month = flows[-1], flows[-2]

    # Walk backward from today's live MRR/active-subscriber counts using
    # each bucket's own net movement to reconstruct that bucket's
    # start-of-period stock -- see module docstring for the identity.
    end_mrr, end_active = mrr_inr, active_subscribers
    stocks: List[Dict[str, Any]] = [{}] * months
    for i in range(months - 1, -1, -1):
        flow = flows[i]
        start_active = end_active - flow["new_subscribers"] + flow["churned_subscribers"]
        stocks[i] = {
            "mrr_inr": end_mrr,
            "active_subscribers": end_active,
            "churn_rate_pct": round(flow["churned_subscribers"] / start_active * 100, 1) if start_active > 0 else 0.0,
        }
        end_mrr = end_mrr - flow["net_mrr_growth_inr"]
        end_active = start_active

    monthly_series = [
        {
            "month": bucket_bounds[i][0].strftime("%Y-%m"),
            "mrr_inr": stocks[i]["mrr_inr"],
            "revenue_inr": flows[i]["revenue_inr"],
            "active_subscribers": stocks[i]["active_subscribers"],
            "new_subscribers": flows[i]["new_subscribers"],
            "new_users": _count_in_window(roles, "created_at", bucket_bounds[i][0], bucket_bounds[i][1]),
            "churned_subscribers": flows[i]["churned_subscribers"],
            "churn_rate_pct": stocks[i]["churn_rate_pct"],
        }
        for i in range(months)
    ]

    mrr_prev_inr = stocks[-2]["mrr_inr"]
    active_subscribers_prev = stocks[-2]["active_subscribers"]
    active_subscribers_prev2 = stocks[-3]["active_subscribers"] if months >= 3 else active_subscribers_prev
    new_users_this_month = monthly_series[-1]["new_users"]
    total_users_prev = total_users - new_users_this_month

    conversion_rate_prev_pct = (
        round(active_subscribers_prev / total_users_prev * 100, 1) if total_users_prev else 0.0
    )
    arpu_prev_inr = round(mrr_prev_inr / total_users_prev, 2) if total_users_prev else 0.0

    churn_rate_pct = round(this_month["churned_subscribers"] / active_subscribers_prev * 100, 1) if active_subscribers_prev else 0.0
    churn_rate_prev_pct = round(last_month["churned_subscribers"] / active_subscribers_prev2 * 100, 1) if active_subscribers_prev2 else 0.0
    renewal_rate_pct = round(100 - churn_rate_pct, 1)

    # Standard SaaS estimate: expected customer lifetime in months is
    # 1 / monthly_churn_rate, so LTV = ARPPU * that lifetime. Undefined
    # with zero observed churn (division by zero, and one month of data
    # isn't a real churn rate anyway) -- None rather than a fake infinity.
    ltv_inr = round(arppu_inr / (churn_rate_pct / 100), 2) if churn_rate_pct > 0 else None

    revenue_this_month_inr = this_month["revenue_inr"]
    revenue_last_month_inr = last_month["revenue_inr"]

    metrics: Dict[str, Any] = {
        "mrr_inr": mrr_inr,
        "arr_inr": arr_inr,
        "active_subscribers": active_subscribers,
        "free_users": free_users,
        # No time-boxed trial exists in the schema today -- "free" IS the
        # trial tier (see PLANS[0] in core/plans.py, name="Free Trial").
        # Aliased here rather than fabricated; see the analytics report
        # for the schema change needed for a real, expiring trial.
        "trial_users": free_users,
        "total_users": total_users,
        "paid_conversion_rate_pct": conversion_rate_pct,
        "revenue_this_month_inr": revenue_this_month_inr,
        "lifetime_revenue_inr": lifetime_revenue_inr,
        "arpu_inr": arpu_inr,
        "arppu_inr": arppu_inr,
        "ltv_inr": ltv_inr,
        "churned_subscribers_this_month": this_month["churned_subscribers"],
        "churn_rate_pct": churn_rate_pct,
        "renewal_rate_pct": renewal_rate_pct,
        "plan_distribution": plan_distribution,
        "new_subscribers_this_month": this_month["new_subscribers"],
        "new_users_this_month": new_users_this_month,
        "new_mrr_inr": this_month["new_mrr_inr"],
        "expansion_mrr_inr": this_month["expansion_mrr_inr"],
        "contraction_mrr_inr": this_month["contraction_mrr_inr"],
        "churned_mrr_inr": this_month["churned_mrr_inr"],
        "net_mrr_growth_inr": this_month["net_mrr_growth_inr"],
        "monthly_series": monthly_series,
        "kpi_cards": {
            "mrr_inr": _card(mrr_inr, mrr_prev_inr),
            "arr_inr": _card(arr_inr, mrr_prev_inr * 12),
            "revenue_this_month_inr": _card(revenue_this_month_inr, revenue_last_month_inr),
            "active_subscribers": _card(active_subscribers, active_subscribers_prev),
            "new_subscribers": _card(this_month["new_subscribers"], last_month["new_subscribers"]),
            "churn_rate_pct": _card(churn_rate_pct, churn_rate_prev_pct, invert=True),
            "conversion_rate_pct": _card(conversion_rate_pct, conversion_rate_prev_pct),
            "arpu_inr": _card(arpu_inr, arpu_prev_inr),
        },
    }
    metrics["insights"] = generate_insights(metrics)
    return metrics


# ── Supabase I/O wrapper ─────────────────────────────────────────────

def get_founder_metrics(supabase, now: Optional[datetime] = None, months: int = 6) -> Dict[str, Any]:
    """Fetches the rows compute_founder_metrics needs and runs it. Three
    bulk queries total (profiles, roles, payments) -- no per-user
    round-trips.

    ponytail: pulls full tables into Python rather than aggregating in
    SQL, matching this file's existing convention (see admin_search_users,
    admin_get_stats). Fine while these tables are in the hundreds/low
    thousands of rows; past that, move the aggregation into a Postgres
    view or RPC.
    """
    now = now or datetime.now(timezone.utc)

    profiles = (
        supabase.table("user_profiles")
        .select("user_id, plan, plan_expires_at, subscription_status")
        .execute()
        .data
    )
    roles = supabase.table("user_roles").select("user_id, created_at").execute().data
    payments = (
        supabase.table("payments")
        .select("user_id, plan_id, amount, status, created_at")
        .order("created_at")
        .execute()
        .data
    )

    metrics = compute_founder_metrics(profiles, roles, payments, now=now, months=months)

    # Failed-payment tracking needs the failed_payments table (see
    # backend/migrations/2026-07-18_failed_payments.sql) -- degrade to
    # None rather than erroring if it hasn't been applied yet.
    try:
        month_start = _month_start(now)
        failed = (
            supabase.table("failed_payments")
            .select("id", count="exact")
            .gte("created_at", month_start.isoformat())
            .execute()
        )
        metrics["failed_payments_this_month"] = failed.count or 0
    except Exception:
        logger.warning("failed_payments table not available -- run 2026-07-18_failed_payments.sql")
        metrics["failed_payments_this_month"] = None

    return metrics


if __name__ == "__main__":
    # ponytail: smallest runnable check for the classification/waterfall
    # logic -- not a pytest suite (see tests/test_founder_metrics.py for
    # that), just a fast sanity pass you can run directly.
    _now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    _profiles = [
        {"user_id": "u1", "plan": "pro", "plan_expires_at": (_now + timedelta(days=10)).isoformat(), "subscription_status": "active"},
        {"user_id": "u2", "plan": "free", "plan_expires_at": None, "subscription_status": "none"},
        {"user_id": "u3", "plan": "free", "plan_expires_at": (_now - timedelta(days=20)).isoformat(), "subscription_status": "expired"},
    ]
    _roles = [{"user_id": u, "created_at": (_now - timedelta(days=200)).isoformat()} for u in ("u1", "u2", "u3")]
    _payments = [
        {"user_id": "u1", "plan_id": "basic", "amount": 29900, "status": "paid", "created_at": (_now - timedelta(days=60)).isoformat()},
        {"user_id": "u1", "plan_id": "pro", "amount": 79900, "status": "paid", "created_at": (_now - timedelta(days=5)).isoformat()},
        {"user_id": "u3", "plan_id": "basic", "amount": 29900, "status": "paid", "created_at": (_now - timedelta(days=50)).isoformat()},
    ]
    result = compute_founder_metrics(_profiles, _roles, _payments, now=_now, months=3)
    assert result["active_subscribers"] == 1
    assert result["free_users"] == 2
    assert result["mrr_inr"] == PLAN_PRICE_INR["pro"]
    assert result["expansion_mrr_inr"] == PLAN_PRICE_INR["pro"] - PLAN_PRICE_INR["basic"]
    assert result["churned_subscribers_this_month"] == 1
    assert len(result["monthly_series"]) == 3
    print("founder_metrics self-check OK")
