"""Billing-integrity tests: self-serve B2C plans are strictly upgrade-only
(Free < Basic < Pro < Elite). Covers:

  * app.core.plans.PLAN_RANK / is_strict_upgrade -- the single rank source.
  * payments.py's pre-payment gate (create_order / create_subscription):
    reject a non-upgrade before ever talking to Razorpay.
  * payments.py's post-payment defense-in-depth gate (verify_payment /
    verify_subscription_payment): reject a downgrade even if the frontend
    and the creation-time gate were both bypassed via a direct API call,
    while still tolerating the legitimate webhook-race "already recorded"
    case (see reject_if_downgrade's docstring).
  * The existing single-live-subscription guard (create_subscription),
    extended to create_order so an active recurring subscription can't
    coexist with a new one-time/annual purchase.

Same fake-Supabase-table convention as test_plans_me.py / test_subscription_
lifecycle.py -- no network, no live DB.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.core.plans import PLAN_RANK, is_strict_upgrade  # noqa: E402
from app.routers import payments as payments_mod  # noqa: E402
from app.routers.payments import (  # noqa: E402
    CreateOrderRequest,
    CreateSubscriptionRequest,
    VerifyPaymentRequest,
    VerifySubscriptionPaymentRequest,
)
from app.routers.auth import UserInfo  # noqa: E402

NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
FAR_FUTURE = (NOW + timedelta(days=300)).isoformat()


# ── Fakes (mirrors test_plans_me.py / test_subscription_lifecycle.py) ────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self._filters = {}

    def select(self, _cols):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def limit(self, _n):
        return self

    def update(self, values):
        self._pending_update = values
        return self

    def execute(self):
        if getattr(self, "_pending_update", None) is not None:
            for row in self.rows:
                if all(row.get(k) == v for k, v in self._filters.items()):
                    row.update(self._pending_update)
            self._pending_update = None
            return _FakeResult(None)
        out = [r for r in self.rows if all(r.get(k) == v for k, v in self._filters.items())]
        return _FakeResult(out)


class _FakeRpcCall:
    def __init__(self, recorder, name, params, response_data):
        self.recorder = recorder
        self.name = name
        self.params = params
        self.response_data = response_data

    def execute(self):
        self.recorder.append((self.name, self.params))
        return _FakeResult(self.response_data)


class _FakeSupabase:
    """table("user_profiles") / table("payments") backed by in-memory rows;
    rpc() records calls and returns canned "success" responses so a full
    legitimate-upgrade run can complete end to end."""

    def __init__(self, profiles=None, payments=None):
        self.tables = {"user_profiles": profiles or [], "payments": payments or []}
        self.rpc_calls = []

    def table(self, name):
        return _FakeTable(self.tables.get(name, []))

    def rpc(self, name, params):
        if name == "process_payment_and_grant":
            return _FakeRpcCall(self.rpc_calls, name, params, "ok")
        return _FakeRpcCall(self.rpc_calls, name, params, None)


def _profile(user_id, plan="free", **extra):
    row = {"user_id": user_id, "plan": plan, "plan_expires_at": None, "subscription_status": "none"}
    row.update(extra)
    return row


def _user(user_id):
    return UserInfo(id=user_id, email=f"{user_id}@example.com")


class _FakeUtility:
    def verify_payment_signature(self, _params):
        return True  # signature accepted -- signature verification itself isn't under test here


class _FakeOrderResource:
    def __init__(self, order):
        self._order = order

    def fetch(self, _order_id):
        return self._order

    def create(self, params):
        return {"id": "order_fake_1", "amount": params["amount"], "currency": params["currency"]}


class _FakeRazorpayClient:
    def __init__(self, order=None):
        self.utility = _FakeUtility()
        self.order = _FakeOrderResource(order)


# ── PLAN_RANK / is_strict_upgrade -- the rank source itself ─────────────

def test_plan_rank_order():
    assert PLAN_RANK == {"free": 0, "basic": 1, "pro": 2, "elite": 3}


@pytest.mark.parametrize("current,target", [
    ("free", "basic"), ("free", "pro"), ("free", "elite"),
    ("basic", "pro"), ("basic", "elite"),
    ("pro", "elite"),
])
def test_allowed_upgrades(current, target):
    assert is_strict_upgrade(current, target) is True


@pytest.mark.parametrize("current,target", [
    ("basic", "free"), ("pro", "free"), ("elite", "free"),
    ("pro", "basic"), ("elite", "basic"), ("elite", "pro"),
    ("free", "free"), ("basic", "basic"), ("pro", "pro"), ("elite", "elite"),
])
def test_disallowed_transitions(current, target):
    assert is_strict_upgrade(current, target) is False


# ── get_effective_current_plan: expiry-aware, not the raw column ────────

def test_effective_current_plan_uses_expiry_aware_self_serve_plan(monkeypatch):
    fake = _FakeSupabase(profiles=[_profile("u1", plan="pro", plan_expires_at=FAR_FUTURE)])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    assert payments_mod.get_effective_current_plan("u1") == "pro"


def test_effective_current_plan_collapses_lapsed_paid_plan_to_free(monkeypatch):
    lapsed = (NOW - timedelta(days=30)).isoformat()
    fake = _FakeSupabase(profiles=[_profile("u1", plan="pro", plan_expires_at=lapsed)])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    assert payments_mod.get_effective_current_plan("u1") == "free"


# ── ensure_new_purchase_is_upgrade: the pre-payment gate ─────────────────

def test_ensure_new_purchase_is_upgrade_allows_free_to_paid(monkeypatch):
    fake = _FakeSupabase(profiles=[_profile("u1", plan="free")])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    payments_mod.ensure_new_purchase_is_upgrade("u1", "basic")  # must not raise


@pytest.mark.parametrize("current,target", [("pro", "basic"), ("elite", "basic"), ("elite", "pro")])
def test_ensure_new_purchase_is_upgrade_blocks_downgrade(monkeypatch, current, target):
    fake = _FakeSupabase(profiles=[_profile("u1", plan=current, plan_expires_at=FAR_FUTURE)])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    with pytest.raises(HTTPException) as exc_info:
        payments_mod.ensure_new_purchase_is_upgrade("u1", target)
    assert exc_info.value.status_code == 400


# ── reject_if_downgrade: the post-payment defense-in-depth gate ─────────

@pytest.mark.parametrize("current,target", [("pro", "basic"), ("elite", "basic"), ("elite", "pro")])
def test_reject_if_downgrade_blocks_true_downgrade(current, target):
    with pytest.raises(HTTPException) as exc_info:
        payments_mod.reject_if_downgrade(current, target, context="test", user_id="u1")
    assert exc_info.value.status_code == 400


@pytest.mark.parametrize("current,target", [("free", "basic"), ("basic", "pro"), ("pro", "elite")])
def test_reject_if_downgrade_allows_upgrade(current, target):
    payments_mod.reject_if_downgrade(current, target, context="test", user_id="u1")  # must not raise


def test_reject_if_downgrade_allows_equal_rank_for_webhook_race_tolerance():
    # Deliberately NOT rejected here -- reject_if_downgrade is only ever
    # reached (see payment_already_recorded's docstring) for a genuinely
    # new payment, where creation-time already enforced the strict
    # upgrade rule; allowing equal rank through means a webhook that
    # legitimately finished granting the same target plan a moment before
    # this call can't be misread as an invalid transition.
    payments_mod.reject_if_downgrade("pro", "pro", context="test", user_id="u1")


# ── payment_already_recorded ─────────────────────────────────────────────

def test_payment_already_recorded_true_when_row_exists(monkeypatch):
    fake = _FakeSupabase(payments=[{"id": 1, "payment_id": "pay_1"}])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    assert payments_mod.payment_already_recorded("pay_1") is True


def test_payment_already_recorded_false_when_no_row(monkeypatch):
    fake = _FakeSupabase(payments=[])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    assert payments_mod.payment_already_recorded("pay_1") is False


# ── get_active_recurring_subscription_id ─────────────────────────────────

def test_active_recurring_subscription_detected(monkeypatch):
    fake = _FakeSupabase(profiles=[_profile(
        "u1", plan="basic", razorpay_subscription_id="sub_1", auto_renew_enabled=True,
    )])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    assert payments_mod.get_active_recurring_subscription_id("u1") == "sub_1"


def test_no_active_recurring_subscription_when_cancelled(monkeypatch):
    fake = _FakeSupabase(profiles=[_profile(
        "u1", plan="basic", razorpay_subscription_id="sub_1", auto_renew_enabled=False,
    )])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    assert payments_mod.get_active_recurring_subscription_id("u1") is None


# ── create_order: pre-payment gate + active-subscription conflict ───────

def test_create_order_blocks_downgrade_before_touching_razorpay(monkeypatch):
    fake = _FakeSupabase(profiles=[_profile("u-pro", plan="pro", plan_expires_at=FAR_FUTURE)])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)

    def _boom():
        raise AssertionError("must not reach Razorpay for a rejected downgrade")
    monkeypatch.setattr(payments_mod, "get_razorpay_client", _boom)

    with pytest.raises(HTTPException) as exc_info:
        payments_mod.create_order(CreateOrderRequest(plan_id="basic"), current_user=_user("u-pro"))
    assert exc_info.value.status_code == 400


def test_create_order_allows_legitimate_upgrade(monkeypatch):
    fake = _FakeSupabase(profiles=[_profile("u-free", plan="free")])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    monkeypatch.setattr(payments_mod, "get_razorpay_client", lambda: _FakeRazorpayClient())

    res = payments_mod.create_order(CreateOrderRequest(plan_id="basic"), current_user=_user("u-free"))
    assert res.order_id == "order_fake_1"


def test_create_order_blocks_when_active_recurring_subscription_exists(monkeypatch):
    # Basic, actively auto-renewing -- an annual/order purchase (even a
    # legitimate-looking upgrade to Pro) must be refused until the existing
    # subscription is cancelled, or the old subscription's next charge can
    # silently overwrite whatever this order just granted.
    fake = _FakeSupabase(profiles=[_profile(
        "u-basic", plan="basic", plan_expires_at=FAR_FUTURE,
        razorpay_subscription_id="sub_1", auto_renew_enabled=True,
    )])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)

    with pytest.raises(HTTPException) as exc_info:
        payments_mod.create_order(CreateOrderRequest(plan_id="pro"), current_user=_user("u-basic"))
    assert exc_info.value.status_code == 400


# ── create_subscription: pre-payment gate + existing single-sub guard ───

@pytest.mark.parametrize("current,target", [("pro", "basic"), ("elite", "basic"), ("elite", "pro")])
def test_create_subscription_blocks_downgrade_before_touching_razorpay(monkeypatch, current, target):
    fake = _FakeSupabase(profiles=[_profile("u1", plan=current, plan_expires_at=FAR_FUTURE)])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)

    def _boom(_plan_id):
        raise AssertionError("must not reach Razorpay plan lookup for a rejected downgrade")
    monkeypatch.setattr(payments_mod, "get_razorpay_plan_id", _boom)

    with pytest.raises(HTTPException) as exc_info:
        payments_mod.create_subscription(CreateSubscriptionRequest(plan_id=target), current_user=_user("u1"))
    assert exc_info.value.status_code == 400


def test_create_subscription_still_blocks_second_active_subscription(monkeypatch):
    # Pre-existing guard, unchanged behavior -- a legitimate upgrade target
    # (basic -> pro) is still refused while an active subscription exists,
    # same as before this change.
    fake = _FakeSupabase(profiles=[_profile(
        "u1", plan="basic", plan_expires_at=FAR_FUTURE,
        razorpay_subscription_id="sub_1", auto_renew_enabled=True,
    )])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    monkeypatch.setattr(payments_mod, "get_razorpay_plan_id", lambda plan_id: f"rzp_{plan_id}")

    with pytest.raises(HTTPException) as exc_info:
        payments_mod.create_subscription(CreateSubscriptionRequest(plan_id="pro"), current_user=_user("u1"))
    assert exc_info.value.status_code == 400
    assert "cancel" in exc_info.value.detail.lower()


# ── verify_payment: direct-API-bypass defense-in-depth ───────────────────

def _order_notes(user_id, plan_id, amount=29900):
    return {"notes": {"plan_id": plan_id, "user_id": user_id}, "amount": amount}


@pytest.mark.parametrize("current,target", [("pro", "basic"), ("elite", "basic"), ("elite", "pro")])
def test_verify_payment_rejects_direct_api_downgrade_bypass(monkeypatch, current, target):
    user_id = f"u-{current}"
    fake = _FakeSupabase(profiles=[_profile(user_id, plan=current, plan_expires_at=FAR_FUTURE)])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    order = _order_notes(user_id, target)
    monkeypatch.setattr(payments_mod, "get_razorpay_client", lambda: _FakeRazorpayClient(order=order))

    req = VerifyPaymentRequest(
        razorpay_order_id="order_1", razorpay_payment_id="pay_1", razorpay_signature="sig",
    )
    with pytest.raises(HTTPException) as exc_info:
        payments_mod.verify_payment(req, current_user=_user(user_id))
    assert exc_info.value.status_code == 400
    # must not have granted anything
    assert fake.rpc_calls == []


def test_verify_payment_allows_legitimate_upgrade_end_to_end(monkeypatch):
    user_id = "u-free"
    fake = _FakeSupabase(profiles=[_profile(user_id, plan="free")])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    order = _order_notes(user_id, "basic", amount=payments_mod.PLAN_PRICE_PAISE["basic"])
    monkeypatch.setattr(payments_mod, "get_razorpay_client", lambda: _FakeRazorpayClient(order=order))

    req = VerifyPaymentRequest(
        razorpay_order_id="order_1", razorpay_payment_id="pay_1", razorpay_signature="sig",
    )
    res = payments_mod.verify_payment(req, current_user=_user(user_id))
    assert res.success is True
    rpc_names = [name for name, _ in fake.rpc_calls]
    # Single atomic call, not two separate process_payment /
    # grant_subscription_period round trips -- see billing audit issue 2.
    assert rpc_names.count("process_payment_and_grant") == 1


def test_verify_payment_tolerates_already_recorded_webhook_race(monkeypatch):
    # The webhook already fully processed this exact payment_id (races
    # ahead of the client's own verify call) -- current effective plan
    # already equals the target. Must NOT be rejected as a "downgrade".
    user_id = "u-pro"
    fake = _FakeSupabase(
        profiles=[_profile(user_id, plan="pro", plan_expires_at=FAR_FUTURE)],
        payments=[{"id": 1, "payment_id": "pay_1"}],
    )
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    order = _order_notes(user_id, "pro", amount=payments_mod.PLAN_PRICE_PAISE["pro"])
    monkeypatch.setattr(payments_mod, "get_razorpay_client", lambda: _FakeRazorpayClient(order=order))

    req = VerifyPaymentRequest(
        razorpay_order_id="order_1", razorpay_payment_id="pay_1", razorpay_signature="sig",
    )
    res = payments_mod.verify_payment(req, current_user=_user(user_id))
    assert res.success is True


# ── verify_subscription_payment: direct-API-bypass defense-in-depth ─────

def _subscription_and_payment(user_id, plan_id, amount=29900):
    subscription = {"notes": {"plan_id": plan_id, "user_id": user_id}, "id": "sub_1", "paid_count": 2}
    payment = {"amount": amount, "order_id": None}
    return subscription, payment


class _FakeSubscriptionResource:
    def __init__(self, subscription):
        self._subscription = subscription

    def fetch(self, _subscription_id):
        return self._subscription


class _FakePaymentResource:
    def __init__(self, payment):
        self._payment = payment

    def fetch(self, _payment_id):
        return self._payment


class _FakePlanResource:
    def __init__(self, amount):
        self._amount = amount

    def fetch(self, _plan_id):
        return {"item": {"amount": self._amount}}


class _FakeSubscriptionRazorpayClient:
    def __init__(self, subscription, payment, plan_amount):
        self.subscription = _FakeSubscriptionResource(subscription)
        self.payment = _FakePaymentResource(payment)
        self.plan = _FakePlanResource(plan_amount)


@pytest.mark.parametrize("current,target", [("pro", "basic"), ("elite", "basic"), ("elite", "pro")])
def test_verify_subscription_payment_rejects_direct_api_downgrade_bypass(monkeypatch, current, target):
    user_id = f"u-{current}"
    fake = _FakeSupabase(profiles=[_profile(user_id, plan=current, plan_expires_at=FAR_FUTURE)])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    monkeypatch.setattr(payments_mod, "verify_subscription_payment_signature", lambda *a, **k: True)
    subscription, payment = _subscription_and_payment(user_id, target, amount=99900)
    monkeypatch.setattr(
        payments_mod, "get_razorpay_client",
        lambda: _FakeSubscriptionRazorpayClient(subscription, payment, plan_amount=99900),
    )

    req = VerifySubscriptionPaymentRequest(
        razorpay_payment_id="pay_1", razorpay_subscription_id="sub_1", razorpay_signature="sig",
    )
    with pytest.raises(HTTPException) as exc_info:
        payments_mod.verify_subscription_payment(req, current_user=_user(user_id))
    assert exc_info.value.status_code == 400
    assert fake.rpc_calls == []


def test_verify_subscription_payment_allows_legitimate_upgrade_end_to_end(monkeypatch):
    user_id = "u-basic"
    fake = _FakeSupabase(profiles=[_profile(user_id, plan="basic", plan_expires_at=FAR_FUTURE)])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    monkeypatch.setattr(payments_mod, "verify_subscription_payment_signature", lambda *a, **k: True)
    subscription, payment = _subscription_and_payment(user_id, "pro", amount=79900)
    monkeypatch.setattr(
        payments_mod, "get_razorpay_client",
        lambda: _FakeSubscriptionRazorpayClient(subscription, payment, plan_amount=79900),
    )

    req = VerifySubscriptionPaymentRequest(
        razorpay_payment_id="pay_1", razorpay_subscription_id="sub_1", razorpay_signature="sig",
    )
    res = payments_mod.verify_subscription_payment(req, current_user=_user(user_id))
    assert res.success is True


# ── Institution cases: B2C plan-rank comparison ignores institution grants ──
# (Full effective_access/institution reconciliation is covered in
# test_plans_me.py -- these confirm payments.py's own gates use the same
# self_serve_plan-only rule, never an institution-inflated one.)

def test_institution_student_with_b2c_free_can_purchase_any_paid_plan(monkeypatch):
    fake = _FakeSupabase(profiles=[_profile("u1", plan="free")])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    for target in ("basic", "pro", "elite"):
        payments_mod.ensure_new_purchase_is_upgrade("u1", target)  # must not raise


@pytest.mark.parametrize("current,blocked_target", [("pro", "basic"), ("elite", "basic"), ("elite", "pro")])
def test_institution_student_with_b2c_paid_plan_cannot_downgrade(monkeypatch, current, blocked_target):
    # institution_access/module grants are never read here -- the gate only
    # ever looks at user_profiles.plan, so an institution's Speaking-only
    # (or full S/R/L/W) grant cannot change this outcome either way.
    fake = _FakeSupabase(profiles=[_profile("u1", plan=current, plan_expires_at=FAR_FUTURE)])
    monkeypatch.setattr(payments_mod, "get_supabase", lambda: fake)
    with pytest.raises(HTTPException):
        payments_mod.ensure_new_purchase_is_upgrade("u1", blocked_target)


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
