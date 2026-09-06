"""Result model shared by every check."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    INFO = "INFO"  # non-blocking: optional checks (OAuth) or PASS-with-data-to-note


class Severity(str, Enum):
    MANDATORY = "mandatory"
    OPTIONAL = "optional"


_SECRET_PATTERNS = [
    re.compile(r"(sbp_|sk_|Bearer\s+)[A-Za-z0-9_\-\.]{8,}"),
]


def redact(text: str, secrets: list[str] | None = None) -> str:
    """Strip known secret values and secret-shaped tokens out of arbitrary
    text (exception messages, API error bodies) before it is ever printed."""
    if not text:
        return text
    out = text
    for s in secrets or []:
        if s:
            out = out.replace(s, "***REDACTED***")
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("***REDACTED***", out)
    return out


@dataclass
class CheckResult:
    name: str
    status: Status
    summary: str
    severity: Severity = Severity.MANDATORY
    details: list[str] = field(default_factory=list)
    remediation: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "severity": self.severity.value,
            "summary": self.summary,
            "details": self.details,
            "remediation": self.remediation,
        }
