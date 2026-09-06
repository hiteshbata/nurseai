from scripts.production_readiness import config
from scripts.production_readiness.checks import auth
from scripts.production_readiness.models import Status


def _base_config(confirm_template: str) -> dict:
    return {
        "site_url": config.EXPECTED_FRONTEND_URL,
        "uri_allow_list": config.EXPECTED_AUTH_CALLBACK_URL,
        "mailer_templates_confirmation_content": confirm_template,
        "external_google_enabled": False,
        "external_azure_enabled": False,
    }


def test_missing_credential_is_unknown():
    assert auth.check_auth_config(None).status == Status.UNKNOWN
    assert auth.check_smtp(None).status == Status.UNKNOWN


def test_legacy_confirmation_url_template_fails(monkeypatch):
    cfg = _base_config('<a href="{{ .ConfirmationURL }}">Confirm</a>')
    monkeypatch.setattr(auth, "_get_auth_config", lambda token: (cfg, None))
    result = auth.check_auth_config("fake-token")
    assert result.status == Status.FAIL
    assert "legacy" in result.summary


def test_token_hash_template_passes(monkeypatch):
    cfg = _base_config(
        '<a href="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email&next={{ .RedirectTo }}">Confirm</a>'
    )
    monkeypatch.setattr(auth, "_get_auth_config", lambda token: (cfg, None))
    result = auth.check_auth_config("fake-token")
    assert result.status == Status.PASS


def test_api_error_is_unknown(monkeypatch):
    monkeypatch.setattr(auth, "_get_auth_config", lambda token: (None, "HTTP 500"))
    result = auth.check_auth_config("fake-token")
    assert result.status == Status.UNKNOWN
