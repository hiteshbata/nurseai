"""Fail-closed guard: refuse to boot a non-production ENVIRONMENT against the
production Supabase project (see app/core/config.py ENVIRONMENT and
PRODUCTION_SUPABASE_PROJECT_REF). Called once from app/main.py at import time
so a misconfigured qa/dev deploy crashes on startup instead of silently
reading/writing production data.

Never logs SUPABASE_URL or any key -- only the short project-ref segment,
which is an id, not a credential.
"""
import re
from urllib.parse import urlparse


def project_ref(supabase_url: str) -> str:
    """Extract the project-ref subdomain from a Supabase URL, e.g.
    "https://abcdefghijklmnop.supabase.co" -> "abcdefghijklmnop". Returns ""
    if the URL is empty or not a *.supabase.co host."""
    if not supabase_url:
        return ""
    host = urlparse(supabase_url).hostname or ""
    match = re.match(r"^([a-z0-9-]+)\.supabase\.co$", host.lower())
    return match.group(1) if match else ""


class ProductionIsolationError(RuntimeError):
    pass


def verify_production_isolation(environment: str, supabase_url: str, production_project_ref: str) -> None:
    """Raises ProductionIsolationError if a non-production ENVIRONMENT is
    pointed at the production Supabase project. No-ops if
    PRODUCTION_SUPABASE_PROJECT_REF isn't configured yet -- can't detect a
    project we don't know the ref for."""
    if (environment or "").strip().lower() == "production":
        return

    prod_ref = project_ref(production_project_ref) or (production_project_ref or "").strip().lower()
    if not prod_ref:
        return

    current_ref = project_ref(supabase_url)
    if current_ref and current_ref == prod_ref:
        raise ProductionIsolationError(
            f"FATAL: ENVIRONMENT={environment!r} but SUPABASE_URL points at the "
            f"production Supabase project (ref {current_ref}). Refusing to start "
            "-- a non-production environment must never talk to production Supabase."
        )


def demo():
    # production + production Supabase -> allowed
    verify_production_isolation("production", "https://prodref123456789.supabase.co", "prodref123456789")
    # qa + QA Supabase -> allowed
    verify_production_isolation("qa", "https://qaref1234567890123.supabase.co", "prodref123456789")
    # development + explicit dev/QA Supabase -> allowed
    verify_production_isolation("development", "https://devref123456789012.supabase.co", "prodref123456789")
    # production ref not configured yet -> allowed (can't detect)
    verify_production_isolation("qa", "https://prodref123456789.supabase.co", "")

    # qa + production Supabase -> must fail
    try:
        verify_production_isolation("qa", "https://prodref123456789.supabase.co", "prodref123456789")
        raise AssertionError("expected ProductionIsolationError")
    except ProductionIsolationError:
        pass

    # development + production Supabase -> must fail
    try:
        verify_production_isolation("development", "https://prodref123456789.supabase.co", "prodref123456789")
        raise AssertionError("expected ProductionIsolationError")
    except ProductionIsolationError:
        pass

    print("env_guard demo OK")


if __name__ == "__main__":
    demo()
