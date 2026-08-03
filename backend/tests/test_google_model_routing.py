"""
H14: google/-namespaced models must go straight to the Gemini native API
instead of through OpenRouter (10-30% markup). OpenRouter is only a fallback
for non-auth failures -- a bad/missing GEMINI_API_KEY should not silently
route every call through the markup provider forever.

Run with:
    python -m unittest backend/tests/test_google_model_routing.py -v
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import ai_scoring  # noqa: E402
from app.core.config import settings  # noqa: E402


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    response = httpx.Response(status, request=request, text="error")
    return httpx.HTTPStatusError(str(status), request=request, response=response)


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
        with patch.object(ai_scoring, "_call_gemini", new=AsyncMock(
            return_value={"raw_feedback": "hi", "_usage": {"input_tokens": 1, "output_tokens": 1}}
        )) as gemini_mock, \
             patch.object(ai_scoring, "_call_openai_compatible", new=AsyncMock()) as compat_mock:
            result = await ai_scoring._call_ai(
                [{"role": "user", "content": "hi"}], model="google/gemini-2.5-flash",
            )
        gemini_mock.assert_called_once()
        compat_mock.assert_not_called()
        self.assertEqual(result["raw_feedback"], "hi")

    async def _run(self, side_effect):
        with patch.object(ai_scoring, "_call_gemini", new=AsyncMock(side_effect=side_effect)), \
             patch.object(ai_scoring, "_call_openai_compatible", new=AsyncMock(
                 return_value={"raw_feedback": "ok", "_usage": {"input_tokens": 1, "output_tokens": 1}}
             )) as compat_mock:
            result = await ai_scoring._call_ai(
                [{"role": "user", "content": "hi"}], model="google/gemini-2.5-flash",
            )
        return result, compat_mock

    async def test_config_errors_do_not_fall_back(self):
        # 400/401/403/404 are configuration problems -- identical on every
        # retry, so falling back would just eat the OpenRouter markup forever.
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                result, compat_mock = await self._run(_http_error(status))
                compat_mock.assert_not_called()
                self.assertTrue(result.get("provider_failure"))

    async def test_transient_errors_fall_back_to_openrouter(self):
        # 408/429/5xx and network/timeout errors are transient -- retry via
        # the fallback chain.
        cases = [_http_error(408), _http_error(429), _http_error(500),
                  _http_error(502), _http_error(503), _http_error(504),
                  httpx.TimeoutException("slow"), httpx.ConnectError("dns fail")]
        for side_effect in cases:
            with self.subTest(side_effect=side_effect):
                result, compat_mock = await self._run(side_effect)
                compat_mock.assert_called_once()
                self.assertEqual(compat_mock.call_args.args[0], "openrouter")
                self.assertEqual(result["raw_feedback"], "ok")


if __name__ == "__main__":
    unittest.main()
