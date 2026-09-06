"""Tests for the Shadow Examiner Calibration Benchmark (Phase 4).

Confirms every golden-set case builds through the real pure pipeline
without error, that its reference judgement is schema-valid (reusing
ShadowResult's own validators), that every cited evidence_id is real
(never fabricated), and that the set covers a distinct archetype per case.
Nothing here calls a model, touches the DB, or imports anything from the
live scoring path.
"""
import pytest

from app.services.examiner_input import ALL_CRITERIA, INDICATORS_BY_CRITERION
from app.services.shadow_examiner_benchmark import (
    GOLDEN_SET,
    cited_evidence_ids,
    export_golden_set_json,
    validate_case,
)

ALL_20_INDICATORS = sorted(
    indicator for indicators in INDICATORS_BY_CRITERION.values() for indicator in indicators
)


def test_golden_set_has_exactly_20_core_cases():
    assert len(GOLDEN_SET) == 20


def test_archetypes_are_unique():
    archetypes = [case.archetype for case in GOLDEN_SET]
    assert len(archetypes) == len(set(archetypes))


def test_case_ids_are_unique():
    ids = [case.case_id for case in GOLDEN_SET]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", GOLDEN_SET, ids=lambda c: c.case_id)
def test_reference_judgement_covers_all_9_criteria(case):
    criteria = {j.criterion for j in case.reference_judgement}
    assert criteria == set(ALL_CRITERIA)


@pytest.mark.parametrize("case", GOLDEN_SET, ids=lambda c: c.case_id)
def test_reference_judgement_is_schema_valid(case):
    # Raises on any orthogonality violation (level set while limited_evidence,
    # wrong level_label, duplicate/missing criterion, etc.) -- same validator
    # a real model response would be checked against.
    validate_case(case)


@pytest.mark.parametrize("case", GOLDEN_SET, ids=lambda c: c.case_id)
def test_no_fabricated_evidence_citations(case):
    for judgement in case.reference_judgement:
        real_ids = cited_evidence_ids(case.criterion_evidence_map, judgement.criterion)
        for pointer in judgement.evidence_refs:
            assert pointer.evidence_id in real_ids, (
                f"{case.case_id}/{judgement.criterion} cites evidence_id "
                f"{pointer.evidence_id!r} not present in that criterion's evidence map"
            )


@pytest.mark.parametrize("case", GOLDEN_SET, ids=lambda c: c.case_id)
def test_no_score_field_leaks_into_examiner_input(case):
    assert "score" not in case.examiner_input.model_dump()


def test_export_produces_valid_json_with_no_python_types(tmp_path):
    out = tmp_path / "golden_set.json"
    export_golden_set_json(str(out))
    import json
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == len(GOLDEN_SET)
    assert {c["case_id"] for c in data} == {c.case_id for c in GOLDEN_SET}


# ── 13 -> 20 expansion: coverage checks (Phase 4 completion) ──────────────

@pytest.mark.parametrize("case", GOLDEN_SET, ids=lambda c: c.case_id)
def test_all_20_clinical_indicators_present_as_evidence_annotations(case):
    """Every case's CriterionEvidenceMap carries all 20 indicator bundles
    (as evidence annotations, i.e. IndicatorEvidence entries -- possibly
    empty/gapped -- never as 20 independent scores; only the 9
    CriterionJudgements are ever scored)."""
    indicators_present = {
        indicator.indicator
        for bundle in case.criterion_evidence_map.clinical
        for indicator in bundle.indicators
    }
    assert indicators_present == set(ALL_20_INDICATORS)


def test_all_20_indicators_have_real_evidence_somewhere_in_benchmark():
    """Across the whole 20-case benchmark, every one of the 20 clinical
    indicators has fired with real (non-empty) evidence at least once --
    not just existed as an empty gap in every case."""
    covered = set()
    for case in GOLDEN_SET:
        for bundle in case.criterion_evidence_map.clinical:
            for indicator in bundle.indicators:
                if indicator.evidence_refs:
                    covered.add(indicator.indicator)
    missing = set(ALL_20_INDICATORS) - covered
    assert not missing, f"indicators with zero real evidence across all 20 cases: {sorted(missing)}"


def test_borderline_adjacent_level_cases_exist():
    borderline = [c for c in GOLDEN_SET if "borderline" in c.tags and "adjacent_level" in c.tags]
    assert len(borderline) >= 5
    boundary_tags = {t for c in borderline for t in c.tags if t.startswith(("clinical_", "linguistic_"))}
    assert {"clinical_3_vs_2", "clinical_2_vs_1", "clinical_1_vs_0", "linguistic_5_vs_4", "linguistic_4_vs_3"} <= boundary_tags


def test_long_consultation_case_exists():
    long_cases = [c for c in GOLDEN_SET if "long_consultation" in c.tags]
    assert len(long_cases) >= 1
    assert len(long_cases[0].transcript) >= 20


def test_conflict_cases_exist():
    conflict_cases = [c for c in GOLDEN_SET if "conflict" in c.tags or c.archetype == "conflicting_evidence"]
    assert len(conflict_cases) >= 2


def test_missing_evidence_cases_exist():
    from app.services.shadow_examiner import STATUS_LIMITED_EVIDENCE
    cases_with_gaps = [
        c for c in GOLDEN_SET
        if any(j.status == STATUS_LIMITED_EVIDENCE for j in c.reference_judgement)
    ]
    assert len(cases_with_gaps) >= 5


def test_audio_and_no_audio_cases_both_exist():
    with_audio = [c for c in GOLDEN_SET if c.examiner_input.audio_availability.audio_available]
    without_audio = [c for c in GOLDEN_SET if not c.examiner_input.audio_availability.audio_available]
    assert with_audio and without_audio


def test_patient_outcome_and_concern_reopened_cases_exist():
    assert any(c.archetype == "concern_reopened" for c in GOLDEN_SET)
    assert any("concern_reopened" in c.tags for c in GOLDEN_SET)
    patient_outcome_cases = [
        c for c in GOLDEN_SET
        for j in c.reference_judgement
        if any(ref.evidence_level == "L4_patient_outcome" for ref in j.evidence_refs)
    ]
    assert patient_outcome_cases


@pytest.mark.parametrize("case", GOLDEN_SET, ids=lambda c: c.case_id)
def test_reference_status_is_provisional(case):
    assert case.reference_status == "provisional"


def test_no_model_or_database_imports_in_benchmark_module():
    """Static guard, not just an absence-of-crash check: the benchmark
    module's actual `import`/`from ... import` statements must never name a
    model-calling or DB-touching module, so a future edit that sneaks one in
    fails CI immediately. Checks real import nodes only (via ast), not
    prose -- the module's own docstrings mention 'ai_registry' by name
    precisely to say it is never imported."""
    import ast
    import inspect
    from app.services import shadow_examiner_benchmark

    source = inspect.getsource(shadow_examiner_benchmark)
    tree = ast.parse(source)
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)

    forbidden = ("ai_registry", "sqlalchemy", "supabase", "openai", "anthropic", "google.generativeai")
    for name in imported_names:
        assert not any(f in name for f in forbidden), f"benchmark module must not import {name!r}"
