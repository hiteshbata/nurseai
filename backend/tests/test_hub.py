import asyncio
from datetime import date, timedelta

import app.routers.hub as hub_router
from app.routers.hub import describe_skill_tag, compute_streak, build_daily_plan


def test_describe_reading_part_tag():
    assert describe_skill_tag("reading:B") == {
        "skill_tag": "reading:B", "label": "Reading Part B", "href": "/practice/reading",
    }


def test_describe_listening_accent_tag():
    d = describe_skill_tag("listening:accent:UK")
    assert d["label"] == "Listening — UK accent"
    assert d["href"] == "/practice/listening"


def test_describe_speaking_criterion_tag():
    d = describe_skill_tag("speaking:appropriateness_of_language")
    assert d["label"] == "Speaking — Appropriateness Of Language"
    assert d["href"] == "/practice/speaking"


def test_streak_zero_with_no_activity():
    assert compute_streak(set(), date(2026, 7, 23)) == 0


def test_streak_counts_consecutive_days_ending_today():
    today = date(2026, 7, 23)
    dates = {today, today - timedelta(days=1), today - timedelta(days=2)}
    assert compute_streak(dates, today) == 3


def test_streak_still_alive_if_active_yesterday_not_yet_today():
    today = date(2026, 7, 23)
    dates = {today - timedelta(days=1), today - timedelta(days=2)}
    assert compute_streak(dates, today) == 2


def test_streak_broken_if_gap_before_yesterday():
    today = date(2026, 7, 23)
    dates = {today - timedelta(days=3)}
    assert compute_streak(dates, today) == 0


def test_streak_stops_at_first_gap():
    today = date(2026, 7, 23)
    dates = {today, today - timedelta(days=1), today - timedelta(days=3)}  # gap at day 2
    assert compute_streak(dates, today) == 2


def test_daily_plan_uses_weakest_skills_when_available():
    weakest = [
        {"skill_tag": "reading:A", "ema_score": 1.0, "attempts": 3},
        {"skill_tag": "speaking:fluency", "ema_score": 2.0, "attempts": 2},
        {"skill_tag": "writing:grammar", "ema_score": 2.5, "attempts": 1},
        {"skill_tag": "listening:B", "ema_score": 5.0, "attempts": 4},
    ]
    plan = build_daily_plan(weakest, attempted_modules={"reading", "speaking", "writing", "listening"})
    assert len(plan) == 3
    assert plan[0]["skill_tag"] == "reading:A"


def test_daily_plan_falls_back_to_starter_tasks_for_new_user():
    plan = build_daily_plan([], attempted_modules=set())
    assert len(plan) == 3
    assert all(p["href"].startswith("/practice/") for p in plan)


# ── ROUTES now source weakness from skill_graph.get_weakness (E1 fix) ──────
# Hub must no longer query user_skill_stats/ema_score directly -- both
# get_today's plan and get_revision_queue delegate to the canonical
# get_weakness, which already enforces WEAKNESS_MIN_ATTEMPTS and
# WEAKNESS_BAND_CEILING.

class _FakeUser:
    def __init__(self, user_id):
        self.id = user_id


class _FakeResult:
    def __init__(self, data=None, count=None):
        self.data = data if data is not None else []
        self.count = count


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def lte(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return self._result


class _FakeSupabase:
    def __init__(self, results):
        self._results = results

    def table(self, name):
        return _FakeQuery(self._results.get(name, _FakeResult([])))


def _patch_weakness(monkeypatch, weakest):
    calls = []

    async def _fake_get_weakness(user_db, user_id, tag_prefix, label_fn=None):
        calls.append((user_id, tag_prefix))
        return weakest

    monkeypatch.setattr(hub_router, "get_weakness", _fake_get_weakness)
    return calls


def test_get_today_plan_uses_canonical_weakness(monkeypatch):
    calls = _patch_weakness(monkeypatch, [
        {"skill": "reading:A", "label": "Reading Part A", "band": 2.0, "attempts": 3},
    ])
    supabase = _FakeSupabase({
        "submissions": _FakeResult([]),
        "daily_goal_completions": _FakeResult([]),
        "vocab_cards": _FakeResult([], count=0),
    })

    result = asyncio.run(hub_router.get_today(current_user=_FakeUser("user-1"), supabase=supabase))

    assert result["plan"][0]["skill_tag"] == "reading:A"
    assert calls == [("user-1", "")]  # empty prefix = scan across all modules


def test_get_today_falls_back_to_starter_plan_when_no_weakness_clears_bar(monkeypatch):
    # get_weakness itself already dropped anything under WEAKNESS_MIN_ATTEMPTS
    # -- an empty return must fall back to the starter plan, not an empty one.
    _patch_weakness(monkeypatch, [])
    supabase = _FakeSupabase({
        "submissions": _FakeResult([]),
        "daily_goal_completions": _FakeResult([]),
        "vocab_cards": _FakeResult([], count=0),
    })

    result = asyncio.run(hub_router.get_today(current_user=_FakeUser("user-1"), supabase=supabase))

    assert len(result["plan"]) == 3
    assert all(p["skill_tag"].endswith(":intro") for p in result["plan"])


def test_get_revision_queue_uses_canonical_weakness(monkeypatch):
    calls = _patch_weakness(monkeypatch, [
        {"skill": "speaking:fluency", "label": "Speaking — Fluency", "band": 1.5, "attempts": 4},
        {"skill": "writing:grammar", "label": "Writing — Grammar", "band": 2.5, "attempts": 2},
    ])

    result = asyncio.run(hub_router.get_revision_queue(current_user=_FakeUser("user-1"), supabase=object()))

    assert calls == [("user-1", "")]
    assert result[0]["skill_tag"] == "speaking:fluency"
    assert result[0]["ema_score"] == 1.5
    assert result[0]["attempts"] == 4
    assert "label" in result[0] and "href" in result[0]  # response shape preserved


def test_get_revision_queue_respects_limit(monkeypatch):
    weakest = [
        {"skill": f"reading:skill_{i}", "label": f"Skill {i}", "band": float(i), "attempts": 3}
        for i in range(hub_router.REVISION_QUEUE_LIMIT + 5)
    ]
    _patch_weakness(monkeypatch, weakest)

    result = asyncio.run(hub_router.get_revision_queue(current_user=_FakeUser("user-1"), supabase=object()))

    assert len(result) == hub_router.REVISION_QUEUE_LIMIT
