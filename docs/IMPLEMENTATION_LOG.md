# Implementation Log

One entry per shipped feature — a concise, permanent record of what changed
and why, separate from the living status docs ([ROADMAP.md](ROADMAP.md),
[SPRINTS.md](SPRINTS.md), [MODULES.md](MODULES.md)) which describe *current
state* and get edited as that state moves on. This file does not get
edited after the fact except to append a follow-up note — it's a log, not a
dashboard.

---

## 2026-08-08 — RC3.1: Content Studio Foundation + QA

Admin-only foundation for the future AI Content Studio (RC3, opened this
sprint). CTO scope was explicit: architecture only — no AI generation, no
review/publishing workflow, no schema change, no learner-facing change.
Read-only end-to-end: dashboard, searchable library, detail page.

**Business goal**: Give the founder one place to see everything content-
related across all six planned modules before any content-production or
AI-generation tooling gets built on top of it, without inventing workflow
states the data model can't actually support yet (see
[docs/CONTENT_FOUNDATION.md](CONTENT_FOUNDATION.md), the design-only
proposal this sprint builds toward).

**What changed**: New `/admin/content-studio` dashboard shows Total/
Published/Unpublished counts overall and per module (Speaking, Reading,
Listening, Writing); Vocabulary and Grammar render as static "Coming Soon"
tiles and are never queried (neither has an admin-ready content store —
`vocab_cards` is a per-user SRS deck, Grammar has no table at all). A new
Library page lists every content item across the four real modules with
search, and Module/Status/Difficulty filters — no filter is shown for
metadata that doesn't exist yet (Specialty/Topic/Skill tags), per CTO
instruction. Every item gets a stable, derived (not stored) human-readable
Content ID: `SPK-000144`, `WRT-000012`, `RDG-000016`, `LST-000254`. A
read-only detail page shows what metadata exists today and labels Version/
Created By/Review History as "Not tracked yet — planned for RC3.3" rather
than faking them.

Status is a **two-value proxy** (Published/Unpublished) off the existing
`is_active` boolean — the CTO explicitly rejected fabricating Draft/Review/
Archived states ahead of the schema change that would make them real
(RC3.3).

**Files changed**:
- `backend/app/services/content_studio.py` (new) — pure aggregation over
  existing `scenarios` (speaking/writing), `reading_passages`,
  `listening_sections` rows; no new tables, no migration.
- `backend/app/routers/admin_content_studio.py` (new) — `GET
  /admin/content-studio/{summary,items,items/{module}/{id}}`, gated
  `require_admin` only (not `require_analyst` — this exposes unpublished
  content across every module, per CTO review).
- `backend/app/main.py` — router registration.
- `frontend/app/admin/content-studio/{page.tsx,library/page.tsx,
  [module]/[id]/page.tsx}` (new) — dashboard, library, detail.
- `frontend/app/admin/AdminShell.tsx` — one nav entry added.
- `frontend/tests/e2e/admin-content-studio.spec.ts` (new, RC3.1 QA) — 8
  scenarios: dashboard load + card rendering, Coming Soon tiles, library
  filters/search/pagination, detail page, admin access, non-staff denial
  (mocked `/auth/me`, no second real account needed), responsive layout,
  API verification.
- `frontend/.gitignore` — `tests/e2e/*.json` (Playwright storageState
  files hold live session tokens; this was already missing before RC3.1,
  closed while touching the file for the same reason).

**User-visible changes**: None — admin-only, behind `require_admin`.

