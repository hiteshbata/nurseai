# Content Strategy

How SpeakOET's practice content (scenarios, reading passages, listening
scripts, writing prompts) gets created, reviewed, and scaled. Distinct from
[docs/seo/](seo/) and the marketing blog (see [MODULES.md](MODULES.md) →
Website) — this covers the practice content that powers the four OET
modules.

---

## Current content strategy

**Status: V1**

AI-assisted generation, human-reviewed before publish, per item. Not
automated end-to-end — a human (the founder, today) reviews AI-generated
content before it goes live.

- **Generation**: purpose-routed through the AI Model Registry —
  `scenario_card_generation` and `scenario_library_generation` for
  Speaking scenarios (`generate_scenario_library.py`, `seed_scenarios.py`),
  `writing_content_extraction` for Writing prompts,
  `reading_content_rewrite` for Reading passages, `listening_audio_
  segmentation` for Listening scripts.
- **Extraction pipeline**: source material (PDFs, existing OET-format
  documents) goes through OCR (`mistral-ocr` engine via OpenRouter,
  purposes `writing_ocr` / `reading_ocr` / `listening_ocr` /
  `scenario_vision`) before content generation. This has a billing gotcha
  worth knowing: OCR calls are metered separately from text generation
  calls, so a bulk content-extraction pass costs more than the same volume
  of scoring calls would suggest.
- **Deduplication**: unique DB indexes block duplicate scenario/reading/
  listening titles at the database level (live-verified 2026-07-26) — this
  is a hard backstop, not just a review-time check.
- **Review**: manual, founder-performed. No formal workflow or tooling
  beyond direct DB/admin edits today.

**Current gaps by module** (see [MODULES.md](MODULES.md) for full
per-module status):
- Reading: functionality complete, content volume is the constraint.
- Listening: functionality complete, content volume (tests/audio/answers)
  is the constraint; existing AI-generated content still wants a
  spot-check for quality.
- Writing: functionality complete, content volume is the constraint.
- Speaking: 100+ scenarios live, largest content library of the four.

## Future: AI Content Factory

**Status: Future (Phase 4)**

Templated generation at volume, replacing the current one-off
`generate_scenario_library.py`-style scripts with a repeatable pipeline
that can produce content for Reading/Listening/Writing at the same scale
Speaking already has. Human review stays a required step (see "Human
review workflow" below) — this phase scales *generation* volume, not
*publish* trust. Depends on nothing architecturally new; it's a scaling
and tooling investment on top of the existing AI Model Registry purposes.

## Knowledge tagging

**Status: Future (Phase 4)**

Tag every content item against the skill-tag taxonomy the Learner Brain
uses (`skill_graph.py`'s `skill_tag` values, e.g. `"reading:B"`,
`"speaking:fluency"`), so a detected weakness (Phase 3) can route a
learner to specific content, not just point them at a module. Hard
dependency: the skill-tag taxonomy needs to be stable (Phase 3 landed)
before tagging content against it is worth doing — tagging against a
taxonomy that's still shifting means re-tagging later.

## Human review workflow

**Status: V1 (informal) / Future (formalized, Phase 4)**

Today: the founder reviews each AI-generated item before publish, with no
dedicated tooling — this is a direct, ad hoc pass. As content volume grows
under the AI Content Factory, this needs to become a first-class workflow
(a review queue, approve/reject/edit states) rather than staying an
informal founder task, or content velocity will bottleneck on one person's
available hours. No tooling or workflow design exists yet — don't build
review tooling ahead of the volume that would justify it (Phase 4).

## Future automation

**Status: Future (Post PMF, Phase 5, loosely scoped)**

Reducing the human-review step's role over time — e.g. automated quality
scoring of generated content as a pre-filter before human review, so
reviewers see fewer, higher-quality candidates rather than a raw firehose.
Not scoped in any detail; do not build against this section, it exists to
flag the direction, not to specify it.
