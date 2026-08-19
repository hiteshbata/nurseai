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


class SanityDatasetIsolationError(RuntimeError):
    pass


def verify_sanity_dataset_isolation(environment: str, dataset: str) -> None:
    """Raises SanityDatasetIsolationError if a non-production ENVIRONMENT is
    about to use the Sanity "production" dataset (SANITY_DATASET's default --
    see app/core/config.py). Unlike Supabase's URL-based check, there's no
    project ref to compare: SANITY_DATASET is a plain string, and its own
    default value IS "production", so an unconfigured QA/dev deploy would
    otherwise silently target production. QA/dev must set their own
    SANITY_DATASET explicitly to pass this check."""
    if (environment or "").strip().lower() == "production":
        return

    if (dataset or "").strip().lower() in ("", "production"):
        raise SanityDatasetIsolationError(
            f"FATAL: ENVIRONMENT={environment!r} but SANITY_DATASET={dataset!r} -- "
            "a non-production environment must explicitly configure its own "
            "Sanity dataset. Refusing to write -- a non-production environment "
            "must never target the production Sanity dataset."
        )


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

    # sanity dataset isolation
    verify_sanity_dataset_isolation("production", "production")  # allowed
    verify_sanity_dataset_isolation("qa", "qa-blog")  # explicit non-prod dataset -> allowed
    try:
        verify_sanity_dataset_isolation("qa", "")  # unconfigured -> must fail
        raise AssertionError("expected SanityDatasetIsolationError")
    except SanityDatasetIsolationError:
        pass
    try:
        verify_sanity_dataset_isolation("development", "production")  # explicit prod dataset -> must fail
        raise AssertionError("expected SanityDatasetIsolationError")
    except SanityDatasetIsolationError:
        pass

    print("env_guard demo OK")


if __name__ == "__main__":
    demo()
