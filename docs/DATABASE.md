# Database

Supabase (Postgres). This file summarizes current schema by area, approved
future changes, frozen rules, and the migration strategy. It is not a full
schema dump — for exact column lists, use
`mcp__claude_ai_Supabase__list_tables` against the live project rather than
trusting this doc to be column-perfect; it's accurate as of 2026-08-08 but
will drift.

---

## Current schema (by area)

**Auth / users**: managed by Supabase Auth (GoTrue) — the backend does not
own the users table. `authenticated_user_rls` (2026-08-02) hardened RLS
across user-facing tables to scope to the authenticated role.

**Skill graph / Learner Brain foundation**:
- `user_skill_stats` — current-state EMA per `(user_id, product,
  skill_tag)`, unique on that triple (re-scoped from
  `(user_id, skill_tag)` on 2026-08-08 — see ADR-005). `product` defaults
  `'OET'`. Indexed on `(user_id, product)`.
- `skill_observations` — append-only raw observation log (ADR-001):
  `id, user_id, product, skill_tag, score, source_module, observed_at`.
  RLS on, read-only for the owning user, service-role-only writes. Indexed
  on `(user_id, product, observed_at DESC)`. No writers yet — Adaptive
  Speaking V1 (Sprint 1, ADR-008) reads/writes `user_skill_stats` only, by
  design, to avoid depending on a migration this table needs
  (`user_skill_stats.product`/`skill_observations` are both still pending
  in production as of 2026-08-08, see the "Learner Brain Foundation" sprint
  in [SPRINTS.md](SPRINTS.md)).

**AI Model Registry** (added 2026-08-07, extended through
`..._v5.sql`):
- `ai_models` — `id, provider, model_name, display_name, api_base,
  enabled, is_default, priority, fallback_model_id (self-FK),
  last_health_status, last_health_latency_ms, last_health_checked_at,
  last_health_error, created_at, updated_at`. Unique on
  `(provider, model_name)`. RLS on, no policies — service-role only.
- `ai_model_purposes` — `purpose (PK, free text), model_id (FK →
  ai_models, ON DELETE RESTRICT), updated_at`.
- `ai_usage_events` (pre-existing, extended) — added `purpose,
  latency_ms, success, error_message`.

**Cost / billing**:
- `refunds` (2026-08-02), atomic session-cost increment RPC
  (`atomic_session_cost_increment`, 2026-08-02) — see ADR around GET
  mutation removal (M3): usage reads no longer have write side effects;
  the reset write moved into the `check-and-increment` RPC path.
- `session_usage.scored_at` (2026-08-02).
- `bonus_sessions` check constraint (2026-08-02).

**Content**:
- `mock_test_packs` (2026-07-26) — packaged Mock Test content sets.
- `scenarios.difficulty` check constraint widened (2026-07-31).
- `users_trgm_search` (2026-08-03) — trigram index for admin user search.

**Audit / admin**:
- `audit_log` — pre-existing, reused by AI Model Registry rollback
  (ADR-007 pattern) rather than a new versioning table.

**Composite indexes**: `composite_indexes` migration (2026-08-02) added
query-pattern-driven indexes; no new ones added since without a measured
query to justify them.

---

## Approved future changes

- **Service-layer writes into `skill_observations`** (Phase 3, no schema
  change needed — table already exists per ADR-001/004).
- **Rollup/decay job** reading `skill_observations` to refresh
  `user_skill_stats` on a schedule, not just on-write (Phase 3). Table
  shape for this is undecided — do not pre-build a rollup table ahead of
  the job design.
- **Knowledge-tagging schema** for content (Phase 4) — depends on the
  skill-tag taxonomy being stable first; no schema exists yet, don't
  invent one ahead of Phase 3 landing.
- **Second `product` value** (e.g. `'NCLEX'`) — schema already supports
  this (ADR-005); Post PMF only, see [BACKLOG.md](BACKLOG.md).

## Frozen rules

- **RLS is defense-in-depth, not the primary authorization boundary**
  (ADR-002). Every table the backend writes to via service-role key still
  needs an explicit ownership check in application code.
- **`skill_observations` (and any future Observation Contract table) is
  append-only** — no UPDATE, no DELETE, ever (ADR-001). If a correction is
  needed, append a new row; do not mutate history.
- **`user_skill_stats` stays a current-state rollup** — do not replace its
  read pattern with a query-time aggregate over `skill_observations`
  (ADR-004). They serve different reads.
- **No `api_key` columns.** Provider credentials live in env vars only,
  never in a table, even an admin-only one (see
  [AI_SYSTEM.md](AI_SYSTEM.md)).
- **New unique/foreign-key constraints must account for `product`
  scoping** on any table that could plausibly need multi-product
  separation later (skill/content/progress tables) — see ADR-005 for what
  "cheap now, expensive later" looks like. This does not apply to
  tables that are inherently single-product-agnostic (billing, auth).

## Migration strategy

- **Forward-only in normal operation.** Every schema change is a new file
  in `supabase/migrations/`, timestamp-prefixed, never edited after being
  applied to any environment.
- **Rollback SQL is hand-written, per-migration, emergency-only** — lives
  in `backend/migrations/rollback/`, named `<forward-migration-name>
  -rollback.sql`. Not every migration gets one; only where the founder
  judged an emergency revert plausible. See ADR-007 and
  `backend/migrations/rollback/README.md` for exactly when it's safe to
  run one (short version: forward migration is applied, it's actively
  causing a production incident, and you've read the rollback file and
  understand what it undoes — never "just in case").
- **No down-migration is auto-generated or trusted.** A bad forward
  migration is normally fixed with a new forward migration, not a revert.
- **Comments explain the "why" inline in the migration file itself** — see
  `20260808010000_learner_brain_product_column.sql` and
  `20260808020000_skill_observations_log.sql` for the house style: explain
  why now (cheap) vs. later (expensive), and what's deliberately *not*
  included (no trigger, no backfill, no worker — service-layer work is
  separate).
- **Applying to production**: via Supabase migration tooling
  (`mcp__claude_ai_Supabase__apply_migration` / CLI), checked against
  `list_migrations` first to confirm current state — never assume local
  migration history matches what's actually applied in prod.
