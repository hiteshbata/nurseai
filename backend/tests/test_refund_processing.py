"""
Money-path checks for the refund system (payments._process_refund +
admin.admin_refund_payment). No network -- fakes stand in for Supabase and
Razorpay, same style as test_subscription_amount_check.py.

Covers exactly the two things a refund handler must never get wrong:
1. A duplicate refund.created delivery (Razorpay retries, or the webhook
   racing an admin-initiated refund for the same refund id) must not
   double-downgrade the user or write a second audit-log entry.
2. The admin endpoint must only call _process_refund -- which downgrades
   the plan -- after Razorpay's refund API call actually succeeds, never
   on a failed/raised call.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.auth import UserInfo


class Result:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """Chainable stand-in for a postgrest QueryBuilder. Records every call
    so tests can assert on what was written, and returns whatever the test
    queued up for that table via `results`."""

    def __init__(self, table_name, calls, results):
        self.table_name = table_name
        self.calls = calls
        self.results = results

    def select(self, *a, **kw):
        return self

    def eq(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        return self

    def update(self, payload):
        self.calls.append((self.table_name, "update", payload))
        return self

    def insert(self, payload):
        self.calls.append((self.table_name, "insert", payload))
        return self

    def upsert(self, payload, **kw):
        self.calls.append((self.table_name, "upsert", payload))
        return self

    def execute(self):
        queue = self.results.get(self.table_name, [])
        # Each table's queued results are consumed in order; last one repeats.
        data = queue.pop(0) if len(queue) > 1 else (queue[0] if queue else [])
        return Result(data)


class FakeSupabase:
    def __init__(self, results):
        self.calls = []
        self.results = results

    def table(self, name):
        return FakeQuery(name, self.calls, self.results)

    def rpc(self, *a, **kw):
        raise AssertionError("refund path must not call any RPC")


def test_duplicate_refund_is_idempotent(monkeypatch):
    import app.routers.payments as payments

    fake = FakeSupabase({
        "payments": [[{"user_id": "u1", "plan_id": "pro"}]],
        # First upsert call "wins" the insert; second sees the unique
        # constraint conflict and ignore_duplicates gives back no rows.
        "refunds": [[{"id": 1}], []],
        # Same table backs both get_current_plan's "plan" lookup and the
        # subscription-id lookup below -- the fake ignores .select() column
        # args, so one row needs both fields present.
        "user_profiles": [[{"plan": "pro", "razorpay_subscription_id": None}]],
        "audit_log": [[{"id": "a1"}]],
    })
    monkeypatch.setattr(payments, "get_supabase", lambda: fake)

    first = payments._process_refund(
        razorpay_refund_id="rfnd_1", payment_id="pay_1", amount=49900,
        reason="test", initiated_by="webhook",
    )
    second = payments._process_refund(
        razorpay_refund_id="rfnd_1", payment_id="pay_1", amount=49900,
        reason="test", initiated_by="webhook",
    )

    assert first == {"success": True, "downgraded": True}
    assert second == {"success": True, "already_processed": True}

    user_profile_updates = [c for c in fake.calls if c[0] == "user_profiles" and c[1] == "update"]
    audit_inserts = [c for c in fake.calls if c[0] == "audit_log" and c[1] == "insert"]
    assert len(user_profile_updates) == 1, "duplicate delivery must not downgrade the user twice"
    assert len(audit_inserts) == 1, "duplicate delivery must not double-log the refund"


def test_admin_refund_skipped_when_razorpay_call_fails(monkeypatch):
    import app.routers.admin as admin
    from fastapi import HTTPException

    fake = FakeSupabase({"payments": [[{"amount": 49900, "currency": "INR"}]]})
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)

    class FailingPaymentResource:
        def refund(self, payment_id, data):
            raise RuntimeError("razorpay down")

    class FailingClient:
        payment = FailingPaymentResource()

    monkeypatch.setattr(admin, "get_razorpay_client", lambda: FailingClient())

    calls = []
    monkeypatch.setattr(admin, "_process_refund", lambda **kw: calls.append(kw))

    admin_user = UserInfo(id="admin_1", email="admin@nurseai.test")
    req = admin.RefundRequest(reason="customer requested")

    try:
        admin.admin_refund_payment("pay_1", req, admin_user)
        assert False, "expected HTTPException on Razorpay failure"
    except HTTPException as e:
        assert e.status_code == 500

    assert calls == [], "_process_refund must never run when the Razorpay refund call itself failed"


def test_admin_refund_runs_only_after_razorpay_confirms(monkeypatch):
    import app.routers.admin as admin

    fake = FakeSupabase({"payments": [[{"amount": 49900, "currency": "INR"}]]})
    monkeypatch.setattr(admin, "get_supabase", lambda: fake)

    class OkPaymentResource:
        def refund(self, payment_id, data):
            assert payment_id == "pay_1"
            return {"id": "rfnd_99", "amount": data["amount"]}

    class OkClient:
        payment = OkPaymentResource()

    monkeypatch.setattr(admin, "get_razorpay_client", lambda: OkClient())

    calls = []
    monkeypatch.setattr(
        admin, "_process_refund",
        lambda **kw: calls.append(kw) or {"success": True, "downgraded": True},
    )

    admin_user = UserInfo(id="admin_1", email="admin@nurseai.test")
    req = admin.RefundRequest(reason="customer requested")

    result = admin.admin_refund_payment("pay_1", req, admin_user)

    assert result["razorpay_refund_id"] == "rfnd_99"
    assert len(calls) == 1
    assert calls[0]["razorpay_refund_id"] == "rfnd_99"
    assert calls[0]["payment_id"] == "pay_1"
    assert calls[0]["amount"] == 49900
    assert calls[0]["initiated_by"] == "admin"
    assert calls[0]["admin"] is admin_user


if __name__ == "__main__":
    class _Ctx:
        """Minimal stand-in so these run with plain `python` too, not just
        pytest (pytest supplies `monkeypatch` as a fixture)."""
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, value):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            for obj, name, value in reversed(self._undo):
                setattr(obj, name, value)

    for fn in (
        test_duplicate_refund_is_idempotent,
        test_admin_refund_skipped_when_razorpay_call_fails,
        test_admin_refund_runs_only_after_razorpay_confirms,
    ):
        ctx = _Ctx()
        try:
            fn(ctx)
        finally:
            ctx.undo()
        print(f"ok  {fn.__name__}")
