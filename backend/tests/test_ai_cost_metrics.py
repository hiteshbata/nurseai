"""
Tests for the AI cost/margin calculation (app.services.ai_cost_metrics).

Pure unit tests -- no Supabase, no network. Same pattern as
test_founder_metrics.py: rows passed in directly as plain dicts, verified
deterministically against a fixed `now`.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ai_cost_metrics import compute_ai_cost_metrics, TREND_DAYS
from app.core.plans import PLAN_PRICE_INR
from app.core.ai_pricing import USD_TO_INR_RATE

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


def event(user_id, call_type, provider, model, cost_usd, days_ago_n, is_estimate=False):
    return {
        "user_id": user_id,
        "call_type": call_type,
        "provider": provider,
        "model": model,
        "cost_usd": cost_usd,
        "is_estimate": is_estimate,
        "created_at": days_ago(days_ago_n),
    }


def test_this_month_total_excludes_last_month():
    events = [
        event("u1", "llm", "google", "gemini", 0.10, 3),
        event("u1", "llm", "google", "gemini", 0.20, 40),  # last month
    ]
    m = compute_ai_cost_metrics(events, {"u1": profile("u1", "pro", 20)}, now=NOW)
    assert m["cost_this_month_usd"] == 0.10
    assert m["cost_last_month_usd"] == 0.20
    assert m["calls_this_month"] == 1


def test_by_call_type_and_provider_grouping():
    events = [
        event("u1", "llm", "google", "gemini-3.5-flash", 0.10, 2),
        event("u1", "tts", "google", "chirp3-hd", 0.05, 2),
        event("u1", "stt", "deepgram", "nova-3", 0.02, 2),
    ]
    m = compute_ai_cost_metrics(events, {"u1": profile("u1", "pro", 20)}, now=NOW)
    call_types = {row["call_type"]: row["cost_usd"] for row in m["by_call_type"]}
    assert call_types == {"llm": 0.10, "tts": 0.05, "stt": 0.02}
    providers = {row["provider"]: row["cost_usd"] for row in m["by_provider"]}
    assert providers["google"] == 0.15
    assert providers["deepgram"] == 0.02


def test_by_model_folds_tail_into_other():
    events = [event("u1", "llm", "p", f"model-{i}", 0.01 * (8 - i), 1) for i in range(8)]
    m = compute_ai_cost_metrics(events, {"u1": profile("u1", "pro", 20)}, now=NOW)
    labels = [row["model"] for row in m["by_model"]]
    assert "other" in labels
    assert len(m["by_model"]) == 7  # top 6 + "other"


def test_unattributed_cost_bucketed_separately():
    events = [
        event("u1", "llm", "google", "gemini", 0.10, 1),
        event(None, "llm", "google", "gemini", 0.03, 1),
    ]
    m = compute_ai_cost_metrics(events, {"u1": profile("u1", "pro", 20)}, now=NOW)
    unattributed = next(r for r in m["plan_margins"] if r["plan"] == "unattributed")
    assert unattributed["total_cost_usd"] == 0.03
    assert unattributed["gross_margin_pct"] is None


def test_plan_margin_math():
    events = [
        event("u1", "llm", "google", "gemini", 1.0, 1),  # $1 spent on one pro user
    ]
    m = compute_ai_cost_metrics(events, {"u1": profile("u1", "pro", 20)}, now=NOW)
    pro_row = next(r for r in m["plan_margins"] if r["plan"] == "pro")
    assert pro_row["active_users"] == 1
    assert pro_row["avg_cost_per_user_usd"] == 1.0
    expected_cost_inr = round(1.0 * USD_TO_INR_RATE, 2)
    assert pro_row["avg_cost_per_user_inr"] == expected_cost_inr
    assert pro_row["price_inr"] == PLAN_PRICE_INR["pro"]
    assert pro_row["gross_margin_inr"] == round(PLAN_PRICE_INR["pro"] - expected_cost_inr, 2)


def test_free_plan_has_no_margin_percent():
    events = [event("u1", "llm", "google", "gemini", 0.01, 1)]
    m = compute_ai_cost_metrics(events, {"u1": profile("u1", "free")}, now=NOW)
    free_row = next(r for r in m["plan_margins"] if r["plan"] == "free")
    assert free_row["active_users"] == 1
    assert free_row["gross_margin_pct"] is None  # no price to divide by


def test_lapsed_paid_plan_costs_bucket_as_free():
    # Same grace-period-aware classification as founder_metrics -- a plan
    # whose period lapsed is free for cost attribution too, not pro.
    events = [event("u1", "llm", "google", "gemini", 0.01, 1)]
    m = compute_ai_cost_metrics(events, {"u1": profile("u1", "pro", -30, status="active")}, now=NOW)
    free_row = next(r for r in m["plan_margins"] if r["plan"] == "free")
    pro_row = next(r for r in m["plan_margins"] if r["plan"] == "pro")
    assert free_row["active_users"] == 1
    assert pro_row["active_users"] == 0


def test_top_spenders_sorted_descending():
    events = [
        event("u1", "llm", "google", "gemini", 0.05, 1),
        event("u2", "llm", "google", "gemini", 0.50, 1),
        event("u3", "llm", "google", "gemini", 0.20, 1),
    ]
    profiles = {u: profile(u, "pro", 20) for u in ("u1", "u2", "u3")}
    m = compute_ai_cost_metrics(events, profiles, now=NOW)
    ordered = [row["user_id"] for row in m["top_spenders"]]
    assert ordered == ["u2", "u3", "u1"]


def test_estimate_ratio():
    events = [
        event("u1", "llm", "google", "gemini", 0.01, 1, is_estimate=True),
        event("u1", "llm", "google", "gemini", 0.01, 1, is_estimate=False),
    ]
    m = compute_ai_cost_metrics(events, {"u1": profile("u1", "pro", 20)}, now=NOW)
    assert m["estimate_ratio_pct"] == 50.0


def test_daily_trend_has_fixed_length_and_covers_today():
    events = [event("u1", "llm", "google", "gemini", 0.01, 0)]
    m = compute_ai_cost_metrics(events, {"u1": profile("u1", "pro", 20)}, now=NOW)
    assert len(m["daily_trend"]) == TREND_DAYS + 1
    today_row = next(r for r in m["daily_trend"] if r["date"] == NOW.strftime("%Y-%m-%d"))
    assert today_row["cost_usd"] == 0.01


def test_no_events_returns_zeroed_metrics_not_errors():
    m = compute_ai_cost_metrics([], {}, now=NOW)
    assert m["cost_this_month_usd"] == 0
    assert m["calls_this_month"] == 0
    assert m["avg_cost_per_call_usd"] == 0.0
    assert m["estimate_ratio_pct"] == 0.0
    assert m["top_spenders"] == []
