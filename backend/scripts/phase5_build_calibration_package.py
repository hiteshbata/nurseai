"""Phase 5 -- builds the Human Calibration Package from the locked 20-case
shadow_examiner_benchmark.GOLDEN_SET.

OFFLINE ONLY: no model call, no ai_registry, no DB, no network. Reads the
in-code benchmark (pure Python objects) and writes plain JSON/Markdown files
under phase5_human_calibration/. Re-running this script is idempotent and
deterministic (fixed shuffle seed) -- it is the one source of truth for
regenerating the package, never hand-edited output.

Usage: venv/Scripts/python.exe scripts/phase5_build_calibration_package.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List

from app.services.examiner_input import ALL_CRITERIA, CLINICAL_CRITERIA, INDICATORS_BY_CRITERION, LINGUISTIC_CRITERIA
from app.services.human_calibration import ComparisonRow, blank_review_template
from app.services.shadow_examiner import CLINICAL_LEVEL_LABELS
from app.services.shadow_examiner_benchmark import GOLDEN_SET, export_golden_set_json

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = ROOT / "phase5_human_calibration"
REVIEWER_DIR = PACKAGE_DIR / "reviewer"
ADMIN_DIR = PACKAGE_DIR / "admin"

# Fixed seed -> deterministic shuffle, never re-derived from case content
# (task Step 17: neutral order that doesn't reveal weak/borderline grouping).
SHUFFLE_SEED = 20260829


def _opaque_case_ids(real_case_ids: List[str]) -> Dict[str, str]:
    shuffled = list(real_case_ids)
    random.Random(SHUFFLE_SEED).shuffle(shuffled)
    return {real_id: f"case_{i + 1:03d}" for i, real_id in enumerate(shuffled)}


def _reviewer_case_material(case, opaque_id: str) -> Dict[str, Any]:
    """Only what task Step 5/23 allow a blind reviewer to see: scenario
    context, transcript, and an honest audio-availability note. No
    reference_judgement, no archetype, no tags, no CriterionEvidenceMap, no
    detector labels, no real case_id."""
    ei = case.examiner_input
    sc = ei.scenario_context
    return {
        "case_id": opaque_id,
        "scenario": {
            "title": sc.title,
            "setting": sc.setting,
            "difficulty": sc.difficulty,
            "specialty": sc.specialty,
            "nurse_tasks": sc.nurse_tasks,
            "patient_name": sc.patient_name,
            "patient_age": sc.patient_age,
            "patient_condition": sc.patient_condition,
            "patient_mood": sc.patient_mood,
            "patient_background": sc.patient_background,
            "patient_concerns": sc.patient_concerns,
            "hidden_information_items": sc.hidden_information_items,
            "emotional_triggers": sc.emotional_triggers,
        },
        "transcript": [{"turn_index": t.turn_index, "role": t.role, "content": t.content} for t in ei.transcript],
        "audio": {
            "recording_available": False,
            "note": (
                "This benchmark contains no real audio recordings for any case. Base "
                "Intelligibility and Fluency on genuine acoustic evidence only; since none "
                "exists here, mark both status=\"limited_evidence\", level=null for every "
                "case in this package. Do not infer pronunciation or spoken fluency from "
                "transcript spelling or word choice."
            ),
        },
    }


def _reviewer_case_markdown(material: Dict[str, Any]) -> str:
    s = material["scenario"]
    lines = [f"# Case {material['case_id']}", ""]
    lines += ["## Scenario", ""]
    lines += [f"- **Setting:** {s['setting']}", f"- **Difficulty:** {s['difficulty']}", f"- **Specialty:** {s['specialty']}"]
    lines += [f"- **Nurse tasks:** {', '.join(s['nurse_tasks']) or '(none listed)'}"]
    lines += [
        f"- **Patient:** {s['patient_name'] or '(unnamed)'}, age {s['patient_age'] or '?'}, "
        f"{s['patient_condition'] or '(condition not specified)'}, mood: {s['patient_mood'] or '(not specified)'}"
    ]
    if s["patient_background"]:
        lines += [f"- **Background:** {s['patient_background']}"]
    if s["patient_concerns"]:
        lines += [f"- **Patient concerns/questions to raise:** {', '.join(s['patient_concerns'])}"]
    if s["hidden_information_items"]:
        lines += [f"- **Information the patient withholds unless asked:** {', '.join(s['hidden_information_items'])}"]
    if s["emotional_triggers"]:
        lines += [f"- **Emotional triggers:** {', '.join(s['emotional_triggers'])}"]
    lines += ["", "## Transcript", ""]
    for t in material["transcript"]:
        lines += [f"**[{t['turn_index']}] {t['role'].upper()}:** {t['content']}", ""]
    lines += ["## Audio", "", material["audio"]["note"], ""]
    return "\n".join(lines)


CRITERION_LABELS = {
    "intelligibility": "INTELLIGIBILITY",
    "fluency": "FLUENCY",
    "appropriateness_of_language": "APPROPRIATENESS_OF_LANGUAGE",
    "resources_of_grammar_and_expression": "RESOURCES_OF_GRAMMAR_AND_EXPRESSION",
    "relationship_building": "RELATIONSHIP_BUILDING",
    "patient_perspective": "PATIENT_PERSPECTIVE",
    "providing_structure": "PROVIDING_STRUCTURE",
    "information_gathering": "INFORMATION_GATHERING",
    "information_giving": "INFORMATION_GIVING",
}


def _framework_summary() -> Dict[str, Any]:
    return {
        "linguistic_criteria": {
            CRITERION_LABELS[c]: {"scale": "0-6"} for c in LINGUISTIC_CRITERIA
        },
        "clinical_criteria": {
            CRITERION_LABELS[c]: {
                "scale": "0-3",
                "level_labels": CLINICAL_LEVEL_LABELS,
                "indicators": {i: None for i in INDICATORS_BY_CRITERION[c]},
            }
            for c in CLINICAL_CRITERIA
        },
    }


def build() -> None:
    REVIEWER_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_DIR.mkdir(parents=True, exist_ok=True)

    real_ids = [c.case_id for c in GOLDEN_SET]
    opaque_by_real = _opaque_case_ids(real_ids)
    real_by_opaque = {v: k for k, v in opaque_by_real.items()}

    provisional_references: Dict[str, Any] = {}
    metadata_rows: List[Dict[str, Any]] = []

    for case in GOLDEN_SET:
        opaque_id = opaque_by_real[case.case_id]

        material = _reviewer_case_material(case, opaque_id)
        (REVIEWER_DIR / f"{opaque_id}.json").write_text(json.dumps(material, indent=2), encoding="utf-8")
        (REVIEWER_DIR / f"{opaque_id}.md").write_text(_reviewer_case_markdown(material), encoding="utf-8")

        provisional_references[case.case_id] = {
            "opaque_case_id": opaque_id,
            "archetype": case.archetype,
            "tags": case.tags,
            "reference_status": case.reference_status,
            "reference_judgement": [j.model_dump(mode="json") for j in case.reference_judgement],
        }
        metadata_rows.append({
            "opaque_case_id": opaque_id,
            "real_case_id": case.case_id,
            "archetype": case.archetype,
            "tags": case.tags,
            "reference_status": case.reference_status,
        })

    template = blank_review_template().model_dump(mode="json")
    (REVIEWER_DIR / "REVIEW_TEMPLATE.json").write_text(json.dumps(template, indent=2), encoding="utf-8")
    (REVIEWER_DIR / "CRITERIA_FRAMEWORK.json").write_text(json.dumps(_framework_summary(), indent=2), encoding="utf-8")
    (REVIEWER_DIR / "README.md").write_text(REVIEWER_README, encoding="utf-8")

    (ADMIN_DIR / "benchmark_metadata.json").write_text(json.dumps({
        "benchmark_size": len(GOLDEN_SET),
        "shuffle_seed": SHUFFLE_SEED,
        "cases": sorted(metadata_rows, key=lambda r: r["opaque_case_id"]),
        "real_to_opaque": opaque_by_real,
        "opaque_to_real": real_by_opaque,
    }, indent=2), encoding="utf-8")
    (ADMIN_DIR / "provisional_references.json").write_text(json.dumps(provisional_references, indent=2), encoding="utf-8")
    (ADMIN_DIR / "comparison_schema.json").write_text(json.dumps(ComparisonRow.model_json_schema(), indent=2), encoding="utf-8")
    (ADMIN_DIR / "README.md").write_text(ADMIN_README, encoding="utf-8")

    # Refresh the stale export artifact (was 13 cases from before the 13->20
    # expansion) so it matches the locked 20-case benchmark -- a derived
    # artifact freshness fix, not a change to the underlying cases.
    export_golden_set_json(str(ROOT / "qa-artifacts" / "phase4_shadow_examiner_golden_set.json"))


REVIEWER_README = """# SpeakOET Shadow Examiner -- Human Calibration Review

