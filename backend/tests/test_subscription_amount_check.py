"""
Regression check for get_subscription_expected_amount_paise: recurring
subscription charges must be validated against the price locked on the
Razorpay Plan tied to the subscription, not the current PLAN_PRICE_PAISE
config -- otherwise a price change breaks renewals for every existing
subscriber forever. No network -- a fake client stands in for
razorpay.Client.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.payments import get_subscription_expected_amount_paise


class FakePlanResource:
    def __init__(self, amount_by_plan_id):
        self.amount_by_plan_id = amount_by_plan_id
        self.fetched_plan_id = None

    def fetch(self, plan_id):
        self.fetched_plan_id = plan_id
        return {"item": {"amount": self.amount_by_plan_id[plan_id]}}


class FakeClient:
    def __init__(self, amount_by_plan_id):
        self.plan = FakePlanResource(amount_by_plan_id)


def test_uses_subscriptions_own_plan_amount_not_live_config():
    # Old Razorpay Plan the subscriber is locked into, priced before a
    # hypothetical price increase that only touched PLAN_PRICE_PAISE.
    client = FakeClient({"plan_old_499": 49900})
    subscription = {"id": "sub_123", "plan_id": "plan_old_499"}

    assert get_subscription_expected_amount_paise(client, subscription) == 49900
    assert client.plan.fetched_plan_id == "plan_old_499"


if __name__ == "__main__":
    test_uses_subscriptions_own_plan_amount_not_live_config()
    print("ok")
