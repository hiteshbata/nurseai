"""
AI cost / margin visibility for the admin panel: what it actually costs to
serve each user, plan, provider, and model -- the number that tells you
whether an AI SaaS is profitable, not just growing.

Reads app.services.cost_tracking's ai_usage_events log (one row per STT/
LLM/TTS/realtime call). That module's own docstring already calls this out
as "the durable log that per-user/per-plan margin reporting reads from" --
this is that reader. Deliberately does NOT read session_usage's cost
columns (best-effort, documented there as "not billing-authoritative").

Every query here is time-windowed. Unlike founder_metrics.py's payments/
profiles pulls (small tables, safe to fetch whole), ai_usage_events is the
highest-volume table in the schema by nature -- one row per AI call inside
every session. An unbounded all-time fetch here is not a safe shortcut;
don't add one. There is no "lifetime AI cost" number for the same reason
-- it isn't actionable the way this-month-vs-last-month is, and computing
it honestly would mean an unbounded scan.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.ai_pricing import USD_TO_INR_RATE
from app.core.plans import PLAN_PRICE_INR
from app.services.founder_metrics import _add_months, _month_start, _pct_change
from app.services.plan_gating import get_plan_from_profile, parse_timestamp

logger = logging.getLogger(__name__)

TOP_MODELS_LIMIT = 6
TOP_SPENDERS_LIMIT = 10
TREND_DAYS = 30
PLAN_TIERS = ("free", "basic", "pro", "elite")


def _in_window(row: dict, start: datetime, end: datetime) -> bool:
    ts = parse_timestamp(row.get("created_at"))
    return ts is not None and start <= ts < end


def _grouped_sum(rows: List[dict], key_field: str) -> Dict[str, float]:
    totals: Dict[str, float] = defaultdict(float)
    for row in rows:
        key = row.get(key_field) or "unknown"
        totals[key] += row.get("cost_usd") or 0
    return dict(totals)


def _ranked(totals: Dict[str, float], label_key: str, top_n: Optional[int] = None) -> List[Dict[str, Any]]:
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    if top_n is None:
        return [{label_key: k, "cost_usd": round(v, 4)} for k, v in ranked]
    top, rest = ranked[:top_n], ranked[top_n:]
    result = [{label_key: k, "cost_usd": round(v, 4)} for k, v in top]
    if rest:
        result.append({label_key: "other", "cost_usd": round(sum(v for _, v in rest), 4)})
    return result


def compute_ai_cost_metrics(
    events: List[dict],
    profiles_by_user: Dict[str, dict],
    now: datetime,
) -> Dict[str, Any]:
    """Pure function: `events` should already be scoped to roughly the
    last two months (see get_ai_cost_metrics for the actual fetch). No I/O
    in here, so this is unit-testable with plain lists of dicts."""
    month_start = _month_start(now)
    prev_month_start = _add_months(month_start, -1)

    this_month = [e for e in events if _in_window(e, month_start, now)]
    last_month = [e for e in events if _in_window(e, prev_month_start, month_start)]

    cost_this_month_usd = round(sum(e.get("cost_usd") or 0 for e in this_month), 2)
    cost_last_month_usd = round(sum(e.get("cost_usd") or 0 for e in last_month), 2)
    calls_this_month = len(this_month)
    estimate_calls = sum(1 for e in this_month if e.get("is_estimate"))

    by_call_type = _ranked(_grouped_sum(this_month, "call_type"), "call_type")
    by_provider = _ranked(_grouped_sum(this_month, "provider"), "provider")
    by_model = _ranked(_grouped_sum(this_month, "model"), "model", top_n=TOP_MODELS_LIMIT)
    by_purpose = _ranked(_grouped_sum(this_month, "purpose"), "purpose", top_n=TOP_MODELS_LIMIT)

    # ── latency + success rate (both columns added 2026-08-07 -- events from
    # before that have no latency_ms and are excluded from the average
    # rather than counted as 0, which would understate it) ──────────────
    latencies = [e["latency_ms"] for e in this_month if e.get("latency_ms") is not None]
    avg_latency_ms = round(sum(latencies) / len(latencies)) if latencies else None
    success_rate_pct = (
        round(sum(1 for e in this_month if e.get("success", True)) / calls_this_month * 100, 1)
        if calls_this_month else None
    )

    # ── per-plan cost + gross margin ────────────────────────────────
    # price_inr - avg cost-to-serve per active user on that plan, in the
    # same currency -- the number that says whether a tier's price
    # actually covers what it costs to run.
    plan_cost_usd: Dict[str, float] = defaultdict(float)
    plan_users: Dict[str, set] = defaultdict(set)
    for e in this_month:
        uid = e.get("user_id")
        if uid is None:
            plan_cost_usd["unattributed"] += e.get("cost_usd") or 0
            continue
        plan = get_plan_from_profile(profiles_by_user.get(uid, {}), now=now)
        plan_cost_usd[plan] += e.get("cost_usd") or 0
        plan_users[plan].add(uid)

    plan_margins = []
    for plan in PLAN_TIERS:
        cost_usd = plan_cost_usd.get(plan, 0.0)
        user_count = len(plan_users.get(plan, ()))
        avg_cost_per_user_usd = cost_usd / user_count if user_count else 0.0
        avg_cost_per_user_inr = avg_cost_per_user_usd * USD_TO_INR_RATE
        price_inr = PLAN_PRICE_INR.get(plan, 0)
        margin_inr = price_inr - avg_cost_per_user_inr
        plan_margins.append({
            "plan": plan,
            "active_users": user_count,
            "total_cost_usd": round(cost_usd, 2),
            "avg_cost_per_user_usd": round(avg_cost_per_user_usd, 4),
            "avg_cost_per_user_inr": round(avg_cost_per_user_inr, 2),
            "price_inr": price_inr,
            "gross_margin_inr": round(margin_inr, 2) if price_inr else None,
            "gross_margin_pct": round(margin_inr / price_inr * 100, 1) if price_inr else None,
        })
    if plan_cost_usd.get("unattributed"):
        plan_margins.append({
            "plan": "unattributed",
            "active_users": 0,
            "total_cost_usd": round(plan_cost_usd["unattributed"], 2),
            "avg_cost_per_user_usd": None,
            "avg_cost_per_user_inr": None,
            "price_inr": None,
            "gross_margin_inr": None,
            "gross_margin_pct": None,
        })

    # ── top spenders this month ─────────────────────────────────────
    # Identity (email/name) lives only in Supabase Auth, not a queryable
    # table -- returning user_id only avoids an extra auth.admin lookup
    # here; the frontend links each row to the existing User 360 page.
    spend_by_user = _grouped_sum([e for e in this_month if e.get("user_id")], "user_id")
    top_spenders = [
        {
            "user_id": uid,
            "cost_usd": round(cost, 4),
            "plan": get_plan_from_profile(profiles_by_user.get(uid, {}), now=now),
        }
        for uid, cost in sorted(spend_by_user.items(), key=lambda kv: kv[1], reverse=True)[:TOP_SPENDERS_LIMIT]
    ]

    # ── daily trend, last TREND_DAYS days ───────────────────────────
    trend_start = (now - timedelta(days=TREND_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)
    daily_cost: Dict[str, float] = defaultdict(float)
    for e in events:
        ts = parse_timestamp(e.get("created_at"))
        if ts is None or ts < trend_start:
            continue
        daily_cost[ts.strftime("%Y-%m-%d")] += e.get("cost_usd") or 0
    daily_trend = [
        {
            "date": day,
            "cost_usd": round(daily_cost.get(day, 0.0), 4),
        }
        for day in (
            (trend_start + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(TREND_DAYS + 1)
        )
    ]

    return {
        "cost_this_month_usd": cost_this_month_usd,
        "cost_last_month_usd": cost_last_month_usd,
        "cost_change_pct": _pct_change(cost_this_month_usd, cost_last_month_usd),
        "calls_this_month": calls_this_month,
        "avg_cost_per_call_usd": round(cost_this_month_usd / calls_this_month, 4) if calls_this_month else 0.0,
        "estimate_ratio_pct": round(estimate_calls / calls_this_month * 100, 1) if calls_this_month else 0.0,
        "by_call_type": by_call_type,
        "by_provider": by_provider,
        "by_model": by_model,
        "by_purpose": by_purpose,
        "avg_latency_ms": avg_latency_ms,
        "success_rate_pct": success_rate_pct,
        "plan_margins": plan_margins,
        "top_spenders": top_spenders,
        "daily_trend": daily_trend,
        "usd_to_inr_rate": USD_TO_INR_RATE,
    }


# ── Supabase I/O wrapper ─────────────────────────────────────────────

def get_ai_cost_metrics(supabase, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Fetches ~2 months of ai_usage_events plus the user_profiles rows
    needed to classify them by plan, then runs the pure computation above.

    Bounded to a fixed window (unlike founder_metrics' full-table pulls --
    see this module's docstring for why) and profiles are fetched only for
    the user_ids that actually appear in that window, not the whole table.
    """
    now = now or datetime.now(timezone.utc)
    window_start = _add_months(_month_start(now), -1)

    events = (
        supabase.table("ai_usage_events")
        .select("user_id, session_id, call_type, provider, model, purpose, cost_usd, is_estimate, latency_ms, success, created_at")
        .gte("created_at", window_start.isoformat())
        .execute()
        .data
    )

    user_ids = sorted({e["user_id"] for e in events if e.get("user_id")})
    profiles_by_user: Dict[str, dict] = {}
    if user_ids:
        profiles = (
            supabase.table("user_profiles")
            .select("user_id, plan, plan_expires_at, subscription_status")
            .in_("user_id", user_ids)
            .execute()
            .data
        )
        profiles_by_user = {p["user_id"]: p for p in profiles}

    return compute_ai_cost_metrics(events, profiles_by_user, now=now)


