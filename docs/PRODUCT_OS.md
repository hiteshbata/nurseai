# SpeakOET Product OS

**Source of truth for how SpeakOET is built.** Every feature, bug fix, and
architecture decision references this document set. If a decision here
conflicts with code, the code is wrong (or this doc is stale and must be
updated in the same PR that changes direction) — it does not mean silently
diverge.

This is not user-facing documentation. It is the internal operating system
for engineering the product.

Document set: [ROADMAP.md](ROADMAP.md) · [SPRINTS.md](SPRINTS.md) ·
[BACKLOG.md](BACKLOG.md) · [DECISIONS.md](DECISIONS.md) ·
[ARCHITECTURE.md](ARCHITECTURE.md) · [MODULES.md](MODULES.md) ·
[AI_SYSTEM.md](AI_SYSTEM.md) · [DATABASE.md](DATABASE.md) ·
[CONTENT_STRATEGY.md](CONTENT_STRATEGY.md) · [RELEASES.md](RELEASES.md)

---

## Vision

Every nurse who wants to work in Australia, the UK, or New Zealand can
prepare for and pass OET without a human tutor, a classroom course, or a
second mortgage on their time — because an AI coach gives them the same
rubric-accurate feedback a human examiner would, on demand, in their own
shift-work schedule.

## Mission

Build the AI coach that covers full OET syllabus depth — Speaking, Writing,
Reading, Listening — with real, rubric-based scoring on every sub-test, so
practice on SpeakOET feels like the real exam and preparation transfers
directly to test-day confidence.

## North Star Metric

**Weekly Active Practicers who complete a scored session** (any module,
scored against the real OET rubric). Not signups, not logins — a completed,
scored rep. This is the leading indicator of both retention and the thing
that actually produces exam-day results, which is the entire value
proposition.

## Product Principles

1. **Full-syllabus depth over single-skill depth.** Every module must be
   credible against the real OET rubric, not a placeholder. See
   [MODULES.md](MODULES.md) for per-module status.
2. **Practice must feel exam-real.** Live roleplay, real rubric, real
   timing — so confidence transfers to the actual test.
3. **Fully self-serve.** Affordable alternative to human tutors and
   classroom courses. No sales-assisted onboarding required, ever.
4. **Ship honest claims only.** Never state a module, result, or proof
   point that isn't real yet. No fabricated testimonials, counts, or press.
5. **One source of truth.** This document set is authoritative. A decision
   not recorded in [DECISIONS.md](DECISIONS.md) is not a locked decision.

## Current Phase

**Phase 0 — Post-launch hardening + Learner Brain foundation.** All four OET
sub-tests plus Mock Test are feature-complete and live. Current work is
security/reliability hardening (see completed items below) plus laying the
groundwork for cross-module personalization (skill graph, observation
history). See [ROADMAP.md](ROADMAP.md) for phase detail.

## Current Sprint

See [SPRINTS.md](SPRINTS.md) for the live sprint board. As of 2026-08-08:
**Learner Brain Foundation** — tag skill-graph rows by product
(`user_skill_stats.product`), add append-only observation history
(`skill_observations`). Migrations written, not yet applied. Sprint 1
(Adaptive Speaking V1) closed this same day — see Completed Work below.

## Current Milestone

AI Model Registry (shipped 2026-08-07/08): every hardcoded model ID in the
backend replaced by a DB-backed registry with purpose routing, fallback,
health checks, and audit-logged rollback. See
[docs/ai-model-registry.md](ai-model-registry.md) for the full handover and
[AI_SYSTEM.md](AI_SYSTEM.md) for how it fits the wider AI architecture.

## Completed Work

- **All 4 OET sub-tests + Mock Test**: Speaking (live AI patient roleplay,
  9-criteria rubric), Writing (OCR + official rubric scoring), Reading
  (Part A/B/C, MCQ + short-answer), Listening (audio + transcript scoring),
  full timed Mock Test (all 4 parts, unlocked band report).
- **Security hardening**: local JWT verification (no per-request Supabase
  round-trip), RLS on all user tables, rate limiting + size caps on
  upload/chat endpoints, generic auth error messages (no `str(e)` leaks),
  server-side session-duration caps, atomic cost-tracking RPCs, CAPTCHA +
  timeout on AI-backed public endpoints.
- **Admin panel**: RBAC, audit log, AI cost/margin tracking, AI Model
  Registry UI, reminders, lead tracking, impersonation (hardened —
  no refresh token in client storage).
- **Platform**: CI (backend pytest + ruff, frontend build), Sentry
  (frontend + backend), PostHog as primary analytics tool, cron jobs for
  reminders/pruning/usage-reset (5 jobs, all live), blog on Sanity CMS,
  SEO fundamentals (sitemap, robots, OpenGraph).
