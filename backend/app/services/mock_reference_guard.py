"""Guards content deletion against the Dynamic Mock Test reference model.

Mock Test freezes content by reference (id), not by copy -- see mock.py's
module docstring. Deleting a reading/listening test or a writing/speaking
scenario that's still frozen into a live pack or an open session silently
nulls the reference via each FK's ON DELETE SET NULL, corrupting that
pack/session with no warning (this is exactly how Mock Test 3 ended up with
reading_test_id=NULL). This module is the one place that check lives, so
reading.py/listening.py/admin.py don't need to import mock.py itself.
"""
from fastapi import HTTPException

# Mirrors mock.py's OPEN_STATUSES -- duplicated rather than imported so this
# module (and its callers) stay independent of mock.py.
OPEN_MOCK_SESSION_STATUSES = ["in_progress", "awaiting_speaking"]


def block_if_referenced_by_mock_test(supabase, column: str, content_id: int) -> None:
    """Raise 409 if `content_id` is still referenced -- via `column` (e.g.
    "reading_test_id") -- by an active mock_tests pack or an open
    mock_test_sessions row. A *completed* session's copy of the id does NOT
    block deletion: its result is already recorded and needs no live content.

    Call this immediately before the delete, not earlier in the handler --
    it's a check-then-act race like any other (a pack/session could be
    created referencing this content between the check and the delete), not
    a database-level guarantee. Closing that race fully would need a DB
    trigger/constraint; not warranted here since the content this protects
    (admin-authored test/scenario library) isn't written concurrently at a
    rate where that race is a realistic concern.
    """
    packs = (
        supabase.table("mock_tests").select("id, label")
        .eq(column, content_id).eq("is_active", True).execute().data
    )
    open_sessions = (
        supabase.table("mock_test_sessions").select("id")
        .eq(column, content_id).in_("status", OPEN_MOCK_SESSION_STATUSES).execute().data
    )
    if not packs and not open_sessions:
        return

    parts = []
    if packs:
        parts.append(f"active Mock Test pack(s): {', '.join(p['label'] for p in packs)}")
    if open_sessions:
        parts.append(f"{len(open_sessions)} in-progress mock test session(s)")
    raise HTTPException(
        status_code=409,
        detail=f"Can't delete -- referenced by {' and '.join(parts)}. "
        "Deactivate the pack first, or wait for the session(s) to finish.",
    )
