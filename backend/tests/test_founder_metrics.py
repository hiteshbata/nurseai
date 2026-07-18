"""
Tests for the founder-dashboard metrics calculation (app.services.founder_metrics).

Pure unit tests -- no Supabase, no network. Rows are passed in directly as
plain dicts, same pattern as test_subscription_lifecycle.py, so the payment
classification (new/expansion/contraction/renewal/churn) and the MRR
waterfall bridge are verified deterministically against a fixed `now`.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.founder_metrics import compute_founder_metrics, generate_insights
from app.core.plans import PLAN_PRICE_INR

NOW = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def days_ago(n: int) -> str:
    return iso(NOW - timedelta(days=n))


def profile(user_id, plan, expires_in_days=None, status="active"):
    return {
        "user_id": user_id,
        "plan": plan,
        "plan_expires_at": iso(NOW + timedelta(days=expires_in_days)) if expires_in_days is not None else None,
        "subscription_status": status,
    }


def role(user_id, signed_up_days_ago):
    return {"user_id": user_id, "created_at": days_ago(signed_up_days_ago)}


def payment(user_id, plan_id, days_ago_n, plan_price_key=None):
    price = PLAN_PRICE_INR[plan_price_key or plan_id]
    return {
        "user_id": user_id,
        "plan_id": plan_id,
        "amount": price * 100,
        "status": "paid",
        "created_at": days_ago(days_ago_n),
    }


# ── active/free/MRR classification ───────────────────────────────────

def test_active_subscriber_counted_in_mrr():
    profiles = [profile("u1", "pro", expires_in_days=10)]
    roles = [role("u1", 100)]
    payments = [payment("u1", "pro", 100)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    assert m["active_subscribers"] == 1
    assert m["free_users"] == 0
    assert m["mrr_inr"] == PLAN_PRICE_INR["pro"]
    assert m["arr_inr"] == PLAN_PRICE_INR["pro"] * 12


def test_lapsed_plan_counts_as_free_not_active():
    # plan_expires_at well in the past, beyond grace -- get_plan_from_profile
    # treats this as free even though the stored `plan` column still says pro.
    profiles = [profile("u1", "pro", expires_in_days=-30, status="active")]
    roles = [role("u1", 100)]
    payments = [payment("u1", "pro", 100)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    assert m["active_subscribers"] == 0
    assert m["free_users"] == 1
    assert m["mrr_inr"] == 0


def test_user_with_no_profile_row_counts_as_free():
    profiles = []
    roles = [role("u1", 5)]
    payments = []
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    assert m["total_users"] == 1
    assert m["free_users"] == 1
    assert m["trial_users"] == 1


# ── payment classification: new / expansion / contraction / renewal ──

def test_first_ever_payment_is_new_mrr():
    profiles = [profile("u1", "basic", expires_in_days=20)]
    roles = [role("u1", 5)]
    payments = [payment("u1", "basic", 3)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    assert m["new_mrr_inr"] == PLAN_PRICE_INR["basic"]
    assert m["new_subscribers_this_month"] == 1
    assert m["expansion_mrr_inr"] == 0
    assert m["contraction_mrr_inr"] == 0


def test_upgrade_is_expansion_not_new():
    profiles = [profile("u1", "pro", expires_in_days=20)]
    roles = [role("u1", 100)]
    payments = [payment("u1", "basic", 60), payment("u1", "pro", 3)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    assert m["new_mrr_inr"] == 0
    assert m["expansion_mrr_inr"] == PLAN_PRICE_INR["pro"] - PLAN_PRICE_INR["basic"]


def test_downgrade_is_contraction():
    profiles = [profile("u1", "basic", expires_in_days=20)]
    roles = [role("u1", 100)]
    payments = [payment("u1", "elite", 60), payment("u1", "basic", 3)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    assert m["contraction_mrr_inr"] == PLAN_PRICE_INR["elite"] - PLAN_PRICE_INR["basic"]
    assert m["expansion_mrr_inr"] == 0


def test_same_plan_repayment_is_renewal_not_new():
    profiles = [profile("u1", "basic", expires_in_days=20)]
    roles = [role("u1", 100)]
    payments = [payment("u1", "basic", 60), payment("u1", "basic", 3)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    assert m["new_mrr_inr"] == 0
    assert m["new_subscribers_this_month"] == 0


# ── churn ─────────────────────────────────────────────────────────────

def test_expired_profile_within_month_counts_as_churned():
    # Swept by admin_sweep_expired_subscriptions: plan reset to 'free',
    # but plan_expires_at (now 10 days in the past, past grace) survives --
    # that's what churn detection reads.
    profiles = [profile("u1", "free", expires_in_days=-10, status="expired")]
    roles = [role("u1", 100)]
    payments = [payment("u1", "basic", 40)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    assert m["churned_subscribers_this_month"] == 1
    # Lost plan recovered from payment history since user_profiles.plan
    # was already overwritten to 'free' by the sweep.
    assert m["churned_mrr_inr"] == PLAN_PRICE_INR["basic"]


def test_no_churn_when_nothing_expired():
    profiles = [profile("u1", "pro", expires_in_days=20)]
    roles = [role("u1", 100)]
    payments = [payment("u1", "pro", 10)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    assert m["churned_subscribers_this_month"] == 0
    assert m["churn_rate_pct"] == 0.0


# ── revenue ───────────────────────────────────────────────────────────

def test_lifetime_and_monthly_revenue_from_payments():
    profiles = [profile("u1", "pro", expires_in_days=20)]
    roles = [role("u1", 200)]
    payments = [payment("u1", "basic", 200), payment("u1", "pro", 5)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    assert m["lifetime_revenue_inr"] == PLAN_PRICE_INR["basic"] + PLAN_PRICE_INR["pro"]
    assert m["revenue_this_month_inr"] == PLAN_PRICE_INR["pro"]


# ── kpi cards + insights ────────────────────────────────────────────

def test_kpi_cards_have_uniform_shape():
    profiles = [profile("u1", "pro", expires_in_days=20)]
    roles = [role("u1", 100)]
    payments = [payment("u1", "pro", 3)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    for key in ("mrr_inr", "arr_inr", "revenue_this_month_inr", "active_subscribers",
                "new_subscribers", "churn_rate_pct", "conversion_rate_pct", "arpu_inr"):
        card = m["kpi_cards"][key]
        assert set(card) == {"value", "previous", "delta", "change_pct", "trend", "invert"}


def test_insights_are_nonempty_strings():
    profiles = [profile("u1", "pro", expires_in_days=20), profile("u2", "basic", expires_in_days=20)]
    roles = [role("u1", 100), role("u2", 100)]
    payments = [payment("u1", "pro", 3), payment("u2", "basic", 40)]
    m = compute_founder_metrics(profiles, roles, payments, now=NOW)
    insights = generate_insights(m)
    assert insights
    assert all(isinstance(s, str) and s for s in insights)


def test_monthly_series_length_matches_months_param():
    m = compute_founder_metrics([], [], [], now=NOW, months=4)
    assert len(m["monthly_series"]) == 4
    assert m["monthly_series"][-1]["month"] == NOW.strftime("%Y-%m")
