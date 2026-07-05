import time
from collections import deque


class SlidingWindowRateLimiter:
    """In-memory sliding-window limiter, keyed by an arbitrary string (e.g. user_id).

    Generalizes the per-router pattern originally in speaking.py's
    _tts_rate_limited/_tts_call_log. The prod entrypoint runs a single uvicorn
    worker (no --workers flag), so a per-process dict is a correct and
    sufficient backstop against request-flooding without adding new infra.
    It resets on restart and isn't shared across workers if that ever changes.
    """

    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._call_log: dict[str, deque] = {}

    def is_rate_limited(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        calls = self._call_log.setdefault(key, deque())
        while calls and calls[0] < window_start:
            calls.popleft()
        if len(calls) >= self.max_calls:
            return True
        calls.append(now)
        return False
