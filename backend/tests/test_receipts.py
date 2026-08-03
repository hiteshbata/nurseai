"""
Regression check for the payment-receipt endpoints (backend/app/routers/payments.py):
list_receipts/download_receipt scope to the caller's own user_id, and
_build_receipt_pdf produces a real PDF. Same style as test_coupon_discount.py:
route/helper functions called directly with a mocked get_supabase, no live DB.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from app.routers import payments as payments_module  # noqa: E402
from app.routers.auth import UserInfo  # noqa: E402

USER = UserInfo(id="11111111-1111-1111-1111-111111111111", email="nurse@example.com")

PAYMENT_ROW = {
    "payment_id": "pay_test123",
    "order_id": "order_test123",
    "user_id": USER.id,
    "plan_id": "pro",
    "amount": 149900,
    "currency": "INR",
    "status": "paid",
    "created_at": "2026-08-01T12:00:00Z",
}


def _fake_supabase_for_list(rows):
    supabase = MagicMock()
    result = MagicMock()
    result.data = rows
    chain = supabase.table.return_value.select.return_value.eq.return_value.order.return_value
    chain.execute.return_value = result
    return supabase


def _fake_supabase_for_fetch(rows):
    supabase = MagicMock()
    result = MagicMock()
    result.data = rows
    chain = supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value
    chain.execute.return_value = result
    return supabase


class ListReceiptsTests(unittest.TestCase):
    def test_maps_row_to_plan_name_and_amount(self):
        with patch.object(payments_module, "get_supabase", return_value=_fake_supabase_for_list([PAYMENT_ROW])):
            receipts = payments_module.list_receipts(current_user=USER)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].payment_id, "pay_test123")
        self.assertEqual(receipts[0].plan_name, "Pro")
        self.assertEqual(receipts[0].amount, 149900)

    def test_empty_when_no_payments(self):
        with patch.object(payments_module, "get_supabase", return_value=_fake_supabase_for_list([])):
            receipts = payments_module.list_receipts(current_user=USER)
        self.assertEqual(receipts, [])


class DownloadReceiptTests(unittest.TestCase):
    def test_returns_pdf_for_own_payment(self):
        with patch.object(payments_module, "get_supabase", return_value=_fake_supabase_for_fetch([PAYMENT_ROW])):
            response = payments_module.download_receipt("pay_test123", current_user=USER)
        self.assertIsInstance(response, Response)
        self.assertEqual(response.media_type, "application/pdf")
        self.assertIn("receipt-pay_test123.pdf", response.headers["content-disposition"])
        self.assertTrue(response.body.startswith(b"%PDF"))

    def test_404_when_payment_not_found_or_not_owned(self):
        with patch.object(payments_module, "get_supabase", return_value=_fake_supabase_for_fetch([])):
            with self.assertRaises(HTTPException) as ctx:
                payments_module.download_receipt("pay_not_mine", current_user=USER)
        self.assertEqual(ctx.exception.status_code, 404)


class BuildReceiptPdfTests(unittest.TestCase):
    def test_produces_valid_pdf_bytes(self):
        pdf_bytes = payments_module._build_receipt_pdf(PAYMENT_ROW)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_no_gst_language_present(self):
        # SpeakOET isn't GST-registered -- the receipt must never claim to be
        # a GST invoice or print a GSTIN.
        pdf_bytes = payments_module._build_receipt_pdf(PAYMENT_ROW)
        self.assertNotIn(b"GSTIN", pdf_bytes)


if __name__ == "__main__":
    unittest.main()
