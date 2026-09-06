# SpeakOET Shadow Examiner -- Human Calibration Review

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
