"""Tests for app.core.config's ENVIRONMENT -> dotenv selection (Milestone 4
Finding 1): a QA process must load backend/.env.qa only and never fall back
to backend/.env, which holds production-only secrets like GEMINI_API_KEY /
TURNSTILE_SECRET_KEY. See app/core/config.py _resolve_env_file and
docs/QA_ENVIRONMENT.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings, _resolve_env_file

# Production-only vars with no QA equivalent -- must stay unset in a QA
# process rather than being inherited from backend/.env.
_PROD_ONLY_VARS = ["GEMINI_API_KEY", "TURNSTILE_SECRET_KEY"]


def _write_env(path, **kv):
    path.write_text("\n".join(f"{k}={v}" for k, v in kv.items()) + "\n")


def test_resolve_env_file_production(tmp_path):
    assert _resolve_env_file("production", tmp_path) == tmp_path / ".env"


def test_resolve_env_file_qa(tmp_path):
    assert _resolve_env_file("qa", tmp_path) == tmp_path / ".env.qa"


def test_resolve_env_file_development(tmp_path):
    assert _resolve_env_file("development", tmp_path) == tmp_path / ".env"


def test_resolve_env_file_unknown_defaults_to_dot_env(tmp_path):
    assert _resolve_env_file("bogus", tmp_path) == tmp_path / ".env"


def test_resolve_env_file_case_insensitive(tmp_path):
    assert _resolve_env_file("QA", tmp_path) == tmp_path / ".env.qa"


def test_qa_settings_do_not_inherit_production_only_vars(tmp_path, monkeypatch):
    for var in _PROD_ONLY_VARS + ["SUPABASE_URL", "ENVIRONMENT"]:
        monkeypatch.delenv(var, raising=False)

    prod_env = tmp_path / ".env"
    qa_env = tmp_path / ".env.qa"
    _write_env(
        prod_env,
        SUPABASE_URL="https://prod-fake.supabase.co",
        GEMINI_API_KEY="prod-fake-key",
        TURNSTILE_SECRET_KEY="prod-fake-secret",
    )
    _write_env(qa_env, ENVIRONMENT="qa", SUPABASE_URL="https://qa-fake.supabase.co")

    settings = Settings(_env_file=str(qa_env))

    assert settings.SUPABASE_URL == "https://qa-fake.supabase.co"
    assert settings.GEMINI_API_KEY == ""
    assert settings.TURNSTILE_SECRET_KEY == ""


def test_production_settings_still_load_from_dot_env(tmp_path, monkeypatch):
    for var in _PROD_ONLY_VARS + ["SUPABASE_URL", "ENVIRONMENT"]:
        monkeypatch.delenv(var, raising=False)

    prod_env = tmp_path / ".env"
    _write_env(
        prod_env,
        ENVIRONMENT="production",
        SUPABASE_URL="https://prod-fake.supabase.co",
        GEMINI_API_KEY="prod-fake-key",
    )

    settings = Settings(_env_file=str(prod_env))

    assert settings.SUPABASE_URL == "https://prod-fake.supabase.co"
    assert settings.GEMINI_API_KEY == "prod-fake-key"


def test_missing_optional_qa_var_stays_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    qa_env = tmp_path / ".env.qa"
    _write_env(qa_env, ENVIRONMENT="qa", SUPABASE_URL="https://qa-fake.supabase.co")

    settings = Settings(_env_file=str(qa_env))

    assert settings.TURNSTILE_SECRET_KEY == ""


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
