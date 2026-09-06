import httpx

from scripts.production_readiness import config
from scripts.production_readiness.checks import vercel
from scripts.production_readiness.models import Status


class _FakeVercelClient:
    """Stands in for vercel._VercelClient. `responses` maps a path prefix
    to a canned dict/response, checked in insertion order."""

    def __init__(self, responses):
        self._responses = responses

    def get(self, path, params=None):
        for prefix, payload in self._responses:
            if path.startswith(prefix):
                return httpx.Response(200, json=payload)
        raise AssertionError(f"unexpected path {path}")

    def close(self):
        pass


def _happy_responses():
    return [
        (f"/v9/projects/{config.EXPECTED_VERCEL_PROJECT}", {"id": config.EXPECTED_VERCEL_PROJECT_ID, "name": config.EXPECTED_VERCEL_PROJECT}),
        (
            "/v6/deployments",
            {
                "deployments": [
                    {
                        "state": "READY",
                        "target": "production",
                        "meta": {"githubCommitSha": config.EXPECTED_PRODUCTION_COMMIT + "0" * 32, "githubCommitRef": "main"},
                    }
                ]
            },
        ),
        (f"/v9/projects/{config.EXPECTED_VERCEL_PROJECT_ID}/domains", {"domains": [{"name": "www.speakoet.com"}]}),
        (
            f"/v9/projects/{config.EXPECTED_VERCEL_PROJECT_ID}/env",
            {"envs": [{"key": "NEXT_PUBLIC_SUPABASE_URL", "target": ["production"]}]},
        ),
    ]


def test_missing_token_is_unknown():
    result = vercel.check_vercel(None)
    assert result.status == Status.UNKNOWN


def test_project_id_mismatch_fails(monkeypatch):
    responses = _happy_responses()
    responses[0] = (responses[0][0], {"id": "prj_wrong", "name": config.EXPECTED_VERCEL_PROJECT})
    responses[2] = ("/v9/projects/prj_wrong/domains", {"domains": [{"name": "www.speakoet.com"}]})
    responses[3] = ("/v9/projects/prj_wrong/env", {"envs": [{"key": "NEXT_PUBLIC_SUPABASE_URL", "target": ["production"]}]})
    monkeypatch.setattr(vercel, "_VercelClient", lambda token, team_id: _FakeVercelClient(responses))
    result = vercel.check_vercel("fake-token")
    assert result.status == Status.FAIL
    assert "project id" in result.summary


def test_api_error_is_unknown(monkeypatch):
    class _ErrorClient:
        def get(self, path, params=None):
            return httpx.Response(500, text="boom")

        def close(self):
            pass

    monkeypatch.setattr(vercel, "_VercelClient", lambda token, team_id: _ErrorClient())
    result = vercel.check_vercel("fake-token")
    assert result.status == Status.UNKNOWN


def test_qa_supabase_url_detected(monkeypatch):
    responses = _happy_responses()

    class _Client(_FakeVercelClient):
        def get(self, path, params=None):
            if path.endswith("/env") and (params or {}).get("decrypt") == "true":
                return httpx.Response(200, json={"envs": [{"key": "NEXT_PUBLIC_SUPABASE_URL", "target": ["production"], "value": config.EXPECTED_QA_SUPABASE_URL}]})
            return super().get(path, params)

    monkeypatch.setattr(vercel, "_VercelClient", lambda token, team_id: _Client(responses))
    result = vercel.check_vercel("fake-token")
    assert result.status == Status.FAIL
    assert "QA" in result.summary


def test_undecryptable_env_value_does_not_false_fail(monkeypatch):
    """BUG 3: a token without decrypt scope can get HTTP 200 back with
    `value` set to stored ciphertext instead of plaintext. That ciphertext
    trivially differs from both the prod and QA URLs, so a naive equality
    check would FAIL a production deploy whose shipped bundle is actually
    correct. Non-URL-shaped values must not be treated as a mismatch."""
    responses = _happy_responses()

    class _Client(_FakeVercelClient):
        def get(self, path, params=None):
            if path.endswith("/env") and (params or {}).get("decrypt") == "true":
                return httpx.Response(
                    200,
                    json={"envs": [{"key": "NEXT_PUBLIC_SUPABASE_URL", "target": ["production"], "value": "enc:AbCd1234=="}]},
                )
            return super().get(path, params)

    monkeypatch.setattr(vercel, "_VercelClient", lambda token, team_id: _Client(responses))
    result = vercel.check_vercel("fake-token")
    assert result.status == Status.PASS
    assert any("Bundle isolation" in d for d in result.details)


def test_correctly_decrypted_production_url_passes(monkeypatch):
    responses = _happy_responses()

    class _Client(_FakeVercelClient):
        def get(self, path, params=None):
            if path.endswith("/env") and (params or {}).get("decrypt") == "true":
                return httpx.Response(
                    200,
                    json={"envs": [{"key": "NEXT_PUBLIC_SUPABASE_URL", "target": ["production"], "value": config.EXPECTED_PRODUCTION_SUPABASE_URL}]},
                )
            return super().get(path, params)

    monkeypatch.setattr(vercel, "_VercelClient", lambda token, team_id: _Client(responses))
    result = vercel.check_vercel("fake-token")
    assert result.status == Status.PASS
    assert any("confirmed pointed at production" in d for d in result.details)
