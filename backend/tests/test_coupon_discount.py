"""
Regression check for apply_coupon (backend/app/routers/payments.py):
percent/flat_paise discount math, and the invalid/expired/exhausted
rejection paths that guard the one-off order checkout from a bad or
abused coupon. Same style as test_rbac.py: route/helper functions called
directly with a mocked get_supabase, no live DB.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from app.routers import payments as payments_module  # noqa: E402


def _fake_supabase(coupon: dict | None):
    supabase = MagicMock()
    result = MagicMock()
    result.data = [coupon] if coupon is not None else []
    supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = result
    return supabase


def _coupon(**overrides):
    base = {
        "code": "SAVE20",
        "discount_type": "percent",
        "discount_value": 20,
        "max_redemptions": None,
        "times_redeemed": 0,
        "active": True,
        "expires_at": None,
    }
    base.update(overrides)
    return base


class ApplyCouponTests(unittest.TestCase):
    def _apply(self, coupon, base_amount):
        with patch.object(payments_module, "get_supabase", return_value=_fake_supabase(coupon)):
            return payments_module.apply_coupon("save20", base_amount)

    def test_percent_discount(self):
        _, amount = self._apply(_coupon(discount_type="percent", discount_value=20), 79900)
        self.assertEqual(amount, 63920)  # 79900 * 0.8

    def test_flat_discount(self):
        _, amount = self._apply(_coupon(discount_type="flat_paise", discount_value=10000), 79900)
        self.assertEqual(amount, 69900)

    def test_flat_discount_floors_at_minimum_amount(self):
        _, amount = self._apply(_coupon(discount_type="flat_paise", discount_value=100000), 79900)
        self.assertEqual(amount, payments_module.RAZORPAY_MIN_AMOUNT_PAISE)

    def test_unknown_code_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self._apply(None, 79900)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_inactive_coupon_rejected(self):
        with self.assertRaises(HTTPException):
            self._apply(_coupon(active=False), 79900)

    def test_expired_coupon_rejected(self):
        expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with self.assertRaises(HTTPException):
            self._apply(_coupon(expires_at=expired), 79900)

    def test_exhausted_redemptions_rejected(self):
        with self.assertRaises(HTTPException):
            self._apply(_coupon(max_redemptions=5, times_redeemed=5), 79900)

    def test_under_redemption_cap_allowed(self):
        _, amount = self._apply(_coupon(max_redemptions=5, times_redeemed=4), 79900)
        self.assertEqual(amount, 63920)


class SubscriptionChargeIsCouponTrustedTests(unittest.TestCase):
    """subscription_charge_is_coupon_trusted: the recurring-billing analog
    of apply_coupon -- Razorpay's own Offer engine sets the first-cycle
    discounted amount (dashboard-only, no API to recompute it from our
    side), so callers skip the Plan-price equality check for exactly one
    cycle and trust Razorpay's charge instead. Getting this wrong either
    lets a discount silently repeat every renewal (revenue loss) or
    wrongly rejects a legitimate first payment (refuses to grant a plan
    someone paid for)."""

    def test_first_cycle_with_coupon_is_trusted(self):
        self.assertTrue(
            payments_module.subscription_charge_is_coupon_trusted("SAVE20", {"paid_count": 1})
        )

    def test_renewal_with_coupon_is_not_trusted(self):
        self.assertFalse(
            payments_module.subscription_charge_is_coupon_trusted("SAVE20", {"paid_count": 2})
        )

    def test_first_cycle_without_coupon_is_not_trusted(self):
        self.assertFalse(
            payments_module.subscription_charge_is_coupon_trusted(None, {"paid_count": 1})
        )

    def test_missing_paid_count_is_not_trusted(self):
        self.assertFalse(
            payments_module.subscription_charge_is_coupon_trusted("SAVE20", {})
        )


if __name__ == "__main__":
    unittest.main()
