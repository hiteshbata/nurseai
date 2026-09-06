import httpx

from scripts.production_readiness import config
from scripts.production_readiness.checks import render
from scripts.production_readiness.models import Status


class _FakeRenderClient:
    def __init__(self, responses):
        self._responses = responses

    def get(self, path, params=None):
        for prefix, payload, status in self._responses:
            if path.startswith(prefix):
                return httpx.Response(status, json=payload)
        raise AssertionError(f"unexpected path {path}")

    def close(self):
        pass


def _happy_responses(service_id="srv-123", branch=config.EXPECTED_PRODUCTION_BRANCH):
    return [
        (f"/services/{service_id}/custom-domains", None, 404),  # discovery not needed, service_id passed explicitly
        (f"/services/{service_id}/deploys", [{"deploy": {"status": "live", "commit": {"id": config.EXPECTED_PRODUCTION_COMMIT + "0" * 32}}}], 200),
        (
            f"/services/{service_id}/env-vars",
            [
                {"envVar": {"key": "ENVIRONMENT", "value": "production"}},
                {"envVar": {"key": "SUPABASE_URL", "value": f"https://{config.PRODUCTION_SUPABASE_PROJECT_REF}.supabase.co"}},
                {"envVar": {"key": "FRONTEND_URL", "value": config.EXPECTED_FRONTEND_URL}},
                {"envVar": {"key": "PRODUCTION_SUPABASE_PROJECT_REF", "value": config.PRODUCTION_SUPABASE_PROJECT_REF}},
            ],
            200,
        ),
        (f"/services/{service_id}", {"branch": branch, "suspended": "not_suspended", "name": "nurseai-backend"}, 200),
    ]


def test_missing_credential_is_unknown():
    result = render.check_render(None)
    assert result.status == Status.UNKNOWN


def test_branch_mismatch_fails(monkeypatch):
    responses = _happy_responses(branch="feature/some-branch")
    monkeypatch.setattr(render, "_RenderClient", lambda api_key: _FakeRenderClient(responses))
    result = render.check_render("fake-key", service_id="srv-123")
    assert result.status == Status.FAIL
    assert "branch" in result.summary


def test_api_error_is_unknown(monkeypatch):
    class _ErrorClient:
        def get(self, path, params=None):
            return httpx.Response(500)

        def close(self):
            pass

    monkeypatch.setattr(render, "_RenderClient", lambda api_key: _ErrorClient())
    result = render.check_render("fake-key", service_id="srv-123")
    assert result.status == Status.UNKNOWN


def test_explicit_service_id_skips_discovery(monkeypatch):
    """RENDER_SERVICE_ID set -> the /services list-and-scan discovery path
    must never be called. The fake client has no /services (list) response
    registered, so calling it would raise AssertionError."""
    responses = _happy_responses(service_id="srv-d988tjfavr4c7394dnq0")
    monkeypatch.setattr(render, "_RenderClient", lambda api_key: _FakeRenderClient(responses))
    result = render.check_render("fake-key", service_id="srv-d988tjfavr4c7394dnq0")
    assert result.status == Status.PASS


def test_discovery_failure_is_unknown_never_a_guess(monkeypatch):
    """No RENDER_SERVICE_ID and discovery can't identify a service -> UNKNOWN,
    never a fabricated/guessed service id."""
    class _NoMatchClient:
        def get(self, path, params=None):
            if path == "/services":
                return httpx.Response(200, json=[{"service": {"id": "srv-unrelated"}}])
            if path == "/services/srv-unrelated/custom-domains":
                return httpx.Response(200, json=[{"name": "some-other-app.onrender.com"}])
            raise AssertionError(f"unexpected path {path}")

        def close(self):
            pass

    monkeypatch.setattr(render, "_RenderClient", lambda api_key: _NoMatchClient())
    result = render.check_render("fake-key", service_id=None)
    assert result.status == Status.UNKNOWN
    assert "no service found" in result.summary
