"""
H14 origin: google/-namespaced models must go straight to the Gemini native
API instead of through OpenRouter (10-30% markup).

Since the ai_scoring -> ai_registry refactor (commit 4215b64b "make _call_ai
purpose-driven via the AI model registry"), _call_openai_compatible and
_call_gemini no longer live on ai_scoring at all -- they moved to
ai_registry.py, and provider choice is no longer a "google/" model-name
heuristic inside _call_ai. It is decided entirely by whatever Admin > AI
Models config an admin assigns to a "purpose" (ai_registry.get_model_config),
and _call_ai does one unconditional fallback hop to that model's configured
fallback_model_id on ANY failure -- see ai_registry.py's module docstring and
_call_ai's own docstring ("single-hop fallback"). The old distinction between
config errors (400/401/403/404 -- don't retry) and transient errors
(408/429/5xx/timeout -- do retry) was removed in that refactor, so it is
intentionally NOT reproduced here.

These tests exercise the current contract by mocking _call_ai's two external
dependencies -- ai_registry.get_model_config (DB lookup) and
ai_registry.dispatch_call (the network call) -- and asserting on the
ModelConfig.provider that dispatch_call was actually invoked with, which is
how "which path was taken" is now observable.

Run with:
    python -m unittest backend/tests/test_google_model_routing.py -v
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import ai_scoring  # noqa: E402
from app.services import ai_registry  # noqa: E402
from app.core.config import settings  # noqa: E402


def _cfg(provider: str, model_name: str, fallback=None) -> ai_registry.ModelConfig:
    return ai_registry.ModelConfig(id=1, provider=provider, model_name=model_name, api_base=None, fallback=fallback)


_SUCCESS = {"text": "ok", "finish_reason": "stop", "usage": {"input_tokens": 1, "output_tokens": 1}}


class GoogleModelRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._patches = [
            patch.object(settings, "GEMINI_API_KEY", "gk"),
            patch.object(settings, "OPENAI_API_KEY", "ok"),
            patch.object(settings, "OPENROUTER_API_KEY", "ork"),
            patch("app.services.ai_scoring.circuit_breaker.allow_request", return_value=True),
            patch("app.services.ai_scoring.circuit_breaker.record_success"),
            patch("app.services.ai_scoring.circuit_breaker.record_failure"),
            patch("app.services.ai_scoring.cost_circuit_breaker.raise_if_tripped"),
            patch("app.services.ai_scoring.log_ai_usage", new_callable=AsyncMock),
            patch("app.services.ai_scoring.run_sync", new_callable=AsyncMock),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    async def test_google_model_calls_gemini_directly_not_openrouter(self):
        cfg = _cfg("google", "gemini-2.5-flash", fallback=_cfg("openrouter", "openai/gpt-5.4-mini"))
        with patch.object(ai_registry, "get_model_config", new=AsyncMock(return_value=cfg)), \
             patch.object(ai_registry, "dispatch_call", new=AsyncMock(return_value=_SUCCESS)) as dispatch_mock:
            result = await ai_scoring._call_ai([{"role": "user", "content": "hi"}], purpose="scoring")

        dispatch_mock.assert_called_once()
        self.assertEqual(dispatch_mock.call_args.args[0].provider, "google")
        self.assertEqual(result["raw_feedback"], "ok")

    async def _run(self, primary_error, fallback_error=None):
        primary = _cfg("google", "gemini-2.5-flash", fallback=_cfg("openrouter", "openai/gpt-5.4-mini"))

        async def fake_dispatch(candidate, *_a, **_kw):
            if candidate.provider == "google":
                raise primary_error
            if fallback_error is not None:
                raise fallback_error
            return _SUCCESS

        with patch.object(ai_registry, "get_model_config", new=AsyncMock(return_value=primary)), \
             patch.object(ai_registry, "dispatch_call", new=AsyncMock(side_effect=fake_dispatch)) as dispatch_mock:
            result = await ai_scoring._call_ai([{"role": "user", "content": "hi"}], purpose="scoring")
        return result, dispatch_mock

    async def test_primary_failure_falls_back_to_configured_model(self):
        # Any failure on the primary -- auth/config error or a transient
        # one -- now triggers the single configured fallback hop. The old
        # config-error-vs-transient-error split no longer exists in _call_ai.
        cases = [
            ai_registry.ModelCallError("bad key", 401),
            ai_registry.ModelCallError("not found", 404),
            ai_registry.ModelCallError("server exploded", 500),
            TimeoutError("slow"),
            ConnectionError("dns fail"),
        ]
        for side_effect in cases:
            with self.subTest(side_effect=side_effect):
                result, dispatch_mock = await self._run(side_effect)
                self.assertEqual(dispatch_mock.call_count, 2)
                self.assertEqual(dispatch_mock.call_args.args[0].provider, "openrouter")
                self.assertEqual(result["raw_feedback"], "ok")

    async def test_all_candidates_failing_returns_provider_failure(self):
        # Single-hop only: exactly the 2 configured candidates (primary +
        # its one configured fallback) are tried, never an open-ended retry.
        result, dispatch_mock = await self._run(
            ai_registry.ModelCallError("bad key", 401),
            fallback_error=ai_registry.ModelCallError("server exploded", 500),
        )
        self.assertEqual(dispatch_mock.call_count, 2)
        self.assertTrue(result.get("provider_failure"))


if __name__ == "__main__":
    unittest.main()
