# Architecture Decision Records

Every locked architectural decision lives here as an ADR. A decision made
in a PR description, a chat message, or a founder's vault note is not
binding until it's recorded here. Reference an ADR number from code
comments, PRs, and other docs in this set rather than re-explaining the
reasoning inline.

**Format**: Observation → Reason → Consequences → Status.

**Status values**: `Proposed` (not yet binding) · `Accepted` (binding,
follow it) · `Superseded by ADR-NNN` (historical, do not follow).

---

## ADR-001: The Observation Contract is immutable and append-only

**Observation**: Every module's scoring pipeline (Speaking, Writing,
Reading, Listening) eventually needs to write a graded result somewhere the
Learner Brain can read across modules. That write target — the
"Observation Contract" — must never be edited or deleted in place once
written; only appended to.

**Reason**: `user_skill_stats` already proved the failure mode of a
mutable, overwrite-in-place rollup: each new score overwrites the last EMA,
so the system can answer "what's my weakest skill right now" but can never
answer "how did this skill trend," can never have `EMA_ALPHA` retuned
retroactively, and can never feed a future mastery-decay or band-prediction
model. Those all need the individual data points, not just their moving
average. An immutable log is the only shape that supports both today's
"current state" read and tomorrow's "replay history" read from the same
source of truth.

**Consequences**: `skill_observations` (added 2026-08-08, see
[DATABASE.md](DATABASE.md)) is the first concrete instance of this
contract — one append-only row per graded observation, no update, no
delete, service-role-write-only. Any future scoring pipeline that wants to
feed the Learner Brain writes into this shape, not a new mutable table.
Rollups (like `user_skill_stats`) may exist *alongside* the contract as
derived, mutable read-optimizations, but are never the record of truth.

**Status**: Accepted. Schema laid down 2026-08-08 (migration
`20260808020000_skill_observations_log.sql`); nothing writes to it yet —
the write path is Phase 3 work (see [ROADMAP.md](ROADMAP.md)).

---

## ADR-002: The backend enforces authorization itself; RLS is defense-in-depth

**Observation**: FastAPI backend endpoints use the Supabase service-role
key and re-check ownership/permission in application code before acting.
Row Level Security policies exist on user-facing tables but are not relied
upon as the primary boundary.

**Reason**: The service-role key bypasses RLS by design, so any endpoint
using it is already outside RLS's enforcement — authorization has to
happen somewhere the service-role key can't skip, which is the application
layer. RLS stays on as a second layer in case a code path is ever added
that queries with a user-scoped key instead.

**Consequences**: Every new backend endpoint that touches user data must
explicitly check ownership/permission in code — do not assume RLS will
catch a missing check. RLS policy changes are still worth making
correctly (see the 2026-08-02 `authenticated_user_rls` migration and the
rollback-emergency-only pattern in ADR-007), but a bug in a policy is not
expected to be the only thing standing between a request and unauthorized
data.

**Status**: Accepted.

---

## ADR-003: All AI model dispatch goes through the AI Model Registry

**Observation**: No application code may hardcode a provider/model ID
(e.g. `"gpt-4o"`, `"gemini-1.5-flash"`) at a call site. Every AI call
resolves a `purpose` string through `ai_registry.py` against the
`ai_models` / `ai_model_purposes` tables.

**Reason**: Before this registry (built 2026-08-07/08), every model swap —
provider outage, pricing change, quality regression — required a code
change and a deploy. With 20+ AI call sites across scoring, OCR, content
generation, and realtime voice, that was both slow and error-prone (easy to
miss a call site). A DB-backed registry with admin-panel editing and a
60-second cache makes model changes a config change, not a deploy.

**Consequences**: Adding a new AI-backed feature means adding a new
`purpose` and mapping it in `/admin/ai-models` before the code path runs
unmapped purposes fail gracefully (`AI_PURPOSE_NOT_CONFIGURED`, never a
raised exception to the caller — see [AI_SYSTEM.md](AI_SYSTEM.md)). New
providers that speak the OpenAI chat-completions format need zero code
change; genuinely different wire formats (Bedrock SigV4, etc.) need a new
dispatch family, not a special case at the call site.

**Status**: Accepted. Live 2026-08-08, all 30 existing purposes migrated
(see [docs/ai-model-registry.md](ai-model-registry.md)).

---

## ADR-004: `skill_observations` is additive; it does not replace `user_skill_stats`

**Observation**: The new append-only observation log
(`skill_observations`) is written *alongside* the existing
`user_skill_stats` upsert, not instead of it. `user_skill_stats` keeps
being the only thing the Study Hub's weakness queries read from.

**Reason**: `user_skill_stats`'s overwrite-in-place EMA is correct and
cheap for "what's my weakest skill right now," which is all the Study Hub
needs today. Replacing it with a query-time aggregate over raw
`skill_observations` rows would trade a cheap indexed lookup for a
scan-and-aggregate on every Study Hub load, for a benefit (historical
replay, retroactive re-tuning) that nothing reads yet. Keep both: cheap
current-state table for today's read pattern, immutable log (ADR-001) for
tomorrow's.

**Consequences**: This is a deliberate, temporary duplication of
information across two tables. It stays justified only as long as
`skill_observations` has real readers on a realistic timeline (Phase 3, see
[ROADMAP.md](ROADMAP.md)). If Phase 3 stalls indefinitely, revisit whether
the table should keep being written to.

**Status**: Accepted.

---

## ADR-005: Schema is product-scoped ahead of need, application logic is not

