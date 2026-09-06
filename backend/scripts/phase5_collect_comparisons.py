"""Phase 5 -- collects submitted human reviews and diffs each against the
provisional reference via `human_calibration.compare_case()`.

Reads every `*.json` file in `phase5_human_calibration/submitted/` (the
convention `REVIEWER_README` in `phase5_build_calibration_package.py`
documents: `case_XXX__reviewerY.json`), validates each against `HumanReview`
(malformed or unrecognized-case_id files are skipped with a reason, not
fatal), and writes an aggregate `comparison_report.json` / `.csv` to
`phase5_human_calibration/admin/`.

OFFLINE ONLY: no model call, no ai_registry, no DB, no network -- reads only
JSON files already on disk. Re-running is idempotent; output reflects
whatever is currently in submitted/ at run time.

Usage: venv/Scripts/python.exe scripts/phase5_collect_comparisons.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from app.services.human_calibration import HumanReview, compare_case
from app.services.shadow_examiner import CriterionJudgement

ROOT = Path(__file__).resolve().parent.parent
SUBMITTED_DIR = ROOT / "phase5_human_calibration" / "submitted"
ADMIN_DIR = ROOT / "phase5_human_calibration" / "admin"


def collect(submitted_dir: Path = SUBMITTED_DIR, admin_dir: Path = ADMIN_DIR) -> Tuple[int, List[Dict[str, Any]], List[Dict[str, Any]]]:
    submitted_dir.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((admin_dir / "benchmark_metadata.json").read_text(encoding="utf-8"))
    provisional = json.loads((admin_dir / "provisional_references.json").read_text(encoding="utf-8"))
    opaque_to_real: Dict[str, str] = metadata["opaque_to_real"]

    rows: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    loaded = 0

    for path in sorted(submitted_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            review = HumanReview(**data)
        except (json.JSONDecodeError, ValidationError) as exc:
            skipped.append({"file": path.name, "reason": str(exc)})
            continue

        real_case_id = opaque_to_real.get(review.case_id)
        if real_case_id is None:
            skipped.append({"file": path.name, "reason": f"unknown case_id {review.case_id!r}"})
            continue

        provisional_criteria = [CriterionJudgement(**d) for d in provisional[real_case_id]["reference_judgement"]]
        comparison_rows = compare_case(real_case_id, review.criteria, provisional_criteria)
        loaded += 1
        for row in comparison_rows:
            entry = row.model_dump(mode="json")
            entry["opaque_case_id"] = review.case_id
            entry["reviewer_id"] = review.reviewer_id
            entry["review_status"] = review.review_status
            entry["source_file"] = path.name
            rows.append(entry)

    (admin_dir / "comparison_report.json").write_text(
        json.dumps({"reviews_loaded": loaded, "files_skipped": skipped, "rows": rows}, indent=2),
        encoding="utf-8",
    )
    if rows:
        with (admin_dir / "comparison_report.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    return loaded, skipped, rows


if __name__ == "__main__":
    loaded, skipped, rows = collect()
    print(f"Loaded {loaded} review file(s), skipped {len(skipped)}, wrote {len(rows)} comparison rows to {ADMIN_DIR}")
    for s in skipped:
        print(f"  SKIPPED {s['file']}: {s['reason']}")
