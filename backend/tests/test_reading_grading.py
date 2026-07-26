from app.routers.reading import grade_reading, combine_reading_results, resolve_latest_wrong_answers, reading_speed_wpm


def _questions():
    return {
        1: {"id": 1, "correct_answer": "Hypertensive crisis"},
        2: {"id": 2, "correct_answer": "Add calcium channel blocker"},
        3: {"id": 3, "correct_answer": None},  # open-ended / no key -> skipped
    }


def test_all_correct():
    r = grade_reading(_questions(), [
        {"questionId": 1, "selectedOption": "Hypertensive crisis"},
        {"questionId": 2, "selectedOption": "Add calcium channel blocker"},
    ])
    assert r["correct"] == 2 and r["graded"] == 2
    assert r["band"] == 6.0


def test_half_correct_bands_to_three():
    r = grade_reading(_questions(), [
        {"questionId": 1, "selectedOption": "Hypertensive crisis"},
        {"questionId": 2, "selectedOption": "Stroke"},
    ])
    assert r["correct"] == 1 and r["graded"] == 2
    assert r["band"] == 3.0


def test_ungraded_and_unknown_questions_skipped():
    r = grade_reading(_questions(), [
        {"questionId": 3, "selectedOption": "anything"},   # no correct_answer
        {"questionId": 99, "selectedOption": "ghost"},      # not in map
        {"questionId": 1, "selectedOption": "Hypertensive crisis"},
    ])
    assert r["graded"] == 1 and r["correct"] == 1
    assert r["band"] == 6.0


def test_no_answers_is_zero_not_crash():
    r = grade_reading(_questions(), [])
    assert r == {"band": 0.0, "correct": 0, "graded": 0, "results": []}


def test_combine_mixes_mcq_and_short_answer():
    mcq = grade_reading(_questions(), [
        {"questionId": 1, "selectedOption": "Hypertensive crisis"},
        {"questionId": 2, "selectedOption": "Stroke"},
    ])  # 1/2 correct
    short_results = [
        {"questionId": 10, "selected": "surfactant", "correct_answer": "Surfactant", "is_correct": True, "feedback": ""},
        {"questionId": 11, "selected": "wrong", "correct_answer": "KL-6", "is_correct": False, "feedback": ""},
    ]
    combined = combine_reading_results(mcq, short_results)
    assert combined["correct"] == 2 and combined["graded"] == 4
    assert combined["band"] == 3.0
    assert len(combined["results"]) == 4


def test_combine_with_no_short_answers_matches_mcq_alone():
    mcq = grade_reading(_questions(), [{"questionId": 1, "selectedOption": "Hypertensive crisis"}])
    combined = combine_reading_results(mcq, [])
    assert combined == {**mcq, "results": mcq["results"]}


def test_combine_no_questions_at_all_is_zero():
    combined = combine_reading_results({"band": 0.0, "correct": 0, "graded": 0, "results": []}, [])
    assert combined["band"] == 0.0 and combined["graded"] == 0


def test_wrong_answer_stays_wrong_across_attempts():
    # newest-first: most recent attempt at q1 was still wrong
    blobs = [{"results": [{"questionId": 1, "is_correct": False}]}]
    assert 1 in resolve_latest_wrong_answers(blobs)


def test_fixed_mistake_does_not_resurface():
    # newest attempt (first in list) got q1 right; an older attempt got it wrong.
    # The fixed question must not show up in the notebook.
    blobs = [
        {"results": [{"questionId": 1, "is_correct": True}]},   # most recent
        {"results": [{"questionId": 1, "is_correct": False}]},  # older
    ]
    assert resolve_latest_wrong_answers(blobs) == {}


def test_only_most_recent_attempt_counts_per_question():
    blobs = [
        {"results": [{"questionId": 1, "is_correct": False, "selected": "B"}]},  # most recent, still wrong
        {"results": [{"questionId": 1, "is_correct": True, "selected": "A"}]},   # older, was right
    ]
    result = resolve_latest_wrong_answers(blobs)
    assert result[1]["selected"] == "B"


def test_no_wrong_answers_is_empty():
    blobs = [{"results": [{"questionId": 1, "is_correct": True}]}]
    assert resolve_latest_wrong_answers(blobs) == {}


def test_wpm_computed_from_word_count_and_time():
    assert reading_speed_wpm(word_count=300, elapsed_seconds=60) == 300
    assert reading_speed_wpm(word_count=150, elapsed_seconds=60) == 150


def test_wpm_none_without_a_timer():
    assert reading_speed_wpm(word_count=300, elapsed_seconds=None) is None
    assert reading_speed_wpm(word_count=300, elapsed_seconds=0) is None


def test_wpm_none_for_implausibly_short_duration():
    # 2 seconds for any real passage is a client timer glitch, not a genuine read
    assert reading_speed_wpm(word_count=300, elapsed_seconds=2) is None


def test_wpm_none_for_empty_passage():
    assert reading_speed_wpm(word_count=0, elapsed_seconds=60) is None
