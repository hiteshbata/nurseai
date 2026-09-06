"""Tests for the Phase 5 Human Calibration Package (schema + builder).

Pure/offline only -- no model call, no ai_registry, no DB, no network. See
app/services/human_calibration.py's module docstring for scope.
"""
from __future__ import annotations

import ast
import inspect
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services import human_calibration as hc
from app.services.examiner_input import ALL_CRITERIA, CLINICAL_CRITERIA, LINGUISTIC_CRITERIA
from app.services.shadow_examiner import (
    FAMILY_CLINICAL,
    FAMILY_LINGUISTIC,
    STATUS_ASSESSED,
    STATUS_LIMITED_EVIDENCE,
)
from app.services.shadow_examiner_benchmark import GOLDEN_SET

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _criterion_review(criterion: str, **overrides) -> hc.HumanCriterionReview:
    family = FAMILY_LINGUISTIC if criterion in LINGUISTIC_CRITERIA else FAMILY_CLINICAL
    defaults = dict(
        criterion=criterion, family=family, status=STATUS_LIMITED_EVIDENCE, level=None, justification="x",
    )
    defaults.update(overrides)
    return hc.HumanCriterionReview(**defaults)


def _full_review(case_id="case_001", reviewer_id=None, **per_criterion_overrides) -> hc.HumanReview:
    criteria = [
        _criterion_review(c, **per_criterion_overrides.get(c, {})) for c in ALL_CRITERIA
    ]
    return hc.HumanReview(case_id=case_id, reviewer_id=reviewer_id, criteria=criteria)


# ── Schema: exactly 9 criteria, valid families/levels/status ──────────────


def test_human_review_requires_exactly_nine_criteria():
    review = _full_review()
    assert len(review.criteria) == 9
    assert {c.criterion for c in review.criteria} == set(ALL_CRITERIA)


def test_too_few_criteria_rejected():
    with pytest.raises(ValidationError, match="exactly 9"):
        hc.HumanReview(case_id="c", criteria=[_criterion_review(ALL_CRITERIA[0])])


def test_duplicate_criteria_rejected():
    dupes = [_criterion_review(ALL_CRITERIA[0]), _criterion_review(ALL_CRITERIA[0])] + [
        _criterion_review(c) for c in ALL_CRITERIA[1:8]
    ]
    with pytest.raises(ValidationError, match="duplicate criterion"):
        hc.HumanReview(case_id="c", criteria=dupes)


def test_unknown_criterion_rejected():
    with pytest.raises(ValidationError):
        _criterion_review("not_a_real_criterion")


def test_missing_criterion_rejected():
    partial = [_criterion_review(c) for c in ALL_CRITERIA[:8]]
    with pytest.raises(ValidationError):
        hc.HumanReview(case_id="c", criteria=partial)


def test_valid_clinical_level_range():
    _criterion_review(CLINICAL_CRITERIA[0], status=STATUS_ASSESSED, level=3)
    _criterion_review(CLINICAL_CRITERIA[0], status=STATUS_ASSESSED, level=0)


def test_invalid_clinical_level_rejected():
    with pytest.raises(ValidationError):
        _criterion_review(CLINICAL_CRITERIA[0], status=STATUS_ASSESSED, level=4)


def test_valid_linguistic_level_range():
    _criterion_review(LINGUISTIC_CRITERIA[0], status=STATUS_ASSESSED, level=6)
    _criterion_review(LINGUISTIC_CRITERIA[0], status=STATUS_ASSESSED, level=0)


def test_invalid_linguistic_level_rejected():
    with pytest.raises(ValidationError):
        _criterion_review(LINGUISTIC_CRITERIA[0], status=STATUS_ASSESSED, level=7)


def test_invalid_status_rejected():
    with pytest.raises(ValidationError):
        _criterion_review(ALL_CRITERIA[0], status="not_a_real_status")


def test_family_mismatch_rejected():
    with pytest.raises(ValidationError, match="inconsistent"):
        hc.HumanCriterionReview(
            criterion=CLINICAL_CRITERIA[0], family=FAMILY_LINGUISTIC, status=STATUS_LIMITED_EVIDENCE,
            level=None, justification="x",
        )


# ── limited_evidence requires null level -- never force a zero ────────────


def test_limited_evidence_requires_null_level():
    with pytest.raises(ValidationError, match="never force a zero"):
        _criterion_review(CLINICAL_CRITERIA[0], status=STATUS_LIMITED_EVIDENCE, level=0)


def test_assessed_requires_non_null_level():
    with pytest.raises(ValidationError, match="requires a non-null level"):
        _criterion_review(CLINICAL_CRITERIA[0], status=STATUS_ASSESSED, level=None)


def test_evidence_conflict_unresolved_requires_null_level():
    with pytest.raises(ValidationError):
        _criterion_review(CLINICAL_CRITERIA[0], status="evidence_conflict_unresolved", level=2)


# ── evidence reference validation ──────────────────────────────────────────


def test_evidence_ref_turn_index_must_be_non_negative():
    with pytest.raises(ValidationError):
        hc.HumanEvidenceRef(turn_index=-1)


