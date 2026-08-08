# Implementation Log

One entry per shipped feature — a concise, permanent record of what changed
and why, separate from the living status docs ([ROADMAP.md](ROADMAP.md),
[SPRINTS.md](SPRINTS.md), [MODULES.md](MODULES.md)) which describe *current
state* and get edited as that state moves on. This file does not get
edited after the fact except to append a follow-up note — it's a log, not a
dashboard.

---

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
