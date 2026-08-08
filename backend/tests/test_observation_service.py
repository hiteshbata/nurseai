from app.services.observation_service import validate_and_normalize


def test_keeps_in_range_scores_for_the_matching_module():
    result = validate_and_normalize("speaking", {"speaking:fluency": 4.0, "speaking:grammar": 6})
    assert result == {"speaking:fluency": 4.0, "speaking:grammar": 6.0}


def test_rejects_out_of_range_scores():
    result = validate_and_normalize("speaking", {"speaking:fluency": -1, "speaking:grammar": 6.1})
    assert result == {}


def test_rejects_non_numeric_and_bool_scores():
    result = validate_and_normalize("speaking", {"speaking:fluency": "4", "speaking:grammar": True})
    assert result == {}


def test_rejects_nan():
    result = validate_and_normalize("speaking", {"speaking:fluency": float("nan")})
    assert result == {}


def test_rejects_tags_from_a_different_module():
    result = validate_and_normalize("speaking", {"reading:comprehension": 4.0})
    assert result == {}


def test_empty_module_yields_no_observations():
    assert validate_and_normalize("", {"speaking:fluency": 4.0}) == {}


def test_rounds_to_two_decimal_places():
    result = validate_and_normalize("speaking", {"speaking:fluency": 4.5678})
    assert result == {"speaking:fluency": 4.57}