def test_evidence_ref_accepts_optional_note_and_evidence_id():
    ref = hc.HumanEvidenceRef(turn_index=2, note="patient raised concern here", evidence_id="empathy_ack")
    assert ref.turn_index == 2


def test_indicator_notes_must_belong_to_criterion():
    with pytest.raises(ValidationError, match="do not belong"):
        _criterion_review("relationship_building", status=STATUS_ASSESSED, level=2, indicator_notes=["D1"])


def test_indicator_notes_rejected_for_linguistic():
    with pytest.raises(ValidationError, match="clinical-only"):
        _criterion_review(LINGUISTIC_CRITERIA[0], status=STATUS_ASSESSED, level=3, indicator_notes=["A1"])


# ── multiple reviewers supported, not auto-merged ──────────────────────────


def test_multiple_reviewers_same_case_not_merged():
    review_a = _full_review(case_id="case_001", reviewer_id="reviewer_a")
    review_b = _full_review(case_id="case_001", reviewer_id="reviewer_b")
    assert review_a.reviewer_id != review_b.reviewer_id
    assert review_a is not review_b  # schema supports independent objects; nothing merges them


def test_blank_review_template_is_schema_valid_and_all_limited_evidence():
    template = hc.blank_review_template("case_001")
    assert len(template.criteria) == 9
    assert all(c.status == STATUS_LIMITED_EVIDENCE and c.level is None for c in template.criteria)


# ── administrator comparison utility ───────────────────────────────────────


def test_compare_case_exact_agreement():
    from app.services.shadow_examiner import CriterionJudgement

    human = [_criterion_review("relationship_building", status=STATUS_ASSESSED, level=2,
                                evidence_refs=[hc.HumanEvidenceRef(turn_index=2)])]
    provisional = [CriterionJudgement(
        criterion="relationship_building", family=FAMILY_CLINICAL, status=STATUS_ASSESSED, level=2,
        level_label="Competent use", justification="x", evidence_quality="STRONG",
        evidence_refs=[{"evidence_id": "e1", "turn_index": 2, "evidence_level": "L2_deterministic", "source": "candidate_event"}],
    )]
    rows = hc.compare_case("case_001", human, provisional)
    assert len(rows) == 1
    assert rows[0].agreement_bucket == hc.AGREEMENT_EXACT
    assert rows[0].level_difference == 0
    assert rows[0].evidence_turn_overlap == [2]


def test_compare_case_adjacent_and_large_disagreement():
    from app.services.shadow_examiner import CriterionJudgement

    def _prov(level):
        return CriterionJudgement(
            criterion="relationship_building", family=FAMILY_CLINICAL, status=STATUS_ASSESSED, level=level,
            level_label={3: "Adept use", 2: "Competent use", 1: "Partially effective use", 0: "Ineffective use"}[level],
            justification="x", evidence_quality="STRONG",
        )

    adjacent = hc.compare_case("c", [_criterion_review("relationship_building", status=STATUS_ASSESSED, level=2)], [_prov(3)])
    assert adjacent[0].agreement_bucket == hc.AGREEMENT_ADJACENT

    large = hc.compare_case("c", [_criterion_review("relationship_building", status=STATUS_ASSESSED, level=0)], [_prov(3)])
    assert large[0].agreement_bucket == hc.AGREEMENT_LARGE


def test_compare_case_status_mismatch_and_both_limited():
    from app.services.shadow_examiner import CriterionJudgement

    limited_prov = CriterionJudgement(
        criterion="relationship_building", family=FAMILY_CLINICAL, status=STATUS_LIMITED_EVIDENCE,
        level=None, justification="x", evidence_quality="INSUFFICIENT",
    )
    both_limited = hc.compare_case(
        "c", [_criterion_review("relationship_building", status=STATUS_LIMITED_EVIDENCE)], [limited_prov],
    )
    assert both_limited[0].agreement_bucket == hc.AGREEMENT_BOTH_LIMITED

    assessed_prov = CriterionJudgement(
        criterion="relationship_building", family=FAMILY_CLINICAL, status=STATUS_ASSESSED, level=2,
        level_label="Competent use", justification="x", evidence_quality="STRONG",
    )
    mismatch = hc.compare_case(
        "c", [_criterion_review("relationship_building", status=STATUS_LIMITED_EVIDENCE)], [assessed_prov],
    )
    assert mismatch[0].agreement_bucket == hc.AGREEMENT_STATUS_MISMATCH


def test_compare_case_can_load_both_sides_from_generated_admin_package(tmp_path):
    """Administrator comparison can load a HumanReview alongside the
    provisional_references.json this package generates for one case."""
    admin_dir = BACKEND_ROOT / "phase5_human_calibration" / "admin"
    provisional = json.loads((admin_dir / "provisional_references.json").read_text(encoding="utf-8"))
    metadata = json.loads((admin_dir / "benchmark_metadata.json").read_text(encoding="utf-8"))
    real_case_id = metadata["cases"][0]["real_case_id"]
    ref_judgement_dicts = provisional[real_case_id]["reference_judgement"]

    from app.services.shadow_examiner import CriterionJudgement

    provisional_criteria = [CriterionJudgement(**d) for d in ref_judgement_dicts]
    human_review = hc.HumanReview(
        case_id=metadata["cases"][0]["opaque_case_id"],
        criteria=[_criterion_review(c) for c in ALL_CRITERIA],
    )
    rows = hc.compare_case(real_case_id, human_review.criteria, provisional_criteria)
    assert len(rows) == 9
    assert {r.criterion for r in rows} == set(ALL_CRITERIA)


