"""Pure dedup logic for the reminder-email crons (see app/routers/admin.py
send-reminders endpoints). Separated from the Supabase I/O so the one
thing that actually matters -- never re-emailing someone for the same
event, never silently skipping a real one -- is testable without a DB.
"""
from typing import Any, Dict, List


def rows_due_for_expiry_reminder(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A row is due unless a reminder was already sent for THIS
    plan_expires_at value. Comparing against the exact expiry timestamp
    (not just "was a reminder ever sent") means a renewal that pushes
    plan_expires_at forward makes the user eligible again next cycle."""
    return [r for r in rows if r.get("expiry_reminder_sent_for") != r.get("plan_expires_at")]


def rows_due_for_failed_payment_reminder(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A row is due if it has someone to email and hasn't been reminded yet."""
    return [r for r in rows if r.get("user_id") and not r.get("reminder_sent_at")]


if __name__ == "__main__":
    expiry_rows = [
        {"user_id": "u1", "plan_expires_at": "2026-08-01T00:00:00Z", "expiry_reminder_sent_for": None},
        {"user_id": "u2", "plan_expires_at": "2026-08-01T00:00:00Z", "expiry_reminder_sent_for": "2026-08-01T00:00:00Z"},
        {"user_id": "u3", "plan_expires_at": "2026-09-01T00:00:00Z", "expiry_reminder_sent_for": "2026-08-01T00:00:00Z"},
    ]
    due = rows_due_for_expiry_reminder(expiry_rows)
    assert {r["user_id"] for r in due} == {"u1", "u3"}, due

    failed_rows = [
        {"id": 1, "user_id": "u1", "reminder_sent_at": None},
        {"id": 2, "user_id": "u2", "reminder_sent_at": "2026-07-01T00:00:00Z"},
        {"id": 3, "user_id": None, "reminder_sent_at": None},
    ]
    due2 = rows_due_for_failed_payment_reminder(failed_rows)
    assert [r["id"] for r in due2] == [1], due2

    print("reminders self-check OK")