if __name__ == "__main__":
    # ponytail: smallest runnable check for the grouping/margin math, not
    # a pytest suite (see tests/test_ai_cost_metrics.py for that).
    _now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    _profiles = {
        "u1": {"user_id": "u1", "plan": "pro", "plan_expires_at": (_now + timedelta(days=10)).isoformat(), "subscription_status": "active"},
        "u2": {"user_id": "u2", "plan": "free", "plan_expires_at": None, "subscription_status": "none"},
    }
    _events = [
        {"user_id": "u1", "call_type": "llm", "provider": "google", "model": "gemini-3.5-flash", "purpose": "speaking_scoring_premium", "cost_usd": 0.02, "is_estimate": False, "latency_ms": 800, "success": True, "created_at": (_now - timedelta(days=2)).isoformat()},
        {"user_id": "u1", "call_type": "tts", "provider": "google", "model": "chirp3-hd", "purpose": "tts_google_chirp_female", "cost_usd": 0.01, "is_estimate": True, "latency_ms": None, "success": True, "created_at": (_now - timedelta(days=1)).isoformat()},
        {"user_id": "u2", "call_type": "stt", "provider": "deepgram", "model": "nova-3", "purpose": "stt_deepgram_rest", "cost_usd": 0.005, "is_estimate": False, "latency_ms": 400, "success": True, "created_at": (_now - timedelta(days=1)).isoformat()},
        {"user_id": None, "call_type": "llm", "provider": "google", "model": "gemini-2.5-flash", "purpose": "grammar_tutor", "cost_usd": 0.001, "is_estimate": False, "latency_ms": 200, "success": False, "created_at": (_now - timedelta(days=1)).isoformat()},
    ]
    result = compute_ai_cost_metrics(_events, _profiles, now=_now)
    assert result["calls_this_month"] == 4
    assert result["cost_this_month_usd"] == 0.04
    pro_row = next(r for r in result["plan_margins"] if r["plan"] == "pro")
    assert pro_row["active_users"] == 1
    assert pro_row["total_cost_usd"] == 0.03
    unattributed_row = next(r for r in result["plan_margins"] if r["plan"] == "unattributed")
    assert unattributed_row["total_cost_usd"] == 0.0
    assert result["top_spenders"][0]["user_id"] == "u1"
    assert len(result["daily_trend"]) == TREND_DAYS + 1
    assert result["avg_latency_ms"] == round((800 + 400 + 200) / 3)  # the None latency is excluded, not counted as 0
    assert result["success_rate_pct"] == 75.0
    assert {r["purpose"] for r in result["by_purpose"]} == {
        "speaking_scoring_premium", "tts_google_chirp_female", "stt_deepgram_rest", "grammar_tutor",
    }
    print("ai_cost_metrics self-check OK")
