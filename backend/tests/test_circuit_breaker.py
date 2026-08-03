"""
H12: AI provider calls need a circuit breaker so a provider outage doesn't
turn into a thundering herd of timeouts -- after 5 consecutive failures the
provider is skipped for 60s, then gets one probe request.

Run with:
    python -m unittest backend/tests/test_circuit_breaker.py -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import circuit_breaker  # noqa: E402


class CircuitBreakerLocalFallbackTests(unittest.TestCase):
    """Exercises the in-process fallback path (get_redis() -> None), same as
    running with no REDIS_URL configured."""

    def setUp(self):
        self._original_get_redis = circuit_breaker.get_redis
        circuit_breaker.get_redis = lambda: None
        circuit_breaker._local_fails.clear()
        circuit_breaker._local_opened_at.clear()

    def tearDown(self):
        circuit_breaker.get_redis = self._original_get_redis
        circuit_breaker._local_fails.clear()
        circuit_breaker._local_opened_at.clear()

    def test_closed_by_default(self):
        self.assertEqual(circuit_breaker.state("openrouter"), "closed")
        self.assertTrue(circuit_breaker.allow_request("openrouter"))

    def test_opens_after_threshold_failures(self):
        for _ in range(circuit_breaker.FAILURE_THRESHOLD - 1):
            circuit_breaker.record_failure("openrouter")
        self.assertTrue(circuit_breaker.allow_request("openrouter"))  # still under threshold

        circuit_breaker.record_failure("openrouter")  # 5th failure trips it
        self.assertEqual(circuit_breaker.state("openrouter"), "open")
        self.assertFalse(circuit_breaker.allow_request("openrouter"))

    def test_half_open_after_cooldown_then_success_closes(self):
        for _ in range(circuit_breaker.FAILURE_THRESHOLD):
            circuit_breaker.record_failure("openrouter")
        self.assertFalse(circuit_breaker.allow_request("openrouter"))

        circuit_breaker._local_opened_at["openrouter"] -= circuit_breaker.COOLDOWN_SECONDS
        self.assertEqual(circuit_breaker.state("openrouter"), "half_open")
        self.assertTrue(circuit_breaker.allow_request("openrouter"))

        circuit_breaker.record_success("openrouter")
        self.assertEqual(circuit_breaker.state("openrouter"), "closed")

    def test_providers_are_independent(self):
        for _ in range(circuit_breaker.FAILURE_THRESHOLD):
            circuit_breaker.record_failure("gemini")
        self.assertFalse(circuit_breaker.allow_request("gemini"))
        self.assertTrue(circuit_breaker.allow_request("openai"))


if __name__ == "__main__":
    unittest.main()
