from app.services.skill_graph import update_ema


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
