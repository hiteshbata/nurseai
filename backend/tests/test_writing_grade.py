"""Deterministic OET writing overall/grade math (no AI involved)."""
from app.services.ai_scoring import _writing_grade, _writing_overall, WRITING_MAX_RAW


def _scores(purpose, content, conc, genre, org, lang):
    return {
        "purpose": {"score": purpose},
        "content": {"score": content},
        "conciseness": {"score": conc},
        "genre_style": {"score": genre},
        "organization": {"score": org},
        "language": {"score": lang},
    }


def test_grade_band_boundaries():
    assert _writing_grade(500) == "A"
    assert _writing_grade(450) == "A"
    assert _writing_grade(449) == "B"
    assert _writing_grade(350) == "B"
    assert _writing_grade(340) == "C+"
    assert _writing_grade(300) == "C+"
    assert _writing_grade(299) == "C"
    assert _writing_grade(200) == "C"
    assert _writing_grade(199) == "D"
    assert _writing_grade(100) == "D"
    assert _writing_grade(99) == "E"
    assert _writing_grade(0) == "E"


def test_full_marks_is_500_grade_a():
    out = _writing_overall(_scores(3, 7, 7, 7, 7, 7))
    assert out["raw_total"] == WRITING_MAX_RAW == 38
    assert out["overall_score"] == 500
    assert out["estimated_oet_grade"] == "A"


def test_zero_is_grade_e():
    out = _writing_overall(_scores(0, 0, 0, 0, 0, 0))
    assert out["overall_score"] == 0
    assert out["estimated_oet_grade"] == "E"


def test_grade_b_anchor_matches_official_guide():
    # OET Writing guide: a grade-B answer = 2/3 Purpose + 5/7 on the other five.
    out = _writing_overall(_scores(2, 5, 5, 5, 5, 5))
    assert out["raw_total"] == 27
    assert out["overall_score"] == 355
    assert out["estimated_oet_grade"] == "B"


def test_mid_case_scales_linearly():
    # raw 19 of 38 -> 250 -> grade C
    out = _writing_overall(_scores(2, 4, 4, 4, 3, 2))
    assert out["raw_total"] == 19
    assert out["overall_score"] == 250
    assert out["estimated_oet_grade"] == "C"


def test_out_of_range_scores_are_clamped_to_criterion_max():
    # model hands back purpose 6 (max 3) and language 99 (max 7) -> clamped
    out = _writing_overall(_scores(6, 7, 7, 7, 7, 99))
    assert out["raw_total"] == WRITING_MAX_RAW  # 3 + 7*5
    assert out["estimated_oet_grade"] == "A"
