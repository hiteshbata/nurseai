# Content Foundation

**Status: Proposal (Sprint 1.5, design-only — not yet implemented).** No
schema or application code changed to produce this document. The Content
Foundation provides standards for future content improvements. Adaptive
Reading V1 proceeds using the existing content library, while metadata
normalization and content enhancement continue as parallel work — this
doc is that standard, not a gate in front of Adaptive Reading. See
[ROADMAP.md](ROADMAP.md) Phase 4 and
[CONTENT_STRATEGY.md](CONTENT_STRATEGY.md) for how this fits the existing
content pipeline.

Numbers below are a live count against the production Supabase project
(`lgwaiwasnjjohqkeizdz`) taken 2026-08-08.

---

## 1. Current content audit

### What exists today

| Module | Item table | Count | Sub-items | Count |
|---|---|---|---|---|
| Speaking | `scenarios` (`module='speaking'`) | 144 | — | — |
| Writing | `scenarios` (`module='writing'`) | 26 | `questions` (`module='writing'`) | 5 (1 each: case_notes, handover_notes, incident_report, patient_education, referral_letter) |
| Reading | `reading_tests` → `reading_passages` | 16 tests / 127 passages (Part A 16, B 84, C 27) | `questions` (`module='reading'`) | 624 (mcq 408, short_answer 212, comprehension 4) |
| Listening | `listening_tests` → `listening_sections` | 26 tests / 254 sections (Part A 52, B 150, C 52) | `questions` (`module='listening'`) | 1,095 (short_answer 624, mcq 467, audio_comprehension 4) |
| Mock Test | `mock_tests` (packs) | 13 packs, each bundling 1 listening test + 1 reading test + 1 writing scenario + 2 speaking scenarios | — | — |
| Vocabulary | `vocab_cards` | 0 rows (table exists, no content) | — | — |
| Grammar | none | 0 (no table exists) | — | — |

Reading and Listening are the deepest content libraries by question count
(624 and 1,095 respectively) — consistent with [MODULES.md](MODULES.md)'s
note that both are "functionality complete, content volume is the
constraint" is backwards for raw question count; the real constraint is
**test/passage variety and difficulty spread**, not question count, per the
gaps below.

### Biggest gaps

1. **Zero beginner content in Reading and Listening.** Every
   `reading_passages` and `listening_sections` row is `intermediate` (119 /
   250) or `advanced` (8 / 4) — no `easy`/`beginner` tier exists in either
   module. A learner who can't yet handle intermediate text has nowhere to
   start in either module.
2. **Inconsistent difficulty vocabulary across modules.** Speaking uses
   `easy` / `medium` / `hard` / `intermediate` (four values, two of them
   synonyms) with no visible scale ordering. Writing uses only `easy` /
   `medium`. Reading/Listening use `intermediate` / `advanced`. There is no
   shared difficulty ladder today — see §4.
3. **Inconsistent (duplicated) specialty tags on Speaking.** `scenarios.
   specialty` for Speaking has 14 distinct values that are really ~9
   specialties written two ways: `emergency` / `Emergency / Acute Care`,
   `general` / `General / Internal Medicine`, `mental_health` / `Mental
   Health`, `paediatric` / `Paediatrics`. A specialty filter or
   recommendation query written against this column today undercounts
   silently. Writing has no specialty tagging at all (`specialty` is
   null-equivalent — the column doesn't exist on Writing's rows in any
   meaningful way).
4. **No skill-tag metadata on any content item.** `skill_graph.py` already
   defines a skill-tag taxonomy (`"reading:B"`, `"speaking:fluency"`,
   `"listening:accent:UK"`) for *user* skill stats, but no content item
   carries a matching tag. This is the named gap in
   [CONTENT_STRATEGY.md](CONTENT_STRATEGY.md) → Knowledge tagging. Adaptive
   Reading V1 proceeds on the existing content library without it;
   tagging content against this taxonomy is parallel work that improves
   routing precision over time, not a precondition to shipping.