## Purpose

You are independently assessing 20 simulated OET Speaking sub-test consultations
against the **official OET Speaking sub-test assessment criteria** -- the same
framework a real OET examiner uses. Your judgement is the reference this project
is calibrating an experimental AI examiner against. There is no existing "correct
answer" you are trying to match; your independent judgement IS the data point.

## What you will see, per case

- `case_XXX.json` / `case_XXX.md` -- scenario context (setting, patient, tasks,
  concerns) and the full transcript. Turn indices are numbered from 0.
- `CRITERIA_FRAMEWORK.json` -- the 9 official criteria, their scales, and (for the
  5 clinical criteria) the indicators (A1-E5) that may inform your judgement.
- `REVIEW_TEMPLATE.json` -- copy this once per case per reviewer and fill it in.

## What you will NOT see (by design)

No AI-generated score, no internal detector output, no "expected" or reference
judgement, and no label revealing which archetype a case represents (weak/strong/
borderline/conflict/etc). Case IDs are randomized and opaque. This is intentional:
we are testing whether our evidence architecture captures what a human independently
notices, not whether you can guess our system's answer.

## The 9 criteria

**Linguistic (0-6 each):** INTELLIGIBILITY, FLUENCY, APPROPRIATENESS_OF_LANGUAGE,
RESOURCES_OF_GRAMMAR_AND_EXPRESSION.

