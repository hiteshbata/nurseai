"""
Tests for the subscription expiry/renewal lifecycle (LB-6).

Pure unit tests against app.services.plan_gating (the read-side gating
logic, which is real production code) plus contract tests against
app.routers.payments' thin RPC wrappers (get_current_plan,
grant_subscription_period). The actual read-decide-write for extending
plan_expires_at is atomic SQL (grant_subscription_period in
supabase-subscription-lifecycle-migration.sql), not Python — see that
migration for the authoritative implementation. compute_renewed_expiry
below is kept as the algorithmic spec the SQL function mirrors.
No network, no Supabase, no live DB — datetimes are injected explicitly
so the tests are deterministic and don't depend on wall-clock time.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.plan_gating import (
    is_subscription_active,
    get_plan_from_profile,
    get_effective_subscription_status,
    compute_renewed_expiry,
    parse_timestamp,
)
from app.core.plans import PLAN_PERIOD_DAYS, GRACE_PERIOD_DAYS

NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


# ── parse_timestamp ──────────────────────────────────────────────────

def test_parse_timestamp_handles_none():
    assert parse_timestamp(None) is None
    assert parse_timestamp("") is None


def test_parse_timestamp_handles_z_suffix():
    parsed = parse_timestamp("2026-06-15T12:00:00Z")
    assert parsed == NOW


def test_parse_timestamp_handles_datetime_passthrough():
    assert parse_timestamp(NOW) == NOW


# ── is_subscription_active ───────────────────────────────────────────

def test_active_within_paid_period():
    profile = {"plan_expires_at": iso(NOW + timedelta(days=5))}
    assert is_subscription_active(profile, now=NOW) is True


def test_active_within_grace_period():
    # expired 1 day ago, grace is 3 days — still active
    profile = {"plan_expires_at": iso(NOW - timedelta(days=1))}
    assert is_subscription_active(profile, now=NOW) is True


def test_inactive_past_grace_period():
    profile = {"plan_expires_at": iso(NOW - timedelta(days=GRACE_PERIOD_DAYS + 1))}
    assert is_subscription_active(profile, now=NOW) is False


def test_no_expiry_recorded_is_treated_as_active():
    # Legacy row / not yet backfilled — nothing to enforce against.
    assert is_subscription_active({}, now=NOW) is True


# ── get_plan_from_profile (the actual enforcement point) ─────────────

def test_free_plan_is_always_free():
    assert get_plan_from_profile({"plan": "free"}) == "free"


def test_active_paid_plan_is_honored():
    profile = {"plan": "elite", "plan_expires_at": iso(NOW + timedelta(days=10))}
    assert get_plan_from_profile(profile, now=NOW) == "elite"


def test_expired_paid_plan_downgrades_to_free():
    profile = {
        "plan": "elite",
        "plan_expires_at": iso(NOW - timedelta(days=GRACE_PERIOD_DAYS + 1)),
    }
    assert get_plan_from_profile(profile, now=NOW) == "free"


def test_missing_plan_defaults_to_free():
    assert get_plan_from_profile({}, now=NOW) == "free"


# ── compute_renewed_expiry ────────────────────────────────────────────
# No longer called by production code directly — kept as the algorithmic
# spec that supabase-subscription-lifecycle-migration.sql's
# grant_subscription_period SQL function mirrors (same same-plan +
# still-active + GREATEST(now, current_expires_at) logic).

def test_fresh_purchase_starts_full_period_from_now():
    expires_at, is_fresh = compute_renewed_expiry(
        now=NOW, new_plan="pro", current_plan=None, current_expires_at=None,
    )
    assert is_fresh is True
    assert expires_at == NOW + timedelta(days=PLAN_PERIOD_DAYS)


def test_renewal_of_same_active_plan_extends_from_current_expiry():
    current_expires_at = NOW + timedelta(days=10)
    expires_at, is_fresh = compute_renewed_expiry(
        now=NOW, new_plan="pro", current_plan="pro", current_expires_at=current_expires_at,
    )
    assert is_fresh is False
    # Extends from the remaining expiry, not from "now" — user doesn't lose
    # the 10 days they already paid for.
    assert expires_at == current_expires_at + timedelta(days=PLAN_PERIOD_DAYS)


def test_renewal_within_grace_period_extends_from_now_not_the_stale_date():
    # Lapsed 2 days ago (within the 3-day grace window). Still counted as
    # a renewal (is_fresh=False, so plan_started_at isn't reset) but the
    # base is max(now, current_expires_at) — since current_expires_at is
    # already in the past, that's `now`, so they get a full fresh period
    # starting today rather than stacking onto an already-lapsed date.
    current_expires_at = NOW - timedelta(days=2)
    expires_at, is_fresh = compute_renewed_expiry(
        now=NOW, new_plan="pro", current_plan="pro", current_expires_at=current_expires_at,
    )
    assert is_fresh is False
    assert expires_at == NOW + timedelta(days=PLAN_PERIOD_DAYS)


def test_renewal_after_grace_has_fully_lapsed_starts_fresh_from_now():
    # Lapsed well past grace — no unused time to protect, don't stack it
    current_expires_at = NOW - timedelta(days=GRACE_PERIOD_DAYS + 30)
    expires_at, is_fresh = compute_renewed_expiry(
        now=NOW, new_plan="pro", current_plan="pro", current_expires_at=current_expires_at,
    )
    assert is_fresh is True
    assert expires_at == NOW + timedelta(days=PLAN_PERIOD_DAYS)


def test_upgrade_to_different_plan_starts_fresh_even_if_still_active():
    # Currently on an active "basic" plan with 10 days left, upgrades to "elite".
    # Deliberately does NOT stack remaining basic time onto the elite period
    # (proration is a separate feature, not implemented here) — starts a
    # clean elite period from now.
    current_expires_at = NOW + timedelta(days=10)
    expires_at, is_fresh = compute_renewed_expiry(
        now=NOW, new_plan="elite", current_plan="basic", current_expires_at=current_expires_at,
    )
    assert is_fresh is True
    assert expires_at == NOW + timedelta(days=PLAN_PERIOD_DAYS)


def test_downgrade_to_different_plan_starts_fresh():
    current_expires_at = NOW + timedelta(days=10)
    expires_at, is_fresh = compute_renewed_expiry(
        now=NOW, new_plan="basic", current_plan="elite", current_expires_at=current_expires_at,
    )
    assert is_fresh is True
    assert expires_at == NOW + timedelta(days=PLAN_PERIOD_DAYS)


# ── get_effective_subscription_status ─────────────────────────────────
# (regression test for a bug found during the LB-6 verification review:
# /auth/me was returning the raw stored subscription_status, which can
# say "active" for days after plan_expires_at has actually lapsed and
# get_plan_from_profile has already started reporting "free".)

def test_effective_status_free_user():
    assert get_effective_subscription_status({"plan": "free", "subscription_status": "none"}, now=NOW) == "none"


def test_effective_status_active_paid_plan():
    profile = {"plan": "pro", "subscription_status": "active", "plan_expires_at": iso(NOW + timedelta(days=5))}
    assert get_effective_subscription_status(profile, now=NOW) == "active"


def test_effective_status_lapsed_plan_reports_expired_even_if_stored_as_active():
    profile = {
        "plan": "pro",
        "subscription_status": "active",  # stale — sweep hasn't run
        "plan_expires_at": iso(NOW - timedelta(days=GRACE_PERIOD_DAYS + 1)),
    }
    assert get_effective_subscription_status(profile, now=NOW) == "expired"
    # and it must never contradict get_plan_from_profile for the same profile
    assert get_plan_from_profile(profile, now=NOW) == "free"


def test_effective_status_within_grace_still_active():
    profile = {"plan": "pro", "subscription_status": "active", "plan_expires_at": iso(NOW - timedelta(days=1))}
    assert get_effective_subscription_status(profile, now=NOW) == "active"


# ── grant_subscription_period / get_current_plan (RPC-wrapper contract) ──
# The actual read-decide-write now happens atomically inside the
# grant_subscription_period SQL function (supabase-subscription-lifecycle-
# migration.sql), not in Python — see the LB-6 concurrency review: the
# previous Python-side implementation had both a lost-update race AND a
# tautological same-plan check (it read user_profiles.plan AFTER
# process_payment_rpc had already overwritten it to the new plan). These
# tests verify the Python wrapper is a correct, thin pass-through: it
# reads previous_plan BEFORE the payment is processed, and forwards the
# right arguments to the RPC. compute_renewed_expiry (tested above)
# remains the algorithmic spec — the SQL function mirrors it exactly.

class _FakeRpcCall:
    def __init__(self, recorder, name, params, response_data):
        self.recorder = recorder
        self.name = name
        self.params = params
        self.response_data = response_data

    def execute(self):
        self.recorder.append((self.name, self.params))
        return _FakeResult(self.response_data)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeRpcSupabase:
    """Records every .rpc(name, params).execute() call; table() reads
    return canned data for get_current_plan."""
    def __init__(self, table_rows=None, rpc_response=None):
        self.table_rows = table_rows or {}
        self.rpc_response = rpc_response if rpc_response is not None else [
            {"plan_expires_at": iso(NOW + timedelta(days=PLAN_PERIOD_DAYS)), "is_fresh_start": True}
        ]
        self.rpc_calls = []

    def rpc(self, name, params):
        return _FakeRpcCall(self.rpc_calls, name, params, self.rpc_response)

    def table(self, name):
        return _FakeReadOnlyTable(self.table_rows)


class _FakeReadOnlyTable:
    def __init__(self, rows):
        self.rows = rows
        self._filter_user_id = None

    def select(self, _cols):
        return self

    def eq(self, col, val):
        if col == "user_id":
            self._filter_user_id = val
        return self

    def execute(self):
        row = self.rows.get(self._filter_user_id)
        return _FakeResult([row] if row else [])


def test_get_current_plan_reads_before_any_payment_processing(monkeypatch):
    import app.routers.payments as payments_mod

    fake = _FakeRpcSupabase(table_rows={"user-1": {"plan": "basic"}})
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)

    assert payments_mod.get_current_plan("user-1") == "basic"
    assert payments_mod.get_current_plan("no-such-user") is None


def test_grant_subscription_period_calls_rpc_with_previous_plan_and_period_constants(monkeypatch):
    # This is the regression test for the tautology bug: previous_plan
    # must be threaded through to the RPC exactly as the caller captured
    # it (e.g. "basic", from BEFORE process_payment overwrote the column
    # to "elite") — never re-derived from the (by-then-already-new) plan.
    import app.routers.payments as payments_mod

    fake = _FakeRpcSupabase()
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)

    payments_mod.grant_subscription_period("user-1", "elite", previous_plan="basic")

    assert len(fake.rpc_calls) == 1
    name, params = fake.rpc_calls[0]
    assert name == "grant_subscription_period"
    assert params == {
        "p_user_id": "user-1",
        "p_new_plan": "elite",
        "p_previous_plan": "basic",
        "p_period_days": PLAN_PERIOD_DAYS,
        "p_grace_days": GRACE_PERIOD_DAYS,
    }


def test_grant_subscription_period_raises_if_rpc_returns_no_row(monkeypatch):
    import app.routers.payments as payments_mod
    import pytest

    fake = _FakeRpcSupabase(rpc_response=[])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)

    with pytest.raises(RuntimeError):
        payments_mod.grant_subscription_period("ghost-user", "pro", previous_plan="free")


def test_previous_plan_is_captured_before_process_payment_call_in_verify_payment():
    # Structural check: get_current_plan(...) must appear before
    # process_payment_rpc(...) in verify_payment's source, or previous_plan
    # would be read after user_profiles.plan has already been overwritten.
    import inspect
    import app.routers.payments as payments_mod

    src = inspect.getsource(payments_mod.verify_payment)
    assert src.index("get_current_plan(") < src.index("process_payment_rpc(")


def test_verify_payment_checks_order_notes_user_id():
    # verify-payment must reject an order whose notes.user_id doesn't match
    # the caller -- otherwise any authenticated user could pay for their own
    # order but hand the order_id to someone else's account, or vice versa,
    # and grant a plan to a user who never paid.
    import inspect
    import app.routers.payments as payments_mod

    src = inspect.getsource(payments_mod.verify_payment)
    assert "notes_user_id" in src
    assert src.index("notes_user_id") < src.index("process_payment_rpc(")


def test_previous_plan_is_captured_before_process_payment_call_in_webhook():
    # Both the payment.captured and subscription.charged branches of
    # _process_webhook_body share their finalization logic via
    # _finalize_payment, so the ordering guarantee is checked there once.
    import inspect
    import app.routers.payments as payments_mod

    src = inspect.getsource(payments_mod._finalize_payment)
    assert src.index("get_current_plan(") < src.index("process_payment_rpc(")


# ── structural invariants (points 6/7) ────────────────────────────────
# Full integration tests of verify_payment/webhook would need mocked
# Razorpay HMAC signing and FastAPI Request scaffolding this repo has no
# infra for. Instead these lock in the two structural guarantees that
# make retries/failures safe, by inspecting the actual source — so a
# future edit that reorders these calls breaks a test instead of
# silently reopening the double-extension / activate-on-failure holes.

def _extract_event_branch(webhook_src: str, event_marker: str) -> str:
    """Slice out just the `elif event_type == ...` (or `in (...)`) branch
    that contains event_marker, bounded by the next `elif event_type` or
    the final `else:` -- whichever comes first. Scoping to a single branch
    (rather than rindex/index over the whole function) keeps these tests
    correct as more event types are added alongside payment.captured."""
    branch_start = webhook_src.index(event_marker)
    next_elif_idx = webhook_src.find("elif event_type", branch_start + 1)
    next_else_idx = webhook_src.find("\n    else:", branch_start)
    candidates = [i for i in (next_elif_idx, next_else_idx) if i != -1]
    branch_end = min(candidates)
    return webhook_src[branch_start:branch_end]


def test_grant_subscription_period_only_called_after_already_processed_check():
    import inspect
    import app.routers.payments as payments_mod

    verify_src = inspect.getsource(payments_mod.verify_payment)
    already_processed_idx = verify_src.index('"already_processed"')
    grant_call_idx = verify_src.index("grant_subscription_period(")
    assert grant_call_idx > already_processed_idx, (
        "grant_subscription_period must be called after the already_processed "
        "check in verify_payment, or a webhook race can double-extend a single payment"
    )

    # Both the payment.captured and subscription.charged branches share
    # this finalization logic via _finalize_payment, so it's checked once.
    finalize_src = inspect.getsource(payments_mod._finalize_payment)
    already_processed_idx = finalize_src.rindex('"already_processed"')
    grant_call_idx = finalize_src.index("grant_subscription_period(")
    assert grant_call_idx > already_processed_idx, (
        "grant_subscription_period must be called after the already_processed "
        "check in _finalize_payment"
    )


def test_payment_failed_path_never_grants_a_subscription():
    import inspect
    import app.routers.payments as payments_mod

    webhook_src = inspect.getsource(payments_mod._process_webhook_body)
    failed_branch = _extract_event_branch(webhook_src, '"payment.failed"')
    assert "grant_subscription_period" not in failed_branch
    assert "process_payment_rpc" not in failed_branch


def test_subscription_lifecycle_events_never_grant_or_charge():
    """subscription.cancelled/completed/halted only flip auto_renew_enabled
    off -- they must never call grant_subscription_period or
    process_payment_rpc (that's subscription.charged's job, tested above)."""
    import inspect
    import app.routers.payments as payments_mod

    webhook_src = inspect.getsource(payments_mod._process_webhook_body)
    branch = _extract_event_branch(webhook_src, '"subscription.cancelled"')
    assert "grant_subscription_period" not in branch
    assert "process_payment_rpc" not in branch


# ── get_notes: Razorpay sends [] instead of {} for "no notes" on some ──
# ── entities (e.g. subscription-generated payments) -- caught live via ──
# ── ngrok testing: entity.get("notes", {}) doesn't help since the key IS ──
# ── present, just wrongly typed, so .get() on it crashed with 500. ──────

def test_get_notes_handles_list_notes():
    import app.routers.payments as payments_mod

    assert payments_mod.get_notes({"notes": []}) == {}


def test_get_notes_handles_missing_notes():
    import app.routers.payments as payments_mod

    assert payments_mod.get_notes({}) == {}


def test_get_notes_handles_none_notes():
    import app.routers.payments as payments_mod

    assert payments_mod.get_notes({"notes": None}) == {}


def test_get_notes_returns_real_notes_dict():
    import app.routers.payments as payments_mod

    assert payments_mod.get_notes({"notes": {"plan_id": "pro", "user_id": "u1"}}) == {
        "plan_id": "pro",
        "user_id": "u1",
    }


# ── parse_process_payment_result: process_payment is RETURNS text (a ──
# ── scalar) -- PostgREST/postgrest-py hands that back as a bare string, ──
# ── not [{"process_payment": "..."}]. Caught live: every real payment ──
# ── (webhook AND synchronous verify) crashed with TypeError: string ──
# ── indices must be integers the moment this code path actually ran. ──

def test_parse_process_payment_result_handles_bare_string():
    import app.routers.payments as payments_mod

    assert payments_mod.parse_process_payment_result("ok") == "ok"
    assert payments_mod.parse_process_payment_result("already_processed") == "already_processed"


def test_parse_process_payment_result_handles_dict_wrapped_list():
    import app.routers.payments as payments_mod

    assert payments_mod.parse_process_payment_result([{"process_payment": "ok"}]) == "ok"


def test_parse_process_payment_result_handles_raw_string_list():
    import app.routers.payments as payments_mod

    assert payments_mod.parse_process_payment_result(["ok"]) == "ok"


def test_parse_process_payment_result_raises_on_empty():
    import app.routers.payments as payments_mod
    import pytest

    with pytest.raises(RuntimeError):
        payments_mod.parse_process_payment_result([])


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    tests = [f for name, f in vars(mod).items() if name.startswith("test_") and inspect.isfunction(f)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
