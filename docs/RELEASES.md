# Releases

How code ships, today's real workflow first, then the approved future
direction. Do not describe a process the team doesn't actually follow —
this file must match reality (see Definition of Done in
[PRODUCT_OS.md](PRODUCT_OS.md)).

---

## Development branch

**Status: V2**

Three-tier flow: `feature/*` → `develop` → `main`.

- **`feature/*`** — one branch per unit of work (e.g. `fix/voiceorb-a11y`).
  Short-lived, deleted after merge. Branches off `develop`, merges back
  into `develop`.
- **`develop`** — the integration branch. Where feature branches land and
  get combined before anything reaches production. Lets several things
  in flight get reviewed/combined without each one individually touching
  `main`.
- **`main`** — production. Vercel/Render auto-deploy on merge to `main`
  (see Production below) — merging here ships to real users. Only
  `develop` merges into `main`, not individual feature branches directly.

Superseded V1 (`main` as the only long-lived branch, feature branches
merged straight into it) once `develop` was introduced 2026-08-08 — see
[docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md). The V1 rationale
(solo/small-team, no long-lived branch to protect from) still holds for
why there's no further staging tier beyond these three.

## QA

**Status: V1 (informal) / Future (formal, Post PMF)**

No dedicated QA function or environment today. Quality gates are:
1. CI (`.github/workflows/ci.yml`) on every push/PR to `main` — backend
   `pytest` + `ruff check app/ --select F` (scoped to pyflakes: unused
   imports/vars, undefined names, redefinitions — not the fuller
   opinionated ruleset, which is a separate cleanup not yet done),
   frontend build + type check.
2. Manual live-verification against production for anything touching
   auth, payments, or AI scoring — see Definition of Done in
   [PRODUCT_OS.md](PRODUCT_OS.md). This project's history has repeated
   examples of "fixed in code, not yet live-verified" states that later
   needed a second pass — live-verify before calling something done where
   it's cheap to do so.

A dedicated QA environment (Phase 5 / Post PMF, see
[BACKLOG.md](BACKLOG.md)) is not justified at current team size — don't
build one speculatively.

## Internal testing

**Status: V1 (ad hoc)**

Dedicated test accounts exist for specific audit cycles (e.g.
`audit-test-claude@example.com`, `speakoet-audit-0713@mailinator.com` —
created per audit, not a standing shared test account). No formal internal
beta/dogfooding program exists.

## Production

**Status: V1**

- **Frontend**: Vercel, auto-deploys on merge to `main`.
- **Backend**: Render, auto-deploys on merge to `main`.
- **Database**: Supabase — migrations applied via
  `mcp__claude_ai_Supabase__apply_migration` / CLI, checked against
  `list_migrations` first (never assume local history matches prod state).
- **No manual promotion gate** between CI passing and production traffic
  serving the new code — merge to `main` is the release. This is a
  deliberate tradeoff for shipping speed at current team size, not an
  oversight; it's also exactly why live-verification (see QA above) does
  real work here instead of being a formality.

## Versioning strategy

**Status: V1 (none, one-off exception for RC1) / Future (semantic, if ever
needed)**

No version numbers, no changelog today; "what version is live" is normally
answered by "what's the latest commit on `main` that's deployed," not a
version string. RC1 got one lightweight git tag (`v1.0.0-rc1`, on the merge
commit) purely as a stable pointer back to "the commit RC1's live
verification ran against" — not the start of a semver practice. This is
appropriate for a single-deployment web product with no external API
consumers or installable artifact — introduce real semantic versioning only
if a future need actually requires it (e.g. a public API with external
integrators, Phase 5+), not before.

## Recent releases

Not a version-numbered changelog (see Versioning strategy above) — a running
log of what merged to `main`, for anyone scanning history without digging
through commits.

- **2026-08-08 — Adaptive Speaking V1** (Sprint 1, ADR-008): rule-based,
  same-session coaching insights on the Speaking results page. CTO-approved
  after a full QA gate (functional/regression/security/performance/
  accessibility/mobile/UX/code-quality/tech-debt review). No schema change.
  See [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).
- **2026-08-08 — Adaptive Reading V1** (Sprint 2): same rule-based coaching
  insights pattern, ported locally to the Reading test results page.
  CTO-approved after backend tests + frontend typecheck/lint/build. No
  schema change. Committed to `develop`, not yet merged to `main` — not a
  release to production yet, listed here for the record. See
  [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).
- **2026-08-08 — Adaptive Listening V1** (Sprint 3): same rule-based
  coaching insights pattern, ported locally to the Listening test results
  page, keyed off existing part-level tags. CTO-approved after backend
  self-check + frontend typecheck/build. No schema change. Committed to
  `develop`, not yet merged to `main` — not a release to production yet,
  listed here for the record. See
  [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).
