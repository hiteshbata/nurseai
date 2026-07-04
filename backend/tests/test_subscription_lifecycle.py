"""
Tests for the subscription expiry/renewal lifecycle (LB-6).

These are pure unit tests against app.services.plan_gating and the
renewal-calculation helper used by app.routers.payments.grant_subscription_period.
No network, no Supabase — datetimes are injected explicitly so the tests
are deterministic and don't depend on wall-clock time.
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


# ── grant_subscription_period end-to-end (fake Supabase double) ──────
# Verifies points 2/3/4 of the LB-6 lifecycle review against the actual
# DB read -> compute -> write path, not just the pure compute function.

class _FakeQuery:
    def __init__(self, table, op, payload=None):
        self.table = table
        self.op = op
        self.payload = payload
        self.filters = {}

    def select(self, _cols):
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def execute(self):
        row = self.table.rows.get(self.filters.get("user_id"))
        if self.op == "update":
            row = row or {}
            row.update(self.payload)
            self.table.rows[self.filters["user_id"]] = row
            return _FakeResult([row])
        return _FakeResult([row] if row else [])


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self):
        self.rows = {}

    def select(self, _cols):
        return _FakeQuery(self, "select")

    def update(self, payload):
        return _FakeQuery(self, "update", payload)


class _FakeSupabase:
    def __init__(self):
        self._tables = {"user_profiles": _FakeTable()}

    def table(self, name):
        return self._tables[name]


def test_grant_subscription_period_fresh_grant_and_renewal(monkeypatch):
    import app.routers.payments as payments_mod

    fake = _FakeSupabase()
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)

    user_id = "user-1"
    fake._tables["user_profiles"].rows[user_id] = {"plan": "free", "plan_expires_at": None}

    # First payment: fresh grant (point 2 — paid access exists after payment)
    payments_mod.grant_subscription_period(user_id, "pro")
    row = fake._tables["user_profiles"].rows[user_id]
    assert row["subscription_status"] == "active"
    first_expiry = parse_timestamp(row["plan_expires_at"])
    assert first_expiry is not None
    assert first_expiry > datetime.now(timezone.utc) + timedelta(days=PLAN_PERIOD_DAYS - 1)
    assert "plan_started_at" in row  # fresh start records when the period began

    # Second payment for the SAME plan before expiry: renewal extends,
    # doesn't reset the clock (point 4).
    row["plan"] = "pro"  # simulates process_payment_rpc having set this
    payments_mod.grant_subscription_period(user_id, "pro")
    second_expiry = parse_timestamp(fake._tables["user_profiles"].rows[user_id]["plan_expires_at"])
    assert second_expiry > first_expiry  # extended, not reset to a shorter/equal date
    assert second_expiry - first_expiry >= timedelta(days=PLAN_PERIOD_DAYS - 1)


def test_grant_subscription_period_sequential_double_call_is_additive_not_corrupt():
    # Guards point 5 ("multiple payments do not create inconsistent state")
    # for the *sequential* case (e.g. a user legitimately buys two months
    # back to back). True concurrent-race safety depends on process_payment_rpc's
    # own locking, which isn't in this repo — see the review notes for that gap.
    #
    # grant_subscription_period's renewal-vs-fresh-start decision reads
    # user_profiles.plan and compares it to the new plan being granted. In
    # production this only works correctly because process_payment_rpc is
    # called (and presumed to synchronously commit user_profiles.plan)
    # BEFORE grant_subscription_period runs — so this test sets row["plan"]
    # between calls to reproduce that same ordering. If that RPC assumption
    # is ever wrong (async/deferred write), this same-plan detection would
    # silently misfire — see the review notes.
    import app.routers.payments as payments_mod

    fake = _FakeSupabase()
    user_id = "user-2"
    fake._tables["user_profiles"].rows[user_id] = {"plan": "free", "plan_expires_at": None}

    import unittest.mock as mock
    with mock.patch.object(payments_mod, "get_supabase", lambda: fake):
        payments_mod.grant_subscription_period(user_id, "elite")
        fake._tables["user_profiles"].rows[user_id]["plan"] = "elite"  # simulates process_payment_rpc's write
        payments_mod.grant_subscription_period(user_id, "elite")

    row = fake._tables["user_profiles"].rows[user_id]
    expiry = parse_timestamp(row["plan_expires_at"])
    # Two full periods stacked, not a single period and not corrupted/reset.
    assert expiry >= datetime.now(timezone.utc) + timedelta(days=2 * PLAN_PERIOD_DAYS - 1)


# ── structural invariants (points 6/7) ────────────────────────────────
# Full integration tests of verify_payment/webhook would need mocked
# Razorpay HMAC signing and FastAPI Request scaffolding this repo has no
# infra for. Instead these lock in the two structural guarantees that
# make retries/failures safe, by inspecting the actual source — so a
# future edit that reorders these calls breaks a test instead of
# silently reopening the double-extension / activate-on-failure holes.

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

    webhook_src = inspect.getsource(payments_mod.razorpay_webhook)
    already_processed_idx = webhook_src.rindex('"already_processed"')  # the payment.captured one, not verify's
    grant_call_idx = webhook_src.index("grant_subscription_period(")
    assert grant_call_idx > already_processed_idx


def test_payment_failed_path_never_grants_a_subscription():
    import inspect
    import app.routers.payments as payments_mod

    webhook_src = inspect.getsource(payments_mod.razorpay_webhook)
    failed_branch_start = webhook_src.index('"payment.failed"')
    failed_branch_end = webhook_src.index("else:", failed_branch_start)
    failed_branch = webhook_src[failed_branch_start:failed_branch_end]
    assert "grant_subscription_period" not in failed_branch
    assert "process_payment_rpc" not in failed_branch


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
