"""
Tests for the reminder-email dedup logic (app.services.reminders).

Pure unit tests -- no Supabase, no network, no email actually sent. The
one thing that matters here: never re-email someone for the same event,
never silently skip a real one. Same style as test_founder_metrics.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.reminders import (
    rows_due_for_expiry_reminder,
    rows_due_for_failed_payment_reminder,
)


# ── rows_due_for_expiry_reminder ─────────────────────────────────────

def test_never_reminded_is_due():
    rows = [{"user_id": "u1", "plan_expires_at": "2026-08-01T00:00:00Z", "expiry_reminder_sent_for": None}]
    assert rows_due_for_expiry_reminder(rows) == rows


def test_already_reminded_for_same_expiry_is_skipped():
    rows = [{"user_id": "u1", "plan_expires_at": "2026-08-01T00:00:00Z", "expiry_reminder_sent_for": "2026-08-01T00:00:00Z"}]
    assert rows_due_for_expiry_reminder(rows) == []


def test_renewal_pushing_expiry_forward_is_due_again():
    # Reminded for the OLD expiry timestamp; plan_expires_at has since moved
    # (a renewal or admin grant) -- this is a new cycle, must remind again.
    rows = [{"user_id": "u1", "plan_expires_at": "2026-09-01T00:00:00Z", "expiry_reminder_sent_for": "2026-08-01T00:00:00Z"}]
    assert rows_due_for_expiry_reminder(rows) == rows


def test_expiry_mixed_batch_filters_correctly():
    rows = [
        {"user_id": "u1", "plan_expires_at": "2026-08-01T00:00:00Z", "expiry_reminder_sent_for": None},
        {"user_id": "u2", "plan_expires_at": "2026-08-01T00:00:00Z", "expiry_reminder_sent_for": "2026-08-01T00:00:00Z"},
        {"user_id": "u3", "plan_expires_at": "2026-09-01T00:00:00Z", "expiry_reminder_sent_for": "2026-08-01T00:00:00Z"},
    ]
    assert {r["user_id"] for r in rows_due_for_expiry_reminder(rows)} == {"u1", "u3"}


def test_expiry_empty_input_returns_empty():
    assert rows_due_for_expiry_reminder([]) == []


# ── rows_due_for_failed_payment_reminder ─────────────────────────────

def test_never_reminded_with_user_id_is_due():
    rows = [{"id": 1, "user_id": "u1", "reminder_sent_at": None}]
    assert rows_due_for_failed_payment_reminder(rows) == rows


def test_already_reminded_is_skipped():
    rows = [{"id": 1, "user_id": "u1", "reminder_sent_at": "2026-07-01T00:00:00Z"}]
    assert rows_due_for_failed_payment_reminder(rows) == []


def test_no_user_id_is_never_due_even_if_unreminded():
    # A failed attempt that never carried a user_id has nobody to email --
    # must not surface as "due" and then be skipped silently downstream
    # for the wrong reason; it should never be considered due at all.
    rows = [{"id": 1, "user_id": None, "reminder_sent_at": None}]
    assert rows_due_for_failed_payment_reminder(rows) == []


def test_failed_payment_mixed_batch_filters_correctly():
    rows = [
        {"id": 1, "user_id": "u1", "reminder_sent_at": None},
        {"id": 2, "user_id": "u2", "reminder_sent_at": "2026-07-01T00:00:00Z"},
        {"id": 3, "user_id": None, "reminder_sent_at": None},
    ]
    assert [r["id"] for r in rows_due_for_failed_payment_reminder(rows)] == [1]


def test_failed_payment_empty_input_returns_empty():
    assert rows_due_for_failed_payment_reminder([]) == []