**QA notes**: Suite passes 8/8 live against production data
(`SPK-000189` etc. are real rows, not fixtures). Two genuine product
defects found and fixed: the library table had no horizontal-scroll
container (would overflow the page body at mobile widths — table now
scrolls inside `overflow-x-auto`, page body doesn't); the three filter
`<select>`s and the search `<input>` had no accessible name (added
`aria-label`). Two test-authoring bugs also found and fixed, in the test
itself, not the product: a `.count()` check that raced ahead of an async
fetch, and an anchored regex (`^...$`) that failed against
`toContainText`'s substring semantics. Full regression run (existing +
new suite, `--workers=1`): 19/20 pass; the one failure
(`login.spec.ts`) is a pre-existing, already-documented shared-test-
account login race (see RC2's QA notes below), confirmed unrelated by
running it standalone (passes clean).

**Known limitations**:
- Dashboard's Published/Unpublished split is real but coarse — a
  "Published" item could equally be an untouched AI first draft as a
  founder-reviewed final version. True Draft/Review/Approved/Published/
  Archived states need the schema change deferred to RC3.3.
  `is_active` is a publish switch, not a review-workflow status, and
  this sprint deliberately didn't pretend otherwise.
- Vocabulary and Grammar have zero admin tooling behind their "Coming
  Soon" tiles — RC3.2/RC3.3 scope, not started.
- Not yet live-verified against a live preview/production deploy (same
  gate RC1/RC2 are still waiting on).

**Future follow-ups**:
- RC3.2 — Content Production (explicitly out of scope this sprint).
- RC3.3 — Review Workflow, Publishing, and the `status`/`version`/
  `created_by`/`review_history` schema this sprint's detail page already
  has placeholders for.
- Live-verify per the same pattern as RC1/RC2 once deployed.

## 2026-08-08 — RC2: Adaptive Dashboard V1 + QA

Cross-module dashboard surfacing the same `user_skill_stats`/skill-graph
spine Sprints 1-4 (Adaptive Learning V1) already write to, aggregated across
all four modules instead of shown one-module-at-a-time on each results page.
Replaces the old static `RecommendedCaseCard` on `/dashboard`.

**Files changed**:
- `backend/app/services/dashboard_analytics.py` (new) — `compute_trend`
  (improving/stable/declining/insufficient_data off a 3-session-vs-prior-3
  window), `get_skill_insights` (one pass over `get_weakness` per module,
  reused for both per-module weakest/strongest and the cross-module Weak
  Skills list), `pick_weakest_module`.
- `backend/app/routers/progress.py` — `GET /progress/stats` now also
  returns `module_averages` (per-module average/trend/last_activity/
  strongest+weakest skill), `weak_skills` (cross-module, weakest-first),
  and `next_best_action` (weakest attempted module, matched to a specific
  weak skill when one exists).
- `backend/app/routers/{listening,reading,writing}.py` — `GET
  /{module}/{tests,scenarios}/recommend`, one recommended item for the
  dashboard's Next Best Action card (Speaking's equivalent already
  existed). Registered before the `/{id}` route in each file so
  `"recommend"` isn't swallowed as an id.
- `frontend/app/components/oet/ModuleProgressCard.tsx`,
  `WeakSkillsList.tsx` (new) — per-module cards (average, trend, last
  activity, strongest/weakest skill) and the cross-module weak-skills list.
- `frontend/app/components/oet/AdaptiveRecommendationCard.tsx` (renamed
  from `RecommendedCaseCard.tsx`) — fetches the matching `/recommend`
  endpoint for `next_best_action.module` and links into that module.
- `frontend/app/components/oet-dashboard.tsx`, `dashboard/page.tsx`,
  `oet/types.ts` — wiring for the above.
- `frontend/tests/e2e/dashboard.spec.ts` (new, RC2 QA) — 7 scenarios:
  page load with no fatal/console errors, existing-learner full render,
  new-learner empty state (mocked `/progress/stats`), one-session learner
  (trend gracefully degrades to "Not enough data yet"), responsive layout
  (desktop + mobile, no horizontal scroll), uncaught-exception guard, and
  `/progress/stats` API verification.
- `docs/RC2_QA_CHECKLIST.md` (new) — manual founder click-through list
  covering all four modules, the dashboard, monitoring, and release
  verification.

**User-visible changes**: `/dashboard` now shows one card per module
(average band, trend arrow, last activity, strongest/weakest skill), a
cross-module Weak Skills list, and an Adaptive Recommendation card that
routes to whichever module + item is currently weakest — instead of the
prior static recommended-case card.

