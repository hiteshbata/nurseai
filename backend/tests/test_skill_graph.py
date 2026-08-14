import asyncio

from app.services.skill_graph import get_weakness, update_ema, WEAKNESS_MIN_ATTEMPTS, WEAKNESS_BAND_CEILING


def test_first_observation_is_the_score_itself():
    assert update_ema(old_ema=0, attempts=0, new_score=4.5) == 4.5


def test_blends_toward_new_score_after_first():
    # alpha=0.3: 0.3*6 + 0.7*3 = 3.9
    assert update_ema(old_ema=3.0, attempts=1, new_score=6.0, alpha=0.3) == 3.9


def test_repeated_low_scores_pull_average_down():
    ema = 6.0
    attempts = 5  # already has history -- every call below hits the blending branch
    for _ in range(5):
        ema = update_ema(old_ema=ema, attempts=attempts, new_score=0.0, alpha=0.3)
        attempts += 1
    assert ema < 2.0


def test_custom_alpha_is_respected():
    assert update_ema(old_ema=2.0, attempts=1, new_score=4.0, alpha=0.5) == 3.0


# ── get_weakness: the canonical bar every weakness consumer must respect ──

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def like(self, *a, **k):
        return self

    def execute(self):
        return _FakeResult(self._rows)


class _FakeSupabase:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _FakeQuery(self._rows)


def test_get_weakness_excludes_skill_below_min_attempts():
    # A single unlucky attempt must not brand a skill a weakness.
    assert WEAKNESS_MIN_ATTEMPTS == 2
    rows = [{"skill_tag": "reading:A", "attempts": 1, "ema_score": 1.0}]
    out = asyncio.run(get_weakness(_FakeSupabase(rows), "user-1", "reading:"))
    assert out == []


def test_get_weakness_includes_skill_meeting_min_attempts_and_below_ceiling():
    rows = [{"skill_tag": "reading:A", "attempts": WEAKNESS_MIN_ATTEMPTS, "ema_score": WEAKNESS_BAND_CEILING - 0.1}]
    out = asyncio.run(get_weakness(_FakeSupabase(rows), "user-1", "reading:"))
    assert len(out) == 1
    assert out[0] == {"skill": "A", "label": "A", "band": WEAKNESS_BAND_CEILING - 0.1, "attempts": WEAKNESS_MIN_ATTEMPTS}


def test_get_weakness_excludes_skill_at_or_above_band_ceiling():
    rows = [{"skill_tag": "reading:A", "attempts": 5, "ema_score": WEAKNESS_BAND_CEILING}]
    out = asyncio.run(get_weakness(_FakeSupabase(rows), "user-1", "reading:"))
    assert out == []