- **Sprint 1 — Adaptive Speaking V1** (ADR-008, complete + CTO-approved
  2026-08-08): rule-based, same-session coaching recommendation on the
  Speaking results page — strongest/weakest skill, a recommendation
  reason, one actionable improvement, a confidence message, and a
  recommended next scenario. Ships entirely on `user_skill_stats` as
  already deployed, no schema change. See
  [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).

## In Progress

- **Learner Brain Foundation** — see Current Sprint above.
- Frontend audit follow-through (29 findings from 2026-07-31 audit; 5 P0 /
  8 P1 / 11 P2 / 5 P3, tracked in the founder's vault, not yet triaged into
  this backlog — see [BACKLOG.md](BACKLOG.md) Now).
- Production live-verification of Adaptive Speaking V1's insights card
  (code/QA complete and CTO-approved; the click-through against real
  production traffic is still open — see [BACKLOG.md](BACKLOG.md) Now).

## Next Work

See [BACKLOG.md](BACKLOG.md) → **Now** and [ROADMAP.md](ROADMAP.md) →
current phase for the ordered list. Do not start Learner Brain service-layer
work (writing to `skill_observations`, rollup jobs) until it is pulled into
an active sprint in [SPRINTS.md](SPRINTS.md) — the migrations exist ahead of
the code on purpose (see ADR-004 in [DECISIONS.md](DECISIONS.md)). Sprint 1
(Adaptive Speaking V1, ADR-008) is unrelated — it doesn't touch
`skill_observations` at all.

## Frozen Decisions

The following are locked. Changing any of them requires a new ADR in
[DECISIONS.md](DECISIONS.md), not a PR description.

- **Architecture is locked** — no redesign of the module/AI/data
  architecture described in [ARCHITECTURE.md](ARCHITECTURE.md) without an
  ADR.
- **Backend enforces authorization itself**, using the service-role key.
  Supabase RLS is defense-in-depth, not the primary boundary. See ADR-002.
- **AI dispatch goes through the AI Model Registry.** No new hardcoded
  model IDs in application code. See ADR-003 and
  [AI_SYSTEM.md](AI_SYSTEM.md).
- **`user_skill_stats` stores current state only; `skill_observations` is
  the append-only history.** Do not replace the EMA rollup with a
  query-time aggregate over raw observations — it's a different
  performance profile for a query the Study Hub calls on every load. See
  ADR-004.
- **One exam product (OET) today; schema is product-scoped in
  anticipation of a second (NCLEX/IELTS), not built for it.** Don't add
  product-specific branching until a second product is actually funded.
- **No fabricated social proof.** Ever. See Product Principle 4.

## Development Rules

- **Reference this doc set before designing.** If a feature touches a
  module, read its entry in [MODULES.md](MODULES.md) first. If it touches
  AI dispatch, read [AI_SYSTEM.md](AI_SYSTEM.md). If it touches schema,
  read [DATABASE.md](DATABASE.md).
- **New architectural decisions get an ADR** in [DECISIONS.md](DECISIONS.md)
  before code, not after. A decision made only in a PR description or a
  Slack-equivalent message is not durable.
- **No speculative abstraction.** Build for the module/product that exists
  today. Multi-product, multi-tenant, or multi-language scaffolding needs
  an ADR justifying it before it's written — see the `product` column
  precedent in ADR-004 for what "justified ahead of need" looks like (one
  column + one constraint, not a framework).
- **Migrations are forward-only in normal operation.** Rollback SQL is
  emergency-only, hand-written per migration, and lives in
  `backend/migrations/rollback/` — see [DATABASE.md](DATABASE.md).
- **Solo/small-team reality.** There is no dedicated QA team and no staging
  environment today. See [RELEASES.md](RELEASES.md) for what that means for
  how changes ship.

## Definition of Done

A feature or fix is done when:

1. **Code merged to `main`** and deployed (Vercel for frontend, Render for
   backend — auto-deploy on merge, see [RELEASES.md](RELEASES.md)).
2. **CI green** — backend pytest + ruff (`F` ruleset), frontend
   `tsc --noEmit` + build, all passing on the merge commit.
3. **Live-verified**, not just unit-tested, for anything touching a paid
   flow, auth, or AI scoring — click through it (or script it) against the
   real deployed environment, not just local. This project's history shows
   repeated "fixed, not yet live-verified" states that later needed a second
   pass; live-verify before calling it done where it's cheap to do so.
4. **This doc set updated in the same PR** if the change touches an ADR,
   module status, schema, or roadmap phase. Docs drifting from reality is
   the failure mode this OS exists to prevent.
5. **No new hardcoded secrets, model IDs, or `str(e)` error leaks**
   introduced (see Frozen Decisions and ADR-003).