**Clinical communication (0-3 each, one shared scale):** RELATIONSHIP_BUILDING,
PATIENT_PERSPECTIVE, PROVIDING_STRUCTURE, INFORMATION_GATHERING, INFORMATION_GIVING.
Clinical scale: 3 = Adept use, 2 = Competent use, 1 = Partially effective use,
0 = Ineffective use.

Each clinical criterion has named indicators (A1-A4, B1-B3, C1-C3, D1-D5, E1-E5,
listed in `CRITERIA_FRAMEWORK.json`) that are evidence FOR that one criterion --
never separate scores of their own. `indicator_notes` on the review template is
optional and only for noting which indicators informed your judgement.

## Audio

This benchmark contains **no real audio recordings** for any case. For
INTELLIGIBILITY and FLUENCY specifically: mark `status="limited_evidence"`,
`level=null` on every case. Do not infer pronunciation or spoken fluency from
transcript spelling, grammar, or word choice -- that is a different skill than
acoustic delivery and is explicitly not legitimate evidence for these two criteria.

## How to fill in a review

For every one of the 9 criteria, provide:

- `level`: the score (0-6 linguistic / 0-3 clinical), or `null`.
- `status`: `"assessed"` (you gave a level), `"limited_evidence"` (you could not
  responsibly assess this criterion from what's available -- level MUST be null),
  or `"evidence_conflict_unresolved"` (the transcript gives you genuinely
  conflicting signals you cannot resolve -- level MUST be null).
- `justification`: a short, specific reason citing what you observed.
- `evidence_refs`: cite the `turn_index` values that informed your judgement. You
  do not need to quote text at length, and you do not need to use any of this
  project's internal evidence labels.
- `limitations`: anything that limited your confidence (e.g. "very short
  consultation", "no evidence either way for this criterion").

**Never force a zero.** If you genuinely cannot assess a criterion, use
`status="limited_evidence"` and `level=null` -- missing evidence is not the same
as poor performance, and a criterion with nothing to go on is not automatically
a failing score.

## Independence rules

- Assess each case on its own -- do not compare cases to each other or try to
  infer a "pattern" across the set.
- Judge only what's in front of you. Do not assume missing evidence means poor
  performance, and do not assume present evidence means good performance either
  -- weigh what's actually there.
- Distinguish a genuinely borderline performance (you can defend a level, but a
  reasonable colleague might pick the adjacent one) from missing evidence (you
  cannot defend any level at all). These get different `status` values.
- Do not try to guess or match any "expected" or "correct" answer. None is
  available to you, and none should influence you even if you think you can
  guess one.

## Reviewer identity

`reviewer_id` in the template is optional. If you provide one, use a pseudonym
or short code, not your name, email, or any other personal identifier -- none of
that is required or wanted for this exercise.

## Submitting

Save one filled-in review JSON per case you review, named however your
administrator asks (e.g. `case_007__reviewerA.json`). You do not need to review
every case; partial coverage is fine.
"""

ADMIN_README = """# Phase 5 Calibration Package -- Administrator Notes

This directory (and the sibling `reviewer/` directory) is generated by
`scripts/phase5_build_calibration_package.py` from the locked 20-case
`shadow_examiner_benchmark.GOLDEN_SET`. Do not hand-edit generated files --
re-run the script instead.

- `benchmark_metadata.json` -- opaque_case_id <-> real_case_id mapping, archetype,
  tags, reference_status. **Never share this file with a blind reviewer** -- it
  is the de-anonymization key.
- `provisional_references.json` -- each case's existing provisional reference
  judgement (hand-authored, `reference_status="provisional"`, NOT human ground
  truth -- see `shadow_examiner_benchmark.py`'s own module docstring). Kept
  separate from any human review; comparing the two is the point of Phase 5+.
- `comparison_schema.json` -- the JSON Schema for `ComparisonRow`
  (`app/services/human_calibration.py`), the output shape of
  `compare_case()`. Use `compare_case(real_case_id, human_review.criteria,
  provisional_reference_judgement)` to diff a collected `HumanReview` against
  the provisional reference for that case; look up `real_case_id` from a
  submitted review's opaque `case_id` via `benchmark_metadata.json`.

No inter-rater threshold or acceptance criterion is defined anywhere in this
package -- none is invented per the task's explicit instruction. `agreement_bucket`
on each `ComparisonRow` is descriptive only (exact / adjacent / large_disagreement
/ both_limited_evidence / status_mismatch), not a pass/fail verdict.

## Collecting completed reviews

Ask each reviewer to save one filled-in `HumanReview` JSON per case into the
sibling `submitted/` directory, named `<opaque_case_id>__<reviewer_id>.json`
(e.g. `case_007__reviewer_a.json`) -- `reviewer_id` may differ from the
`reviewer_id` field inside the file. Once you have some or all reviews in
`submitted/`, run:

    venv/Scripts/python.exe scripts/phase5_collect_comparisons.py

This validates every file against `HumanReview` (malformed files or unknown
`case_id`s are skipped with a reason, never fatal), diffs each valid review
against its case's provisional reference via `compare_case()`, and writes
`comparison_report.json` / `comparison_report.csv` here in `admin/` -- one
row per reviewer per criterion per case. Re-running it after more reviews
arrive regenerates both files from whatever is currently in `submitted/`.
"""


if __name__ == "__main__":
    build()
    print(f"Wrote {len(GOLDEN_SET)} reviewer cases + admin package to {PACKAGE_DIR}")
