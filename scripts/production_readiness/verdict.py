"""Fail-closed verdict: READY only if every check is PASS or INFO.

FAIL or UNKNOWN on any check forces HOLD -- an UNKNOWN (missing credential,
crashed check, ambiguous API response) is never treated as a pass.
"""
from __future__ import annotations

from .models import CheckResult, Status

READY = "READY"
HOLD = "HOLD"


def compute_verdict(results: list[CheckResult]) -> tuple[str, int]:
    blocking = [r for r in results if r.status in (Status.FAIL, Status.UNKNOWN)]
    if blocking:
        return HOLD, 1
    return READY, 0