5. **Vocabulary and Grammar have no content and, for Grammar, no schema.**
   `vocab_cards` exists but is empty. There is no grammar table at all —
   Grammar has never been scoped as a module. Both are named in this
   sprint's taxonomy ask (§2) but are 0% built.
6. **No `ai_generated` / `human_reviewed` flags on any content row.**
   [CONTENT_STRATEGY.md](CONTENT_STRATEGY.md) states all content today is
   AI-generated and founder-reviewed before publish, but that fact isn't
   recorded per item — there's no way to query "which of the 170 Speaking
   scenarios were reviewed" after the fact.
7. **No estimated-duration field anywhere.** Timing exists implicitly (OET's
   real per-part timing, see
   [reference: OET Reading official format]) but isn't stored per item, so
   Mock Test pack assembly and any future "practice in your next 15
   minutes" surface can't query for it.
8. **Auxiliary tables unused.** `medical_terms` (0 rows) and `reading_notes`
   (0 rows) exist but hold nothing — either dead schema or a
   not-yet-started feature; worth a decision either way, out of scope here.

---

## 2. Content taxonomy

A **content item** is the unit a learner practices once: one Speaking
scenario, one Reading passage, one Listening section, one Writing task, one
Vocabulary card, one Grammar drill. Each belongs to exactly one module and
(where the module has one) one OET part.

### Speaking
- Unit: scenario (interlocutor card + nurse card + scoring criteria).
- Sub-structure: none below scenario — a scenario is atomic.
- Existing volume: 144.

### Reading
- Unit: passage, grouped under a test.
- Sub-structure: OET Part A (4 short texts, ~15 min) / Part B (6 texts, MCQ)
  / Part C (2 texts, MCQ) — see
  [reference: OET Reading official format] for the official timing/count
  this maps onto.
- Existing volume: 127 passages / 16 tests.

### Listening
- Unit: section, grouped under a test.
- Sub-structure: Part A (consultation extract, note completion) / Part B
  (short workplace extracts, MCQ) / Part C (presentation, MCQ) — mirrors
  Reading's Part A/B/C split, different task types per the real OET format.
- Existing volume: 254 sections / 26 tests.

### Writing
- Unit: scenario (task type + case notes + reference response).
- Sub-structure: task type — `case_notes`, `handover_notes`,
  `incident_report`, `patient_education`, `referral_letter` (5 types seen
  today).
- Existing volume: 26.

### Vocabulary (proposed, 0 content today)
- Unit: term card — clinical term, plain-English definition, one example
  sentence in an OET-register context, optionally an audio pronunciation.
- Sub-structure: grouped by medical specialty (reuse Speaking's normalized
  specialty list, §1 finding 3) and by the four modules it's most relevant
  to (a term can tag more than one — e.g. a term used in both a Speaking
  roleplay and a Reading passage).
- This module has a table (`vocab_cards`) but no rows and no shipped UI —
  building it out is a content-and-product decision beyond this sprint's
  scope (documentation only), not something to start on the strength of
  this doc alone.

### Grammar (proposed, 0 content and no schema today)
- Unit: drill item — a grammar point relevant to clinical writing/speaking
  register (e.g. passive voice in handover notes, modal verbs for advice-
  giving), one explanation, 3-5 practice items.
- Sub-structure: grouped by the module where the grammar point is most
  tested (Writing register issues vs. Speaking spoken-grammar criterion vs.
  general).
- No table exists. Scoping and building this module is future work, not
  part of this sprint.

---

## 3. Metadata standard

Every content item, across all six areas above, should carry this field
set. "Today" marks whether the field already exists as a DB column;
"Proposed" fields are new and would need a migration if this proposal is
approved — no migration is written or applied as part of this sprint.