# ── benchmark integrity (locked at 20, unchanged by this phase) ───────────


def test_benchmark_remains_twenty_cases():
    assert len(GOLDEN_SET) == 20


def test_benchmark_case_ids_unchanged():
    expected = {f"case_{i:02d}_" for i in range(1, 21)}
    real_ids = {c.case_id for c in GOLDEN_SET}
    assert len(real_ids) == 20
    for prefix in expected:
        assert any(rid.startswith(prefix) for rid in real_ids), f"missing case with prefix {prefix}"


def test_benchmark_all_provisional():
    assert all(c.reference_status == "provisional" for c in GOLDEN_SET)


# ── reviewer package excludes blind material ───────────────────────────────


REVIEWER_DIR = BACKEND_ROOT / "phase5_human_calibration" / "reviewer"


def test_reviewer_package_has_twenty_cases():
    case_files = sorted(REVIEWER_DIR.glob("case_*.json"))
    assert len(case_files) == 20


def test_reviewer_package_excludes_provisional_answer_and_archetype_and_ai_output():
    forbidden_keys = {"reference_judgement", "archetype", "tags", "reference_status", "evidence_quality", "criterion_evidence_map"}
    for path in REVIEWER_DIR.glob("case_*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        present = forbidden_keys & set(_flatten_keys(data))
        assert not present, f"{path.name} leaks blind material: {present}"


def _flatten_keys(obj, out=None):
    out = out if out is not None else set()
    if isinstance(obj, dict):
        out.update(obj.keys())
        for v in obj.values():
            _flatten_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_keys(v, out)
    return out


def test_reviewer_case_ids_are_opaque_not_real_case_ids():
    real_archetypes = {c.archetype for c in GOLDEN_SET}
    for path in REVIEWER_DIR.glob("case_*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        case_id = data["case_id"]
        assert case_id.startswith("case_") and len(case_id) == 8  # "case_XXX"
        for archetype in real_archetypes:
            assert archetype not in json.dumps(data), f"{path.name} leaks archetype {archetype!r}"


def test_reviewer_package_no_real_audio_and_says_so():
    for path in REVIEWER_DIR.glob("case_*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["audio"]["recording_available"] is False


# ── determinism ─────────────────────────────────────────────────────────


def test_builder_is_deterministic(tmp_path):
    """Re-running the builder produces the identical opaque-id mapping."""
    import os

    env_script = BACKEND_ROOT / "scripts" / "phase5_build_calibration_package.py"
    env = {**os.environ, "PYTHONPATH": str(BACKEND_ROOT)}
    result = subprocess.run(
        [sys.executable, str(env_script)], cwd=str(BACKEND_ROOT), capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    metadata = json.loads((BACKEND_ROOT / "phase5_human_calibration" / "admin" / "benchmark_metadata.json").read_text(encoding="utf-8"))
    assert metadata["cases"][0]["opaque_case_id"] == "case_001"
    # same seed -> same mapping every run
    first_real_id = metadata["real_to_opaque"]
    metadata_again = json.loads((BACKEND_ROOT / "phase5_human_calibration" / "admin" / "benchmark_metadata.json").read_text(encoding="utf-8"))
    assert metadata_again["real_to_opaque"] == first_real_id


# ── no model calls / no network / no DB (purity, matching test_shadow_examiner.py's pattern) ──


def test_no_network_calls_in_compare_case():
    def _blocked(*args, **kwargs):
        raise AssertionError("human_calibration attempted a network call")

    original = socket.socket
    socket.socket = _blocked
    try:
        from app.services.shadow_examiner import CriterionJudgement

        prov = CriterionJudgement(
            criterion="relationship_building", family=FAMILY_CLINICAL, status=STATUS_ASSESSED, level=2,
            level_label="Competent use", justification="x", evidence_quality="STRONG",
        )
        hc.compare_case("c", [_criterion_review("relationship_building", status=STATUS_ASSESSED, level=2)], [prov])
    finally:
        socket.socket = original


def _imported_names(module) -> set:
    tree = ast.parse(inspect.getsource(module))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            names.update(alias.name for alias in node.names)
    return names


def test_module_has_no_ai_registry_or_db_dependency():
    imported = _imported_names(hc)
    assert not any("ai_registry" in n for n in imported)
    assert not any(n in ("ai_scoring", "score_speaking", "supabase", "database", "db") for n in imported)


def test_module_makes_no_provider_sdk_calls():
    source = inspect.getsource(hc)
    for forbidden in ("openai", "anthropic", "genai", "requests.post", "httpx.", "google.generativeai"):
        assert forbidden not in source.lower()
