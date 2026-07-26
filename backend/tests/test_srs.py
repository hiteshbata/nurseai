from app.services.srs import sm2_review, SRSState, DEFAULT_EASE


def _new_card():
    return SRSState(ease=DEFAULT_EASE, interval_days=0, reps=0)


def test_first_good_review_sets_interval_to_one_day():
    result = sm2_review(_new_card(), quality=4)
    assert result.interval_days == 1
    assert result.reps == 1


def test_second_good_review_sets_interval_to_six_days():
    first = sm2_review(_new_card(), quality=4)
    second = sm2_review(first, quality=4)
    assert second.interval_days == 6
    assert second.reps == 2


def test_third_good_review_multiplies_by_ease():
    first = sm2_review(_new_card(), quality=4)
    second = sm2_review(first, quality=4)
    third = sm2_review(second, quality=4)
    assert third.interval_days == round(second.interval_days * second.ease)
    assert third.reps == 3


def test_forgetting_resets_interval_and_reps():
    first = sm2_review(_new_card(), quality=4)
    second = sm2_review(first, quality=4)
    forgot = sm2_review(second, quality=1)
    assert forgot.interval_days == 1
    assert forgot.reps == 0


def test_low_quality_lowers_ease_floor_respected():
    state = _new_card()
    for _ in range(10):
        state = sm2_review(state, quality=0)
    assert state.ease >= 1.3


def test_high_quality_raises_ease():
    result = sm2_review(_new_card(), quality=5)
    assert result.ease > DEFAULT_EASE
