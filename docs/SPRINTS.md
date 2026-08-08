# Sprints

Lightweight sprint tracking for a solo/small-team cadence — no formal
scrum ceremony, but every sprint gets a goal, a status, and an honest
"blocked" list so work doesn't silently stall. Sprints are pulled from
[BACKLOG.md](BACKLOG.md) → **Now**, scoped by the current
[ROADMAP.md](ROADMAP.md) phase.

Update this file when a sprint starts, when its status changes, and when
it closes — not just at the end. A stale sprint board is worse than none.

---

## Sprint: Learner Brain Foundation

**Goal**: Lay the schema groundwork for cross-module skill tracking without
committing to the service-layer read/write work yet (that's Phase 3, see
[ROADMAP.md](ROADMAP.md)).

**Milestones**:
- [x] Add `product` column to `user_skill_stats`, re-scope uniqueness to
      `(user_id, product, skill_tag)`, default `'OET'` so existing rows and
      code need no change.
- [x] Create `skill_observations` append-only table (raw per-observation
      log, RLS read-only for owner, service-role-only writes).
- [x] Write emergency rollback SQL for both migrations
      (`backend/migrations/rollback/`).
- [ ] Apply both migrations to production Supabase.
- [ ] Live-verify: confirm `user_skill_stats` reads/writes are unaffected
      post-migration (existing Study Hub weakness queries still return
      correct results).

**Status**: In progress — migrations written, not yet applied to
production as of 2026-08-08. Unrelated to Sprint 1 below (see ADR-008 in
[DECISIONS.md](DECISIONS.md)) — Sprint 1 deliberately does not depend on
these migrations landing.

**Estimated effort**: Small (schema-only; no service code in this sprint
by design — see ADR-004 in [DECISIONS.md](DECISIONS.md)).

**Blocked items**: none. Service-layer work (writing to
`skill_observations`, rollup jobs) is explicitly out of scope for this
sprint — do not pull it in early.

---

## Sprint 1: Adaptive Speaking V1 (complete)

**Goal**: First rule-based coaching pass for Speaking — after a scored
session, read the learner's `user_skill_stats` history to find a real
weak-skill pattern (falling back to this session's own scores when there
isn't one yet), recommend a next scenario, and show it on the results page
as "Today's Speaking Insights." Ships entirely on the existing production
schema — see ADR-008 in [DECISIONS.md](DECISIONS.md) for why this needed no
new table and no migration.

**Milestones**:
- [x] New `app/services/observation_service.py`: `validate_and_normalize`
      (generic, module-keyed) — owns score validation/normalization so
      `skill_graph.py` doesn't have to.
- [x] `skill_graph.py` unchanged from its pre-Sprint-1 shape — aggregation
      only (`user_skill_stats` EMA upsert), no new parameter, no new table.
- [x] `speaking.py::_build_speaking_insights`: prefers `get_weakness`
      (existing, unmodified) for the weakest skill when it has history;
      falls back to this session's own lowest-scoring criterion otherwise.
      Recommendation still delegates to the existing `_recommend_scenarios`.
- [x] New `app/services/coaching_messages.py`: small config (dict, keyed by
      "history"/"session") for recommendation-reason, actionable-improvement,
      and confidence-message copy — no hardcoded per-case conditionals.
- [x] `/speaking/score` response gains `insights`: strongest/weakest skill,
      `recommendation_reason`, `actionable_improvement`,
      `confidence_message`, `next_best_action` (renamed from
      `recommended_next` to support future non-Speaking recommendations).
- [x] Speaking results page: "Today's Speaking Insights" section — existing
      score display untouched.
- [x] Backend tests: `observation_service` validation, history-vs-session
      recommendation fallback.

**Status**: Complete. Code complete 2026-08-08, QA gate passed (functional/
regression/security/perf/a11y/mobile/UX/code-quality/tech-debt review —
one real bug found and fixed: unguarded exception in
`_build_speaking_insights` could 500 an already-successful `/score`
response; now best-effort like `record_skill_observations`), CTO-approved
2026-08-08. No production migration required — runs on `user_skill_stats`
as already deployed. See [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md)
for the full record. Production live-verification of the insights card
itself (as opposed to the pre-existing scoring flow it sits on top of) is
still pending — tracked in [BACKLOG.md](BACKLOG.md) → Now.

**Estimated effort**: Medium (one new validation module, one new message
config, one recommendation rework, one new frontend section — no schema
change, no AI call, no new dependency).

**Blocked items**: none.

---

## Sprint 1.5: Content Foundation design (complete)

**Goal**: Documentation-only sprint — design the content taxonomy/metadata/
difficulty standard for future content improvements. No code, no schema, no
DB change; explicitly not a build sprint.

**Milestones**:
- [x] Content audit against production Supabase: item counts, difficulty
      distribution, and specialty-tag consistency per module.
- [x] Six-area content taxonomy (Speaking, Reading, Listening, Writing,
      Vocabulary, Grammar).
- [x] Metadata standard (skill tags, difficulty, topic, specialty, learning
      objectives, OET criteria, estimated duration, `ai_generated`,
      `human_reviewed`) mapped against existing columns vs. proposed new
      ones.
- [x] 5-tier Beginner→Exam Ready difficulty model, with a mapping note for
      today's inconsistent `easy`/`medium`/`hard`/`intermediate`/`advanced`
      values.
- [x] Pre-publish content quality checklist.
- [x] Draft→Review→Approval→Publish AI content workflow, mapped onto the
      existing AI Model Registry purposes and founder-review process.

**Status**: Complete. See [CONTENT_FOUNDATION.md](CONTENT_FOUNDATION.md) for
the full proposal. This is a design document, not a locked decision — no
ADR was written, no migration exists. The Content Foundation provides
standards for future content improvements. Adaptive Reading V1 proceeds
using the existing content library, while metadata normalization and
content enhancement continue as parallel work.

**Estimated effort**: Small (documentation only; no code, no migration, no
DB write).

**Blocked items**: none.

---

## Sprint: AI Model Registry (complete)

**Goal**: Replace every hardcoded AI model ID in the backend with a
DB-backed registry, so model/provider changes don't need a code deploy.

**Milestones**:
- [x] `ai_models` + `ai_model_purposes` schema, `ai_registry.py` dispatcher.
- [x] Purpose-based routing with one-level fallback, 60s config cache.
- [x] Admin UI at `/admin/ai-models` (models, purpose mapping, health,
      history/rollback via `audit_log`).
- [x] Seed all 30 existing purposes (realtime voice, TTS, STT, scoring,
      OCR, content generation — full list in
      [docs/ai-model-registry.md](ai-model-registry.md)).
- [x] Backend verified live against Supabase; frontend verified via
      `tsc --noEmit` + production build.
- [ ] Click-through UI test with real admin credentials (deferred — no
      test admin account was on hand this session).

**Status**: Complete, shipped 2026-08-07/08. One follow-up item (UI
click-through) carried to [BACKLOG.md](BACKLOG.md) → Next.

**Estimated effort**: Large (touched every AI call site in the backend).

**Blocked items**: none.

---

## Sprint template

Copy this for the next sprint:

```
## Sprint: <name>

**Goal**: <one sentence, tied to a Roadmap phase>

**Milestones**:
- [ ] <milestone>

**Status**: Not started / In progress / Blocked / Complete

**Estimated effort**: Small / Medium / Large

**Blocked items**: <what's blocking, or "none">
```
