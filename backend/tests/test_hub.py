from datetime import date, timedelta

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