**QA notes** (this entry's actual scope — the dashboard feature above was
already code-complete going into this pass): two issues surfaced by the new
Playwright suite, both in the test itself, not the product — concurrent
Playwright workers logging into the same shared test account raced against
Supabase Auth (`page.waitForURL` timing out); fixed by authenticating once
in `beforeAll` and reusing `storageState` across a serial test run.
Unscoped `getByText('Speaking')` false-matched the sidebar nav instead of
the real module card; fixed by scoping assertions to `getByRole('main')`.
No product-code defects found. `tsc --noEmit` clean; full Playwright suite
(12 tests: 5 existing RC1 smoke + 7 new dashboard) passing locally.

**Known limitations**:
- Not yet live-verified against production/preview traffic — merged to
  `main` and tagged `v1.1.0-rc2`, but the click-through in
  [RC2_QA_CHECKLIST.md](RC2_QA_CHECKLIST.md) hasn't been run against a
  live deploy yet (same gate RC1 is still waiting on — see
  [RELEASES.md](RELEASES.md)).
- `docs/DOMAIN_SPLIT_MIGRATION_PLAN.md` was sitting uncommitted alongside
  this work but is unrelated (separate, not-yet-started initiative) — left
  out of this commit on purpose.

**Future follow-ups**:
- Live-verify per [RC2_QA_CHECKLIST.md](RC2_QA_CHECKLIST.md).
- AppShell renders two `<h1>` per authenticated page (top-bar page title +
  each page's own heading, e.g. `DashboardHeader`'s greeting) — pre-existing
  across every route, not introduced by this work; worth a future a11y pass
  but out of scope for a dashboard-only QA sprint.

## 2026-08-08 — Adaptive Speaking V1

**Feature name**: Adaptive Speaking V1 (Sprint 1, ADR-008 in
[DECISIONS.md](DECISIONS.md))

**Business goal**: Give a learner a concrete answer to "what should I
practice next" right after a scored Speaking session, instead of a raw
9-criteria score with no next step — the first step toward the Learner
Brain vision (cross-module weakness routing) without waiting on Phase 3's
schema/rollup work to land first.

**What changed**: `/speaking/score` now returns an `insights` object built
from the learner's already-scored session plus their existing
`user_skill_stats` history: strongest skill (always this session),
weakest skill (prefers a real historical pattern via `get_weakness` when
one exists — at least 2 attempts and band < 5.0 — falling back to this
session's own lowest-scoring criterion for a learner with no pattern yet),
a recommendation reason, one actionable improvement, a confidence message,
and a recommended next scenario (delegates to the existing
`_recommend_scenarios`). The Speaking results page renders this as a
"Today's Speaking Insights" card. Runs entirely on `user_skill_stats` as
already deployed in production — no new table, no migration (see ADR-008
for why an earlier draft that depended on the still-unapplied
`skill_observations` table was rejected).

**Files changed**:
- `backend/app/services/observation_service.py` (new) — `validate_and_normalize(module, raw_scores)`: keeps only numeric, non-bool, in-range (0-6), correctly-tagged scores.
- `backend/app/services/coaching_messages.py` (new) — history-vs-session copy templates for recommendation reason / actionable improvement / confidence message.
- `backend/app/routers/speaking.py` — `_skill_label`, `_build_speaking_insights`, wired into `score_speaking_session`; raw scores now pass through `validate_and_normalize` before `record_skill_observations`.
- `backend/app/services/skill_graph.py` — docstring only (clarifies `record_skill_observations` now expects pre-validated input); no behavior change.
- `frontend/app/practice/speaking/SpeakingSession.tsx` — "Today's Speaking Insights" card; `insights` threaded through the existing feedback state.
- `backend/tests/test_observation_service.py`, `backend/tests/test_speaking_insights.py` (new).

**User-visible changes**: After finishing a scored Speaking session, the
results page shows a new card: strongest/weakest skill with band scores,
why the weakest skill was picked, one specific thing to practice next, a
confidence note (session-only vs. history-backed), and a link to a
recommended next scenario. No change to the existing score display,
scoring logic, or any other module.

**Technical decisions**:
- No new table/migration — reuses `user_skill_stats` and the unmodified
  `get_weakness`/`_recommend_scenarios` (ADR-008).
- Score validation split into its own module (`observation_service.py`)
  keyed by `module` string, rather than inlined in `skill_graph.py` or
  `speaking.py`, so Reading/Listening/Writing can call the same function
  later without a redesign — `skill_graph.py` stays aggregation-only.
- Coaching copy is a config dict keyed by confidence tier
  (`"history"`/`"session"`), not inline if/else branching, so a new tier
  or a future module's own copy is a dict entry.
- **QA-gate fix**: `_build_speaking_insights` originally had no exception
  guard around its `get_weakness`/`_recommend_scenarios` calls. Because it
  runs *after* the submission is saved and the session is claimed, an
  uncaught DB blip there would have 500'd an already-successful scoring
  request. Wrapped in try/except, logs and returns `None` on failure —
  matching the existing best-effort convention `record_skill_observations`
  already uses. Covered by
  `test_build_speaking_insights_degrades_gracefully_on_unexpected_error`.

**Known limitations**:
- Single-criterion edge case: if the AI returns only one valid criterion
  score for a session, strongest and weakest skill display as the same
  skill. Rare (9 criteria are scored per session today) and cosmetic, not
  a crash.
- Not yet live-verified against production traffic — code-complete,
  QA-reviewed, and CTO-approved, but the actual click-through on deployed
  `/speaking/score` hasn't happened yet (tracked in
  [BACKLOG.md](BACKLOG.md) → Now).

