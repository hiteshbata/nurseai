from scripts.production_readiness.models import CheckResult, Severity, Status, redact
from scripts.production_readiness.verdict import HOLD, READY, compute_verdict


def test_redact_strips_known_secret_values():
    text = "request failed: token sbp_abcdef1234567890 rejected"
    assert "sbp_abcdef1234567890" not in redact(text)
    assert "***REDACTED***" in redact(text)


def test_redact_strips_explicit_secret_list():
    text = "Authorization: Bearer my-super-secret-value"
    out = redact(text, secrets=["my-super-secret-value"])
    assert "my-super-secret-value" not in out


def test_redact_handles_empty_text():
    assert redact("") == ""
    assert redact(None) is None


def _result(status: Status, severity: Severity = Severity.MANDATORY) -> CheckResult:
    return CheckResult(name="X", status=status, severity=severity, summary="s")


def test_verdict_all_pass_is_ready():
    final, code = compute_verdict([_result(Status.PASS), _result(Status.PASS)])
    assert final == READY
    assert code == 0


def test_verdict_info_does_not_block():
    final, code = compute_verdict([_result(Status.PASS), _result(Status.INFO, Severity.OPTIONAL)])
    assert final == READY
    assert code == 0


def test_verdict_any_unknown_forces_hold():
    final, code = compute_verdict([_result(Status.PASS), _result(Status.UNKNOWN)])
    assert final == HOLD
    assert code == 1


def test_verdict_any_fail_forces_hold():
    final, code = compute_verdict([_result(Status.PASS), _result(Status.FAIL)])
    assert final == HOLD
    assert code == 1