| Field | Today | Notes |
|---|---|---|
| **Skill tags** | Proposed | Array of tags matching `skill_graph.py`'s existing taxonomy shape (`"reading:B"`, `"speaking:fluency"`) — improves routing precision once populated. Reuses the taxonomy already live for user skill stats rather than inventing a second one. Not a precondition for Adaptive Reading V1, which proceeds on the existing content library. |
| **Difficulty** | Partial (`scenarios.difficulty`, `reading_passages.difficulty`, `listening_sections.difficulty` — inconsistent values) | Normalize onto the 5-tier ladder in §4. |
| **Topic** | Missing | Free-text or small controlled vocabulary (e.g. "post-op pain management", "discharge planning") — one level more specific than specialty. |
| **Medical specialty** | Partial (`scenarios.specialty` — Speaking only, inconsistent casing/format, §1 finding 3) | Normalize to one canonical list (see §1) and extend the column to Reading/Listening/Writing. |
| **Learning objectives** | Missing | 1-3 short statements of what practicing this item builds (e.g. "practice giving bad news with empathy"). Drives search/recommendation copy, not just tagging. |
| **OET criteria** | Partial (`scenarios.scoring_criteria` jsonb, Speaking only) | Which official rubric criteria this item exercises — already modeled for Speaking's 9-criteria rubric; Writing/Reading/Listening need the equivalent mapped to their own rubrics. |
| **Estimated duration** | Missing | Minutes, matching real OET part timing (§1 finding 7) — powers Mock Test pack assembly and any future time-boxed practice surface. |
| **AI generated?** | Missing (true for ~100% of current content per [CONTENT_STRATEGY.md](CONTENT_STRATEGY.md), just not recorded) | Boolean. Cheap field, closes §1 finding 6. |
| **Human reviewed?** | Missing | Boolean + reviewer identity + review date. Also feeds §6's workflow status. |

Design intent: this is additive metadata on existing tables (`scenarios`,
`reading_passages`, `listening_sections`), not a new content model. It
follows the same "one column, not a framework" pattern the schema already
uses (see ADR-005 in [DECISIONS.md](DECISIONS.md) on the `product` column
precedent) — no per-module metadata tables, no EAV pattern.

---

## 4. Difficulty model

Five tiers, replacing the inconsistent easy/medium/hard/intermediate/
advanced mix found in §1:

1. **Beginner** — short items, high-frequency vocabulary, one clear task.
   No module has content here today (§1 finding 1) — this is the tier that
   needs building before Reading/Listening can serve a learner who isn't
   already intermediate.
2. **Elementary** — slightly longer items, some clinical vocabulary
   introduced with context support.
3. **Intermediate** — current default tier for most existing content
   (Reading 119 passages, Listening 250 sections sit here).
4. **Advanced** — current top tier for Reading/Listening (8 passages, 4
   sections) and Speaking's `hard`.
5. **Exam Ready** — full OET timing, no scaffolding, mixed specialty —
   distinguishes "can do an advanced single skill" from "can sit the real
   exam." Currently unrepresented in the data; Mock Test packs are the
   closest existing approximation but aren't tagged as this tier explicitly.

Migration mapping for existing values (design reference only, not applied):
`easy`→Beginner/Elementary (needs per-item judgment, not a blind rename),
`medium`→Intermediate, `intermediate`→Intermediate, `hard`/`advanced`→
Advanced. Nothing maps automatically to Exam Ready or the empty Beginner
tier — that's new content, not a relabel.

Progression is meant to gate content recommendations (a learner doesn't see
Exam Ready until Advanced items show consistent scores), not to gate access
outright — plan access stays governed by the existing subscription tiers,
untouched by this proposal.

---

## 5. Content quality checklist

Applies before any item moves from Review to Approved (§6). Written to be
checkable by a single reviewer (today: the founder) in a few minutes per
item, not a heavyweight process — consistent with
[CONTENT_STRATEGY.md](CONTENT_STRATEGY.md)'s "no dedicated tooling beyond
direct DB/admin edits today."

1. **Clinically accurate.** No fabricated drug names/dosages, no unsafe
   advice presented as correct, terminology matches real nursing practice.
2. **OET-register appropriate.** Language matches the real exam's tone —
   professional, healthcare-context English, not generic conversational
   English.