- **2026-08-08 — Adaptive Writing V1** (Sprint 4): same rule-based coaching
  insights pattern, ported locally to the Writing results page. Criterion
  scores rescaled from their native OET ranges (Purpose /3, the other five
  /7) onto the shared 0-6 band via a new writing-local
  `normalize_writing_score` helper, kept out of `ObservationService` per
  CTO instruction. CTO-approved after 11 new backend tests, a full backend
  regression run, and a clean frontend typecheck. No schema change.
  Committed to `develop`, not yet merged to `main` — not a release to
  production yet, listed here for the record. Closes **Adaptive Learning
  V1** across all four OET modules — see Release Candidates below and
  [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).
- **2026-08-08 — Adaptive Dashboard V1 + RC2 QA**: cross-module dashboard
  (module progress cards, Weak Skills list, Adaptive Recommendation card)
  plus a new Playwright suite and manual QA checklist. Merged `develop` →
  `main`, tagged `v1.1.0-rc2`. No schema change. See Release Candidates
  below and [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).
- **2026-08-08 — Content Studio Foundation (RC3.1)**: admin-only read-only
  dashboard/library/detail pages for the future AI Content Studio
  (`d32c5327`) — Published/Unpublished counts per module, searchable
  library with filters, stable derived Content IDs, Grammar/Vocabulary as
  static "Coming Soon". No AI generation, no publishing/review workflow,
  no schema change — foundation only, per CTO scope. Includes a new
  8-scenario Playwright suite, passing live against production. Merged
  `develop` → `main`. Not tagged — RC3 stays open pending its remaining
  sub-sprints (Content Production, Review Workflow). See Release
  Candidates below and [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).
- **2026-08-09 — RC3 complete (AI Content Studio)**: closes out all four
  RC3 sub-sprints as one unit.
  - **Content Studio Foundation (RC3.1)**: see above, already on `main`.
  - **AI Draft Generator (RC3.2)**: AI-generated drafts, persisted only to
    `generated_content_drafts` — never to a production content table.
  - **Draft Review/Approval/Publishing (RC3.3)**: full status machine
    (draft → review → approved → published/archived), a revision log that
    only fires on real content/metadata changes, a Publish Preview that
    matches what Publish actually creates, and per-module publish targets
    (Speaking/Writing → `scenarios` with `key_points` on Writing; Reading/
    Listening → standalone, inactive `reading_passages`/
    `listening_sections` rows with no Test Builder linkage; Vocab/Grammar
    blocked). Schema:
    `supabase/migrations/20260808050000_draft_review_workflow.sql`.
  - **Staff Role Management (RC3.4)**: five-tier Staff Role selector
    (None/Support/Analyst/Admin/Owner) replacing the old binary Grant/
    Revoke Admin toggle, rank-based permission inheritance, Owner-only
    role assignment, last-Owner protection, full audit logging.
  - **Final QA**: 14/14 pass (Playwright + direct-API) against the live
    Supabase project — zero code changes required, no blocking defects.
  Committed to `develop`, not yet merged to `main` — not a release to
  production yet, listed here for the record. See Release Candidates
  below and [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).

## Release Candidates

**Status: V1 (informal, third use)**

An RC is an internal label for bundling a set of related, already
CTO-approved sprints for merge and live-verification as one unit — not a
git tag, and not a version number shipped to users (see Versioning
strategy above). It exists so a batch of related work lands and gets
verified together, rather than trickling to `main` one QA-approved-but-
unverified sprint at a time.

- **RC1 — Adaptive Learning V1** (opened 2026-08-08, closed 2026-08-08,
  tagged `v1.0.0-rc1`): bundles Sprint 1 (Adaptive Speaking), Sprint 2
  (Adaptive Reading), Sprint 3 (Adaptive Listening), Sprint 4 (Adaptive
  Writing). All four are code-complete, QA-gated, and CTO-approved.
  - [x] Adaptive Learning (all four modules, code-complete)
  - [x] Monitoring — Sentry environment tagging (dev/rc1/production, one
    project), backend dev-mode gate mirroring the frontend
  - [x] Analytics — PostHog environment tagging (one project, no per-env
    key split), missing `login_completed`/reading+listening `score_viewed`
    events added
  - [x] Playwright — 5 RC1 smoke tests (landing CSP, `/health`, pricing,
    login, signup) written and passing locally (`npm run test:e2e`)
  - [x] Merge `develop` → `main` for Speaking (2026-08-08, `9f508508`) and
    Reading/Listening/Writing (2026-08-08, merge commit on top of
    `9f508508`)
  - [ ] Live verification — click-through of all four insights cards
    plus the monitoring/analytics changes above against real (rc1 or
    production) traffic (see Definition of Done in
    [PRODUCT_OS.md](PRODUCT_OS.md)) — do after this merge deploys
  - [ ] Founder approval

  This closes the git-workflow portion of RC1. Live verification and
  founder approval remain open — see [BACKLOG.md](BACKLOG.md).

