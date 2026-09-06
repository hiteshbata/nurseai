"""Tests for scripts/phase5_collect_comparisons.py -- the submitted-review
collection + comparison tooling (Phase 5 Steps 6/7). Pure/offline, isolated
via tmp_path -- never touches the real submitted/ or admin/ directories.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import sys

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT / "scripts"))

from phase5_collect_comparisons import collect  # noqa: E402

REAL_ADMIN_DIR = BACKEND_ROOT / "phase5_human_calibration" / "admin"


@pytest.fixture
def admin_dir(tmp_path):
    dest = tmp_path / "admin"
    dest.mkdir()
    shutil.copy(REAL_ADMIN_DIR / "benchmark_metadata.json", dest / "benchmark_metadata.json")
    shutil.copy(REAL_ADMIN_DIR / "provisional_references.json", dest / "provisional_references.json")
    return dest


def _blank_criteria():
    from app.services.examiner_input import ALL_CRITERIA, LINGUISTIC_CRITERIA
    from app.services.shadow_examiner import FAMILY_CLINICAL, FAMILY_LINGUISTIC, STATUS_LIMITED_EVIDENCE

    return [
        {
            "criterion": c,
            "family": FAMILY_LINGUISTIC if c in LINGUISTIC_CRITERIA else FAMILY_CLINICAL,
            "status": STATUS_LIMITED_EVIDENCE,
            "level": None,
            "justification": "no evidence in transcript",
        }
        for c in ALL_CRITERIA
    ]


def test_collect_loads_valid_submission_and_produces_rows(tmp_path, admin_dir):
    metadata = json.loads((admin_dir / "benchmark_metadata.json").read_text(encoding="utf-8"))
    opaque_id = metadata["cases"][0]["opaque_case_id"]

    submitted = tmp_path / "submitted"
    submitted.mkdir()
    review = {"case_id": opaque_id, "reviewer_id": "reviewer_a", "criteria": _blank_criteria()}
    (submitted / f"{opaque_id}__reviewer_a.json").write_text(json.dumps(review), encoding="utf-8")

    loaded, skipped, rows = collect(submitted_dir=submitted, admin_dir=admin_dir)

    assert loaded == 1
    assert skipped == []
    assert len(rows) == 9
    assert all(r["opaque_case_id"] == opaque_id and r["reviewer_id"] == "reviewer_a" for r in rows)
    report = json.loads((admin_dir / "comparison_report.json").read_text(encoding="utf-8"))
    assert report["reviews_loaded"] == 1
    assert (admin_dir / "comparison_report.csv").exists()


def test_collect_skips_malformed_and_unknown_case_files(tmp_path, admin_dir):
    submitted = tmp_path / "submitted"
    submitted.mkdir()
    (submitted / "broken.json").write_text("{not valid json", encoding="utf-8")
    (submitted / "unknown_case.json").write_text(
        json.dumps({"case_id": "case_999", "criteria": _blank_criteria()}), encoding="utf-8",
    )
    (submitted / "missing_criteria.json").write_text(
        json.dumps({"case_id": "case_001", "criteria": _blank_criteria()[:3]}), encoding="utf-8",
    )

    loaded, skipped, rows = collect(submitted_dir=submitted, admin_dir=admin_dir)

    assert loaded == 0
    assert rows == []
    assert {s["file"] for s in skipped} == {"broken.json", "unknown_case.json", "missing_criteria.json"}


def test_collect_supports_multiple_independent_reviewers_same_case(tmp_path, admin_dir):
    metadata = json.loads((admin_dir / "benchmark_metadata.json").read_text(encoding="utf-8"))
    opaque_id = metadata["cases"][0]["opaque_case_id"]
    submitted = tmp_path / "submitted"
    submitted.mkdir()
    for reviewer in ("reviewer_a", "reviewer_b"):
        review = {"case_id": opaque_id, "reviewer_id": reviewer, "criteria": _blank_criteria()}
        (submitted / f"{opaque_id}__{reviewer}.json").write_text(json.dumps(review), encoding="utf-8")

    loaded, skipped, rows = collect(submitted_dir=submitted, admin_dir=admin_dir)

    assert loaded == 2
    assert skipped == []
    reviewer_ids = {r["reviewer_id"] for r in rows}
    assert reviewer_ids == {"reviewer_a", "reviewer_b"}


def test_collect_empty_submitted_dir_is_a_noop(tmp_path, admin_dir):
    submitted = tmp_path / "submitted"
    loaded, skipped, rows = collect(submitted_dir=submitted, admin_dir=admin_dir)
    assert (loaded, skipped, rows) == (0, [], [])
    assert not (admin_dir / "comparison_report.csv").exists()
