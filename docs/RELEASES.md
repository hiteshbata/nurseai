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

**Status: V1 (none) / Future (semantic, if ever needed)**

No version numbers, no git tags, no changelog today. The product ships
continuously; "what version is live" is answered by "what's the latest
commit on `main` that's deployed," not a version string. This is
appropriate for a single-deployment web product with no external API
consumers or installable artifact — introduce semantic versioning only if
a future need actually requires it (e.g. a public API with external
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

## Rollback

**Status: V1**

Code rollback: redeploy the previous commit on Vercel/Render (both keep
deployment history). Database rollback: hand-written, emergency-only SQL
per migration in `backend/migrations/rollback/` — see ADR-007 in
[DECISIONS.md](DECISIONS.md) and that directory's README for exactly when
running one is appropriate. The two are independent — a code rollback does
not imply a database rollback, and vice versa; check which one the
incident actually requires before running either.