- **RC2 — Adaptive Dashboard V1** (opened 2026-08-08, closed 2026-08-08,
  tagged `v1.1.0-rc2`): cross-module dashboard (per-module progress cards,
  cross-module Weak Skills list, Adaptive Recommendation card routing to
  the weakest module) built on the same skill-graph spine RC1 shipped,
  plus its own QA layer.
  - [x] Adaptive Dashboard V1 (code-complete)
  - [x] Playwright — 7 new RC2 dashboard scenarios (load, existing/new/
    one-session learner, responsive layout, uncaught-exception guard, API
    verification), passing locally alongside all 5 RC1 smoke tests
    (`frontend/tests/e2e/dashboard.spec.ts`)
  - [x] `docs/RC2_QA_CHECKLIST.md` — manual founder click-through list
  - [x] `tsc --noEmit` clean
  - [x] Merge `develop` → `main` (2026-08-08, `b683fde8`)
  - [ ] Live verification — click-through of
    [RC2_QA_CHECKLIST.md](RC2_QA_CHECKLIST.md) against real (preview or
    production) traffic — do after this merge deploys
  - [ ] Founder approval

  Same open item RC1 has: git-workflow portion closed, live verification
  and founder approval remain open. See
  [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).

- **RC3 — AI Content Studio** (opened 2026-08-08, closed 2026-08-09): unlike
  RC1/RC2, this RC bundled four sequential sub-sprints rather than one —
  Content Production, Review Workflow, and Staff Role Management were real
  future work, not hypothetical, so RC3 stayed open (and untagged) until all
  of them landed, not just the first.
  - [x] **RC3.1 — Content Studio Foundation** (code-complete, QA-gated):
    admin-only dashboard/library/detail pages, read-only, no schema
    change. Merged `develop` → `main` (`d32c5327`).
  - [x] **RC3.2 — AI Draft Generator** (code-complete): `/admin/content-
    studio/generate` calls the AI and returns unpersisted draft(s);
    `POST /drafts` persists to `generated_content_drafts` only — never to
    a production content table. Merged `develop` → `main` (`31aa6149`).
  - [x] **RC3.3 — Review Workflow, Publishing** (code-complete, migration
    applied, QA-gated): draft → review → approved → published/archived
    status machine, revision log (real content/metadata changes only, not
    status-only transitions or renames), Publish Preview that matches
    Publish exactly, Speaking/Writing → `scenarios` (Writing includes
    `key_points`), Reading/Listening → standalone `reading_passages`/
    `listening_sections` rows (`is_active=false`, no `reading_tests`/
    `listening_tests` row created — Test Builder grouping stays deferred),
    Vocab/Grammar correctly blocked from publishing. Schema:
    `supabase/migrations/20260808050000_draft_review_workflow.sql`,
    applied to the live `Nurse Ai` Supabase project 2026-08-09.
  - [x] **RC3.4 — Staff Role Management** (code-complete, QA-gated):
    replaced the binary Grant/Revoke Admin toggle with a five-tier Staff
    Role selector (None/Support/Analyst/Admin/Owner) on the Users list and
    detail pages, rank-based permission inheritance (`ROLE_RANK` in
    `admin.py`), role changes restricted to Owner only, last-remaining-
    Owner demotion blocked, every change audit-logged
    (`staff_role_changed`, old/new role, changed-by).
  - [x] Final QA — 14/14 Playwright + direct-API pass against the live
    Supabase project (role assignment, Owner inheritance across every
    require_* tier, last-Owner protection, non-Owner blocked from
    assigning Owner at both the UI and API layer, learner accounts
    confirmed to have zero staff permissions, full Content Studio
    lifecycle generate→save→edit→submit→approve→reject→preview→publish→
    unpublish, revision-log correctness, audit trail correctness, zero
    500s including a deliberate concurrent double-publish race). Zero
    code changes required as a result — no blocking defects found.
  - [ ] Live verification — click-through against real (`develop`-deployed
    or production) traffic (see Definition of Done in
    [PRODUCT_OS.md](PRODUCT_OS.md)) — do after this merges to `main`; the
    QA above ran against local dev wired to the live Supabase project, not
    a deployed environment.
  - [ ] Founder approval
  - [ ] Tag — deferred until merged `develop` → `main` (see Versioning
    strategy above).

## Rollback

**Status: V1**

Code rollback: redeploy the previous commit on Vercel/Render (both keep
deployment history). Database rollback: hand-written, emergency-only SQL
per migration in `backend/migrations/rollback/` — see ADR-007 in
[DECISIONS.md](DECISIONS.md) and that directory's README for exactly when
running one is appropriate. The two are independent — a code rollback does
not imply a database rollback, and vice versa; check which one the
incident actually requires before running either.