3. **Rubric-mappable.** The item's scoring criteria (§3, OET criteria field)
   actually exercise what they claim to — a Speaking scenario tagged for
   "Empathy" needs a moment that genuinely tests empathy, not just contains
   the word.
4. **Timing matches the real exam.** Passage/section length and expected
   duration are within the official OET Part A/B/C bounds (see
   [reference: OET Reading official format]), not arbitrarily long/short.
5. **No duplicate title.** Already enforced at the DB level by the unique
   indexes from the dedupe fix (live-verified 2026-07-26, see
   [project: Dedupe content titles fixed] in memory) — this is a backstop,
   not the primary check; a reviewer should still eyeball for
   near-duplicate content the title-uniqueness check wouldn't catch.
6. **Metadata complete.** All §3 fields populated, difficulty on the §4
   ladder, specialty from the normalized list (not a raw AI-generated
   string).
7. **No PII or real patient data.** All scenarios are synthetic.
8. **Grammatically clean.** Especially for Writing reference responses and
   Listening transcripts — errors here undermine the AI scoring baseline
   for that item.

---

## 6. AI content workflow

Draft → Review → Approval → Publish, mapped onto what already exists:

**Draft.** Generated through the AI Model Registry's content-generation
purposes (`scenario_card_generation`, `scenario_library_generation`,
`writing_content_extraction`, `reading_content_rewrite`,
`listening_audio_segmentation` — see
[CONTENT_STRATEGY.md](CONTENT_STRATEGY.md)), from source material that's
gone through the appropriate OCR purpose first where relevant. Item is not
visible to learners at this stage.

**Review.** A human (today: the founder, no dedicated reviewer role exists)
runs the §5 checklist against the draft. This is the stage the proposed
`human_reviewed` metadata field (§3) would flip once complete — today this
happens with no recorded trail, which is §1 finding 6.

**Approval.** Distinct from Review only once a second reviewer or a
formal sign-off step exists — today, for a solo founder, Review and
Approval are the same action. Keeping them as separate named stages in this
model (rather than collapsing to Draft→Review→Publish) is deliberate: it's
the seam where a second reviewer role slots in later without a workflow
redesign, matching [CONTENT_STRATEGY.md](CONTENT_STRATEGY.md)'s Phase 4 plan
to formalize review as content volume grows.

**Publish.** Item becomes learner-visible (`is_active = true`, already the
mechanism every content table uses). The dedupe unique index (§5 point 5)
is the hard backstop at this step regardless of whether the earlier stages
were followed correctly.

**What this sprint does not propose:** a `status` column, a review queue
UI, or a second reviewer role. Building workflow tooling ahead of the
volume that justifies it is explicitly the anti-pattern
[CONTENT_STRATEGY.md](CONTENT_STRATEGY.md) already warns against ("don't
build review tooling ahead of the volume that would justify it"). The
Draft/Review/Approval/Publish stages above describe the process as it
should be understood and eventually instrumented — implementing the
`human_reviewed`/`ai_generated` fields from §3 is the cheapest first step
whenever this proposal is picked up, not a full workflow engine.

---

## Open decisions for whoever approves this proposal

- **Relationship to Adaptive Reading**: the Content Foundation provides
  standards for future content improvements. Adaptive Reading V1 proceeds
  using the existing content library, while metadata normalization and
  content enhancement continue as parallel work — nothing here blocks it.
- Does the metadata migration (§3) land as one sprint, or roll out
  module-by-module?
- Who owns writing the ~100+ Beginner-tier Reading/Listening items needed
  to close §1 finding 1?
- Is Vocabulary or Grammar built first, given neither has any content today
  and Grammar has no schema at all?

None of these are decided by this document — it's a proposal, not an ADR.
If and when it's approved, the schema change belongs in
[DATABASE.md](DATABASE.md) and an ADR in [DECISIONS.md](DECISIONS.md) per
the normal Product OS process (see
[PRODUCT_OS.md](PRODUCT_OS.md) → Development Rules).