**Observation**: `user_skill_stats` and `skill_observations` both carry a
`product` column (`DEFAULT 'OET'`), and uniqueness/indexes are scoped by
it. No application code branches on `product` — there is exactly one
product today.

**Reason**: Adding the column now, while there is one product and zero
historical rows that could be ambiguous, is free — every existing row gets
the correct default automatically and no calling code needs to change
(inserts that don't name the column keep working). Adding it later, after
a second product exists, means a backfill guess across however much
history has accumulated by then. The column is cheap insurance; it is not
a bet that a second product is coming soon.

**Consequences**: Do not add product-specific branching, config, or
abstraction anywhere else in the codebase (routing, content, UI) until a
second product is actually funded and scoped — see [BACKLOG.md](BACKLOG.md)
→ After PMF and Product Principle "no speculative abstraction" in
[PRODUCT_OS.md](PRODUCT_OS.md). The column is the one exception, justified
by its near-zero cost; it is not a precedent for pre-building the rest of
multi-product support.

**Status**: Accepted.

---

## ADR-006: JWTs are verified locally, not by a per-request Supabase round-trip

**Observation**: `get_current_user` verifies the Supabase-issued JWT
in-process (HS256 + JWKS), rather than calling Supabase on every
authenticated request to validate the token.

**Reason**: A per-request round-trip to Supabase for auth verification adds
latency and load to every single authenticated call, for a check that's
cryptographically verifiable locally once the signing secret/JWKS is known.

**Consequences**: The backend must keep its local verification logic in
sync with however Supabase issues/rotates its signing keys (JWKS
fetch/cache), and logout must explicitly revoke refresh tokens server-side
(scope=global) since local verification alone can't observe a revocation —
this is why logout revocation exists as its own explicit endpoint rather
than being implied by "the token looks valid."

**Status**: Accepted. Live-verified in production 2026-07-11.

---

## ADR-007: Migrations are forward-only; rollback SQL is hand-written and emergency-only

**Observation**: Normal deploys only ever run forward migrations
(`supabase/migrations/`). Rollback SQL, when it exists, is a separate,
manually written file per migration in `backend/migrations/rollback/`, and
is documented as "emergency use only" — never part of the routine deploy
sequence.

**Reason**: Auto-generated down-migrations are frequently wrong or lossy
(e.g. a down-migration for an RLS hardening change would silently
re-open access). A hand-written rollback, reviewed at the same time as the
forward migration, is safer than trusting a generated inverse — but it's
still only meant for an active incident, not routine schema iteration
(the normal fix for a bad migration is a new forward migration, not a
rollback).

**Consequences**: Not every migration gets a rollback file — only ones
where the founder judged an emergency revert plausible enough to write one
in advance. See `backend/migrations/rollback/README.md` for the exact
conditions under which running one is appropriate.

**Status**: Accepted.

---

## ADR-008: Adaptive Speaking V1 ships on the existing schema, with no dependency on `skill_observations`

**Observation**: [ROADMAP.md](ROADMAP.md) Phase 3 and the "Learner Brain
Foundation" sprint in [SPRINTS.md](SPRINTS.md) both defer the append-only
`skill_observations` write path, a rollup/decay job, and any cross-module
recommendation surface until Phase 3 starts — which depends on production
migrations being applied and weeks of history accumulating first. An
earlier draft of Sprint 1 ("Adaptive Speaking V1") proposed pulling the
`skill_observations` write forward for Speaking alone, requiring the two
pending Learner Brain Foundation migrations to be applied to production as
a prerequisite. On review, that dependency was rejected: Sprint 1's actual
goal (a same-session, rule-based coaching insight) does not need a new
table or a new migration to be true — it needs `user_skill_stats`, which is
already live in production, unmodified, today.

**Reason**: `user_skill_stats` (current-state EMA per `user_id, skill_tag`,
unique on that pair) already carries everything a per-skill weakest/
strongest read and a rule-based recommendation need: `skill_graph.py`'s
`record_skill_observations` already upserts it on every Speaking
submission (V1, live), and `get_weakness` already reads it back
(`/speaking/weakness`, unmodified). Introducing `skill_observations` for
this milestone would mean requiring a production migration for a feature
that doesn't need one — speculative persistence in exactly the sense
[PRODUCT_OS.md](PRODUCT_OS.md)'s "no speculative abstraction" principle
warns against. The append-only log stays exactly where ADR-001 and the
"Learner Brain Foundation" sprint left it: schema written, no writers,
waiting on Phase 3 being pulled into an active sprint on its own terms.

**Consequences**: `skill_graph.py` is untouched beyond what was already
live — no new parameter, no new table write, still aggregation-only.
Validation moves to a new `app/services/observation_service.py`
(`validate_and_normalize(module, raw_scores)`), so `skill_graph.py` doesn't
also own that responsibility — this is the one new module this ADR
introduces, and it's schema-free (pure functions over dicts). The
recommendation (`speaking.py::_build_speaking_insights`) prefers
`get_weakness`'s rolled-up history when it has enough attempts behind it,
and falls back to the current session's own scores otherwise — still no
new read path, `get_weakness` is called exactly as `/speaking/weakness`
already calls it. No production migration is required to ship this
milestone. `skill_observations`, the rollup/decay job, and any cross-module
Study Hub surface remain Phase 3, unstarted, and now explicitly
*not* pulled forward — see [BACKLOG.md](BACKLOG.md) → Later.

**Status**: Accepted. Recorded 2026-08-08, superseding the
`skill_observations`-dependent draft of this ADR from earlier the same day.
