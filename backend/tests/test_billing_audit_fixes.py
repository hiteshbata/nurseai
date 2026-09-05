"""Regression tests for the two billing-audit HIGH findings (2026-09-05):

  1. Stale subscription.charged webhooks (an old, superseded subscription's
     last cycle-end charge) must never overwrite a newer plan --
     is_subscription_webhook_stale.
  2. process_payment + grant_subscription_period must be one atomic
     Postgres transaction, not two independent RPC calls --
     process_payment_and_grant_rpc / process_payment_and_grant (see
     supabase/migrations/20260905000000_atomic_payment_grant.sql).

Same fake-Supabase / fake-Razorpay convention as test_plan_upgrade_only.py /
test_subscription_lifecycle.py -- no network, no live DB. The actual
transactional rollback guarantee for issue 2 lives in Postgres (a single
plpgsql function invocation, including nested function calls, is one
atomic unit unless a nested BEGIN/EXCEPTION block says otherwise -- see
the migration file's comments) and can't be exercised by a Python-side
fake; what's tested here is the call *contract* Python relies on: exactly
one RPC call carrying both the payment and the grant, with previous_plan
threaded through correctly, and no separate grant_subscription_period
fallback/revert path left in the payment call sites.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import app.routers.payments as payments_mod  # noqa: E402
from app.core.plans import PLAN_PERIOD_DAYS, GRACE_PERIOD_DAYS  # noqa: E402

NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ── fakes ──────────────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeProfileTable:
    """table("user_profiles").select(...).eq("user_id", ...).execute()"""

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


class _FakeSupabaseForStaleness:
    def __init__(self, profiles=None):
        self.profiles = profiles or {}

    def table(self, name):
        assert name == "user_profiles"
        return _FakeProfileTable(self.profiles)


class _FakeSubscriptionResource:
    def __init__(self, subscription=None, error=None):
        self._subscription = subscription
        self._error = error

    def fetch(self, _subscription_id):
        if self._error:
            raise self._error
        return self._subscription


class _FakeRazorpayClient:
    def __init__(self, subscription=None, error=None):
        self.subscription = _FakeSubscriptionResource(subscription, error)


class _AlertRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


# ── is_subscription_webhook_stale: the stale-webhook guard (issue 1) ────

def test_no_stored_subscription_is_never_stale(monkeypatch):
    # Brand-new subscriber, nothing on record yet -- e.g. Race B, the very
    # first charge for a brand-new subscription arriving before
    # /verify-subscription-payment has written anything.
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: _FakeSupabaseForStaleness())
    assert payments_mod.is_subscription_webhook_stale("u1", "sub_new", 1700000000) is False


def test_same_subscription_id_is_never_stale(monkeypatch):
    # The current subscription's own renewal (or its own first charge,
    # already recorded) -- trivially not stale.
    monkeypatch.setattr(
        payments_mod, "get_supabase",
        lambda: _FakeSupabaseForStaleness({"u1": {"razorpay_subscription_id": "sub_current"}}),
    )
    assert payments_mod.is_subscription_webhook_stale("u1", "sub_current", 1700000000) is False


def test_older_subscription_webhook_after_upgrade_is_stale(monkeypatch):
    # Race A: user upgraded Basic -> Pro, user_profiles now points at the
    # NEW (Pro) subscription, created AFTER the old Basic one. The old
    # Basic subscription's late cycle-end charge must be rejected.
    monkeypatch.setattr(
        payments_mod, "get_supabase",
        lambda: _FakeSupabaseForStaleness({"u1": {"razorpay_subscription_id": "sub_pro_new"}}),
    )
    monkeypatch.setattr(
        payments_mod, "get_razorpay_client",
        lambda: _FakeRazorpayClient(subscription={"id": "sub_pro_new", "created_at": 1700001000}),
    )
    is_stale = payments_mod.is_subscription_webhook_stale(
        "u1", "sub_basic_old", subscription_created_at=1700000000,  # older than stored (1700001000)
    )
    assert is_stale is True


def test_newer_subscription_webhook_before_verify_write_is_not_stale(monkeypatch):
    # Race B: the NEW subscription's first charge arrives before the
    # client's /verify-subscription-payment call has overwritten
    # razorpay_subscription_id -- user_profiles still shows the OLD
    # subscription (cancel_subscription never clears the id, only flips
    # auto_renew_enabled). The new subscription is created AFTER the
    # stored one, so it must be accepted, not rejected as a mismatch.
    monkeypatch.setattr(
        payments_mod, "get_supabase",
        lambda: _FakeSupabaseForStaleness({"u1": {"razorpay_subscription_id": "sub_basic_old"}}),
    )
    monkeypatch.setattr(
        payments_mod, "get_razorpay_client",
        lambda: _FakeRazorpayClient(subscription={"id": "sub_basic_old", "created_at": 1700000000}),
    )
    is_stale = payments_mod.is_subscription_webhook_stale(
        "u1", "sub_pro_new", subscription_created_at=1700001000,  # newer than stored (1700000000)
    )
    assert is_stale is False


def test_missing_created_at_fails_open_and_alerts(monkeypatch):
    monkeypatch.setattr(
        payments_mod, "get_supabase",
        lambda: _FakeSupabaseForStaleness({"u1": {"razorpay_subscription_id": "sub_other"}}),
    )
    alert = _AlertRecorder()
    monkeypatch.setattr(payments_mod, "send_alert", alert)

    is_stale = payments_mod.is_subscription_webhook_stale("u1", "sub_incoming", subscription_created_at=None)

    assert is_stale is False
    assert len(alert.calls) == 1


def test_razorpay_fetch_failure_fails_open_and_alerts(monkeypatch):
    monkeypatch.setattr(
        payments_mod, "get_supabase",
        lambda: _FakeSupabaseForStaleness({"u1": {"razorpay_subscription_id": "sub_other"}}),
    )
    monkeypatch.setattr(
        payments_mod, "get_razorpay_client",
        lambda: _FakeRazorpayClient(error=RuntimeError("simulated Razorpay outage")),
    )
    alert = _AlertRecorder()
    monkeypatch.setattr(payments_mod, "send_alert", alert)

    is_stale = payments_mod.is_subscription_webhook_stale("u1", "sub_incoming", subscription_created_at=1700000000)

    assert is_stale is False
    assert len(alert.calls) == 1


def test_stale_check_runs_before_finalize_in_subscription_charged_branch():
    # Structural guard: the stale check must gate _finalize_payment, not
    # run after it (or a stale webhook would already have overwritten the
    # plan before ever being rejected).
    import inspect

    webhook_src = inspect.getsource(payments_mod._process_webhook_body)
    branch_start = webhook_src.index('"subscription.charged"')
    stale_check_idx = webhook_src.index("is_subscription_webhook_stale(", branch_start)
    finalize_idx = webhook_src.index("_finalize_payment(", branch_start)
    assert branch_start < stale_check_idx < finalize_idx


# ── process_payment_and_grant_rpc: the atomic call contract (issue 2) ───

class _FakeRpcCall:
    def __init__(self, recorder, name, params, response_data, error=None):
        self.recorder = recorder
        self.name = name
        self.params = params
        self.response_data = response_data
        self.error = error

    def execute(self):
        self.recorder.append((self.name, self.params))
        if self.error:
            raise self.error
        return _FakeResult(self.response_data)


class _FakeRpcSupabase:
    def __init__(self, response_data="ok", error=None):
        self.response_data = response_data
        self.error = error
        self.rpc_calls = []

    def rpc(self, name, params):
        return _FakeRpcCall(self.rpc_calls, name, params, self.response_data, self.error)


def test_process_payment_and_grant_rpc_is_a_single_call_with_full_params(monkeypatch):
    fake = _FakeRpcSupabase(response_data="ok")
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)

    result = payments_mod.process_payment_and_grant_rpc(
        user_id="u1",
        order_id="order_1",
        payment_id="pay_1",
        plan_id="pro",
        amount=79900,
        profile_plan="pro",
        previous_plan="basic",
        period_days=PLAN_PERIOD_DAYS,
    )

    assert result == "ok"
    assert len(fake.rpc_calls) == 1  # scenario 8: one call does both the payment record and the grant
    name, params = fake.rpc_calls[0]
    assert name == "process_payment_and_grant"
    assert params["p_user_id"] == "u1"
    assert params["p_payment_id"] == "pay_1"
    assert params["p_profile_plan"] == "pro"
    assert params["p_previous_plan"] == "basic"  # threaded through, not re-derived post-overwrite
    assert params["p_period_days"] == PLAN_PERIOD_DAYS
    assert params["p_grace_days"] == GRACE_PERIOD_DAYS


def test_process_payment_and_grant_rpc_already_processed_is_idempotent(monkeypatch):
    # scenarios 11/12/13: a retry (webhook-after-verify, verify-after-webhook,
    # or a plain duplicate delivery) must come back "already_processed" from
    # the single call, with nothing left for the caller to redo.
    fake = _FakeRpcSupabase(response_data="already_processed")
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)

    result = payments_mod.process_payment_and_grant_rpc(
        user_id="u1", order_id="order_1", payment_id="pay_1", plan_id="pro",
        amount=79900, profile_plan="pro", previous_plan="basic",
    )

    assert result == "already_processed"
    assert len(fake.rpc_calls) == 1


def test_process_payment_and_grant_rpc_failure_propagates_without_partial_python_state(monkeypatch):
    # scenarios 9/10: if the underlying transaction fails (payment insert
    # rolled back along with the grant, per the migration), the Python
    # wrapper must not paper over it with a separate revert/compensating
    # write -- it just re-raises, so a retry (client re-verify, or
    # Razorpay's webhook retry-on-non-2xx) safely redoes the whole thing
    # against a clean state.
    fake = _FakeRpcSupabase(error=RuntimeError("simulated DB failure"))
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)

    with pytest.raises(RuntimeError):
        payments_mod.process_payment_and_grant_rpc(
            user_id="u1", order_id="order_1", payment_id="pay_1", plan_id="pro",
            amount=79900, profile_plan="pro", previous_plan="basic",
        )

    assert len(fake.rpc_calls) == 1  # exactly one attempt -- no compensating second call


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
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
