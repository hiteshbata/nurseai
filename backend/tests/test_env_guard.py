"""Tests for app.core.env_guard.verify_production_isolation -- the
fail-closed startup check that refuses to boot a non-production ENVIRONMENT
against the production Supabase project (see app/main.py, which calls this
once at import time, and app/core/config.py ENVIRONMENT /
PRODUCTION_SUPABASE_PROJECT_REF).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.env_guard import ProductionIsolationError, project_ref, verify_production_isolation

_PROD_URL = "https://prodref123456789.supabase.co"
_PROD_REF = "prodref123456789"
_QA_URL = "https://qaref1234567890123.supabase.co"
_DEV_URL = "https://devref123456789012.supabase.co"


def _expect_fail(environment, supabase_url, production_ref):
    try:
        verify_production_isolation(environment, supabase_url, production_ref)
        assert False, f"expected ProductionIsolationError for {environment!r} against production Supabase"
    except ProductionIsolationError:
        pass


def _expect_ok(environment, supabase_url, production_ref):
    verify_production_isolation(environment, supabase_url, production_ref)  # must not raise


def test_production_environment_with_production_supabase_allowed():
    _expect_ok("production", _PROD_URL, _PROD_REF)


def test_qa_environment_with_production_supabase_rejected():
    _expect_fail("qa", _PROD_URL, _PROD_REF)


def test_development_environment_with_production_supabase_rejected():
    _expect_fail("development", _PROD_URL, _PROD_REF)


def test_qa_environment_with_different_supabase_project_allowed():
    _expect_ok("qa", _QA_URL, _PROD_REF)


def test_development_environment_with_dev_supabase_allowed():
    _expect_ok("development", _DEV_URL, _PROD_REF)


def test_unconfigured_production_ref_skips_check():
    # Can't detect "this is production" without a configured ref -- must not
    # false-positive-block a QA boot before PRODUCTION_SUPABASE_PROJECT_REF
    # is set.
    _expect_ok("qa", _PROD_URL, "")


def test_environment_comparison_is_case_insensitive():
    _expect_ok("PRODUCTION", _PROD_URL, _PROD_REF)
    _expect_fail("QA", _PROD_URL, _PROD_REF)


def test_project_ref_extracts_subdomain():
    assert project_ref("https://abcdefgh.supabase.co") == "abcdefgh"


def test_project_ref_empty_for_non_supabase_host():
    assert project_ref("https://example.com") == ""


def test_project_ref_empty_for_blank_url():
    assert project_ref("") == ""


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"{passed}/{len(tests)} env guard checks passed")