---

## 2026-08-08 — Adaptive Reading V1

**Feature name**: Adaptive Reading V1 (Sprint 2)

**Business goal**: Same "what should I practice next" answer Sprint 1 gave
Speaking learners, now on the Reading test results page — without waiting
on Content Normalization (the per-item skill metadata Reading's content
library doesn't have yet, see [CONTENT_FOUNDATION.md](CONTENT_FOUNDATION.md))
or a shared cross-module recommendation service.

**What changed**: `/reading/tests/{id}/submit` now returns an `insights`
object built from the just-graded session plus the learner's existing
`user_skill_stats` history: strongest reading skill (this session),
weakest skill (prefers historical pattern via the existing `get_weakness`
when one exists, else this session's own lowest-scoring skill), a
recommendation reason, one actionable improvement, a confidence message,
and a recommended next test (`_recommend_reading_tests`: unattempted tests
first, then the learner's lowest-scored attempted tests, weakest first).
The Reading test results page renders this as a "Today's Reading Insights"
card. Runs entirely on `user_skill_stats` as already deployed — no new
table, no migration.

Deliberately **not** built as a shared `next_best_action` service or a new
Reading-specific recommendation endpoint — both were proposed during
planning and explicitly rejected in favor of keeping this sprint the same
size and shape as Sprint 1 (local, per-module functions; extraction happens
once Speaking, Reading, Listening and Writing each have a working
implementation to extract from).

**Files changed**:
- `backend/app/routers/reading.py` — `_recommend_reading_tests`,
  `_reading_skill_label`, `_build_reading_insights`, wired into
  `submit_reading_test`; both `record_skill_observations` call sites (
  standalone passage + full test) now pass through the existing
  `validate_and_normalize` first, matching Speaking's hygiene.
- `backend/app/services/coaching_messages.py` — reworded "criterion" →
  "area" in the existing tier-keyed templates so Reading could reuse them
  unmodified instead of forking a Reading-specific copy.
- `frontend/app/practice/reading/test/[id]/page.tsx` — "Today's Reading
  Insights" card, same layout as Speaking's.
- `backend/tests/test_reading_insights.py` (new).

**User-visible changes**: After finishing a full Reading test, the results
page shows a new card: strongest/weakest reading skill with band scores,
why the weakest skill was picked, one specific thing to practice next, a
confidence note, and a link to a recommended next test. No change to
existing scoring, per-part bands, or the standalone single-passage flow
(`/reading/submit` gained the `validate_and_normalize` hygiene fix only —
no insights there, out of scope for V1).

**Technical decisions**:
- **Content-level, not skill-aware, recommendation (intentional Phase 1
  decision).** `_recommend_reading_tests` ranks by attempted/unattempted
  and average score only — it does not filter candidate tests by which
  skill they'd exercise, because no content item carries skill metadata
  yet (Sprint 1.5's named gap). Filtering would require scanning every
  active test's questions on every submit to derive skill coverage
  on the fly, which was explicitly rejected as unnecessary work in the hot
  grading path. The weakest skill is still surfaced accurately (via
  `get_weakness`, already free) — it's reported, not used to filter the
  pick. Future Content Normalization enables true skill-aware routing
  without changing this response shape (`next_best_action` stays
  `{test_id, title, reason}` regardless of how it's picked).
- **No shared `next_best_action` service.** Considered and rejected during
  planning (see CTO review history) in favor of a local port of Sprint 1's
  pattern — avoids introducing an abstraction before a second and third
  real caller (Listening, Writing) exist to shape its interface honestly.
- **No new Reading recommendation endpoint.** `next_best_action` rides
  inside the existing submit response only, same as Speaking's
  `/speaking/score` — not a new `/reading/tests/recommend` route.
- `reading_skills.py` untouched — stays classification/label-only; the
  wording generalization needed for cross-module reuse went into
  `coaching_messages.py` instead, keeping the separation between
  "how a question is classified" and "what the learner is told" intact.

**Known limitations**:
- Recommendation quality is a step behind Speaking's: Speaking's rubric
  criteria are AI-graded and directly meaningful; Reading's `reading:skill:*`
  tags come from a keyword heuristic (`classify_reading_skill`), a coarser
  signal.
- Standalone single-passage practice (`/reading/submit`) has no insights
  card — scoped to the full-test flow only for V1.
- Not yet merged to `main` or live-verified against production traffic —
  code-complete, QA-reviewed (backend tests, frontend typecheck/lint/build),
  and CTO-approved, committed to `develop` only as of this entry.

**Future follow-ups**:
- Live-verify the insights card in production.
- Extend `validate_and_normalize` to Reading/Listening/Writing's existing
  `record_skill_observations` call sites (currently speaking-only).
- Cross-module weakness routing (recommend a Reading/Listening/Writing
  scenario, not just another Speaking one) once Phase 3 (Learner Brain)
  lands — deliberately out of scope here, see ADR-008.

---

## 2026-08-08 — Adaptive Listening V1

**Feature name**: Adaptive Listening V1 (Sprint 3)

**Business goal**: Same "what should I practice next" answer Sprint 1
(Speaking) and Sprint 2 (Reading) gave, now on the Listening test results
page — no new tables, endpoints, services, or abstractions.

**What changed**: `/listening/tests/{id}/submit` now returns an `insights`
object built from the just-graded session's per-part bands
(`listening:{A,B,C}`, already recorded by this endpoint pre-Sprint-3) plus
the learner's existing `user_skill_stats` history: strongest part this
session, weakest part (prefers historical pattern via the existing
`get_weakness` when one exists, else this session's own lowest-scoring
part), a recommendation reason, one actionable improvement, a confidence
message, and a recommended next test (`_recommend_listening_tests`:
unattempted tests first, then the learner's lowest-scored attempted tests,
weakest first). The Listening test results page renders this as a "Today's
Listening Insights" card. Runs entirely on `user_skill_stats` as already
deployed — no new table, no migration.

**Files changed**:
- `backend/app/routers/listening.py` — `_recommend_listening_tests`,
  `_build_listening_insights`, wired into `submit_test`.
- `frontend/app/practice/listening/test/[id]/page.tsx` — "Today's Listening
  Insights" card, same layout as Speaking's and Reading's.

**User-visible changes**: After finishing a full Listening test, the
results page shows a new card: strongest/weakest part with band scores,
why the weakest part was picked, one specific thing to practice next, a
confidence note, and a link to a recommended next test. No change to
existing scoring, per-part bands, or transcript reveal.

**Technical decisions**:
- **Part-level insight, not a new skill-tag namespace.** Listening has no
  `listening:skill:*` sub-tags (unlike Reading's `reading:skill:*`) — only
  the part-level `listening:{A,B,C}` tags this endpoint already recorded
  before this sprint. Insights key off those directly rather than
  inventing finer-grained tags, per CTO direction to introduce new skill
  tags "only if absolutely necessary" — it wasn't.
- **Labels kept as "Part A/B/C" — no new label mapping.** No friendlier
  learner-facing part labels exist anywhere in the codebase today. Per CTO
  direction, did not invent one for this sprint; left a `TODO` in
  `_build_listening_insights` for future copy polish once that mapping
  exists elsewhere.
- **`validate_and_normalize` gap on `listening.py`'s
  `record_skill_observations` call left untouched**, per explicit CTO
  instruction this sprint — tracked as existing debt, not this sprint's to
  fix.
- **No shared `next_best_action` service, no new endpoint** — same reasons
  as Sprint 2: local port, avoids shaping an abstraction before Writing (the
  fourth caller) also has one.

**Known limitations**:
- Same content-level (not skill-filtered) recommendation limitation as
  Reading — `_recommend_listening_tests` doesn't filter by which part a
  test would exercise.
- Not yet merged to `main` or live-verified against production traffic —
  code-complete, QA-reviewed (backend self-check, frontend
  typecheck/build), and CTO-approved, committed to `develop` only as of
  this entry.

**Future follow-ups**:
- Live-verify the insights card in production.
- Friendlier Listening part labels, once that copy exists (see `TODO` in
  `_build_listening_insights`).
- Same `validate_and_normalize` and cross-module weakness routing
  follow-ups noted under Sprint 2 — Listening is now a third data point for
  when to extract the shared insights service.

---

## 2026-08-08 — Adaptive Writing V1

**Feature name**: Adaptive Writing V1 (Sprint 4)

**Business goal**: Same "what should I practice next" answer Sprints 1-3
gave Speaking/Reading/Listening learners, now on the Writing results page —
closing Adaptive Learning V1 across all four OET modules. No new tables,
endpoints, services, or abstractions.

**What changed**: `/writing/submit` now returns an `insights` object built
from the just-scored session's six OET criterion scores (`writing:{criterion}`)
plus the learner's existing `user_skill_stats` history: strongest criterion
this session, weakest criterion (prefers historical pattern via the
existing `get_weakness` when one exists, else this session's own
lowest-scoring criterion), a recommendation reason, one actionable
improvement, a confidence message, and a recommended next scenario
(`_recommend_writing_scenarios`: unattempted scenarios first, then the
learner's lowest-scored attempted scenarios, weakest first — same algorithm
as Speaking's `_recommend_scenarios`, including its correct
`run_sync`-wrapped blocking-call pattern, not Reading/Listening's unwrapped
one). The Writing results page renders this as a "Today's Writing Insights"
card. Runs entirely on `user_skill_stats` as already deployed — no new
table, no migration.

Writing's six criteria score on non-uniform official OET ranges (Purpose
0-3; Content, Conciseness, Genre & Style, Organisation, Language each 0-7)
rather than the uniform 0-6 band Speaking/Reading/Listening's criteria
already use. CTO-approved normalization: a new private
`normalize_writing_score(raw_score, max_score)` helper rescales each
criterion by `round(raw/max*6, 2)` before `validate_and_normalize` —
preserving each criterion's percentile-of-max standing so EMA blending and
weakness-ranking stay comparable across all four modules. Kept local to
`writing.py` per explicit CTO instruction — `ObservationService` and
`score_writing`'s rubric are unchanged.

**Files changed**:
- `backend/app/routers/writing.py` — `normalize_writing_score`,
  `WRITING_SKILL_LABELS`/`_writing_skill_label`,
  `_recommend_writing_scenarios`, `_build_writing_insights`, wired into
  `submit_writing`; `_score_and_save` now returns `(feedback,
  criterion_scores)` instead of just `feedback` so the caller can build
  insights without re-deriving normalized scores; its
  `record_skill_observations` call now passes through the existing
  `validate_and_normalize("writing", …)` first (previously the one gap
  alongside Listening — now closed).
- `frontend/app/practice/writing/page.tsx` — `Insights`/`SkillScore`/
  `NextBestAction` interfaces, `insights` state, "Today's Writing Insights"
  card (same layout as Speaking/Reading/Listening's). "Recommended Next"
  renders as a `<button>` calling the existing `handleSelectScenario`, not
  an `<a href>` like Reading/Listening — Writing has no per-scenario route
  (scenario selection has always worked this way via the scenario-picker
  cards), so this isn't a new pattern, it matches Writing's own existing
  convention.
- `backend/tests/test_writing_insights.py` (new) —
  `normalize_writing_score`, `_writing_skill_label`,
  `_build_writing_insights` (history vs. session fallback, graceful
  degradation on no-scenarios and on unexpected errors).

**User-visible changes**: After finishing a scored Writing submission, the
results page shows a new card: strongest/weakest criterion with band
scores, why the weakest criterion was picked, one specific thing to
practice next, a confidence note, and a link to a recommended next
scenario. No change to the existing grade, per-criterion score bars,
strengths/improvements lists, or corrected-version display. The free-tier
"locked" mock branch (score hidden behind a paywall) is unaffected — it
returns before scoring runs, same as before.

**Technical decisions**:
- **Normalization kept local, not pushed into `ObservationService`.** CTO
  explicitly rejected redesigning `ObservationService` or Writing's scoring
  rubric to accommodate non-uniform criterion ranges — `normalize_writing_score`
  is a private `writing.py` function, used nowhere else.
- **`_recommend_writing_scenarios` uses Speaking's `run_sync`-wrapped
  pattern, not Reading/Listening's.** Reading and Listening's equivalent
  functions make a blocking Supabase call directly inside an `async def`
  (pre-existing, untouched debt — out of scope per this sprint's
  non-goals). Writing's new function follows Speaking's correct pattern
  instead of copying that bug a third time.
- **No shared `next_best_action` service, no new endpoint** — same
  reasoning as Sprints 2-3: this was the fourth and final local port, the
  point at which the shared-insights-service extraction (deferred since
  Sprint 1) becomes viable — but extraction itself was not this sprint's
  scope.
- **Labels reuse the frontend's existing `WRITING_CRITERIA` copy** (Purpose,
  Content, Conciseness & Clarity, Genre & Style, Organisation & Layout,
  Language) via a new backend-side `WRITING_SKILL_LABELS` dict, so the
  insights card names a criterion the same way the score breakdown above it
  already does — no new coaching vocabulary invented.

**Known limitations**:
- Same content-level (not skill-filtered) recommendation limitation as
  Reading/Listening — `_recommend_writing_scenarios` doesn't filter by
  which criterion a scenario would exercise.
- Not yet merged to `main` or live-verified against production traffic —
  code-complete, QA-reviewed (11 new backend tests, full backend suite
  regression-checked, frontend typecheck clean), and CTO-approved,
  committed to `develop` only as of this entry.
- Pre-existing, unrelated test failures observed in the same run
  (`test_writing_ocr.py`, `test_ai_scoring_temperature.py`,
  `test_google_model_routing.py`) — confirmed present on unmodified
  `develop` via `git stash` comparison; environmental (missing provider API
  keys in the sandbox), not caused by this sprint.

**Future follow-ups**:
- Live-verify the insights card in production (RC1 gate — see
  [RELEASES.md](RELEASES.md)).
- This is the fourth local port of the same pattern (Speaking, Reading,
  Listening, Writing) — extract a shared insights/recommendation service
  now that all four exist, per the extraction condition named in Sprints
  1-3's docs.
- Cross-module weakness routing (recommend a non-Writing scenario when
  Writing isn't the learner's weakest module) remains Phase 3 (Learner
  Brain) work, unstarted.
