# Roadmap

Phased plan for SpeakOET. Phase 1 is complete; Phase 2 is current. Phases
3-5 depend on PMF signal and are directional, not committed — see
[BACKLOG.md](BACKLOG.md) for the "After PMF" bucket that feeds them.

Do not pull work from a later phase into the current one without an ADR
(see [DECISIONS.md](DECISIONS.md)) explaining why the dependency ordering
below doesn't apply.

---

## Phase 1 — Core Product (complete)

**Objectives**: Prove the flagship mechanism (live AI patient roleplay,
rubric-scored) and reach full OET syllabus coverage.

**Features**:
- Speaking module: 100+ clinically-written scenarios, real-time voice
  roleplay, 9-criteria OET rubric scoring.
- Writing module: OCR-based response capture, official rubric scoring.
- Reading module: Part A/B/C, MCQ + short-answer, mistral-ocr content
  pipeline.
- Listening module: audio playback, transcript-based scoring.
- Full Mock Test: all 4 sub-tests in one timed session, unlocked band
  report.
- Subscription tiers (Free/Basic/Pro/Elite) via Razorpay.
- Progress dashboard: band trend, per-criterion breakdown, streaks,
  session history.

**Dependencies**: none (greenfield).

**Exit criteria**: all four sub-tests + Mock Test live and rubric-scored.
✅ Met 2026-07-26 (Mock Test was the last piece).

---

## Phase 2 — Trust & Reliability Hardening (current)

**Objectives**: Make the product safe to scale traffic into — security,
cost control, and operational visibility — and lay the schema groundwork
for cross-module personalization.

**Features**:
- Auth hardening: local JWT verification, logout revocation, generic error
  messages, impersonation token hardening.
- Cost hardening: atomic usage-increment RPCs, session duration caps,
  AI Model Registry (routing + fallback + health + audit rollback).
- Abuse hardening: rate limiting, CAPTCHA on public AI-backed endpoints,
  request timeouts, size caps.
- Operational visibility: Sentry, PostHog, cron-wired maintenance jobs, CI.
- **Learner Brain Foundation** (schema only): `user_skill_stats.product`
  column, `skill_observations` append-only log. Prepares the data model for
  cross-module weak-skill detection without committing to the read/write
  service layer yet.
- **Adaptive Speaking V1** (Sprint 1, ADR-008 in
  [DECISIONS.md](DECISIONS.md)): a rule-based, same-session coaching
  recommendation for Speaking, reading `user_skill_stats` as it already
  exists in production — no new table, no migration. Distinct from (and
  not a dependency of) the Phase 3 `skill_observations` write path,
  rollup/decay job, and cross-module Study Hub surface below, which remain
  fully deferred. ✅ Complete, CTO-approved 2026-08-08.

**Dependencies**: Phase 1 complete (needs live traffic and paid users to
harden against).

**Exit criteria**: no open P0 security finding; AI spend has a hard
per-user ceiling and a routing layer with fallback; every scheduled job
verified live. Frontend audit P0/P1 items (see
[BACKLOG.md](BACKLOG.md) → Now) triaged and closed.

---

## Phase 3 — Learner Brain (Future)

**Objectives**: Turn per-module scoring into a cross-module personalization
loop — tell a learner what to practice next based on their actual weakest
skills, not just let them pick a module.

**Features**:
- Service-layer writes into `skill_observations` alongside the existing
  `user_skill_stats` upsert (additive, not a replacement — see ADR-004 in
  [DECISIONS.md](DECISIONS.md)). No module writes to it yet — Adaptive
  Speaking V1 (Phase 2, Sprint 1, ADR-008) deliberately does not depend on
  this table.
- Rollup/decay job so `user_skill_stats` EMA reflects recency, not just a
  running average.
- Study Hub recommendation surface driven by the skill graph
  (`skill_graph.py`'s `get_weakness`) across all four modules, not just
  within one.
- Formalize the **Observation Contract** — the schema every module's
  scoring pipeline writes into (see [ARCHITECTURE.md](ARCHITECTURE.md)).

**Dependencies**: Phase 2's `skill_observations` table live in production
with real data accumulating (needs weeks of Phase 2 running before there's
enough history to roll up meaningfully).

**Exit criteria**: Study Hub surfaces a real, data-backed "practice this
next" recommendation, not a static list.

---

## Phase 4 — Content Brain + Knowledge Brain (Future)

**Objectives**: Scale content production and content quality without
scaling headcount linearly — today's content pipeline is AI-assisted
generation with human review per item; this phase makes that a system.

**Features** (see [CONTENT_STRATEGY.md](CONTENT_STRATEGY.md)):
- AI Content Factory: templated generation for scenarios/reading
  passages/listening scripts at volume, still human-reviewed before
  publish.
- Knowledge tagging: content tagged against the skill graph's `skill_tag`
  taxonomy so the Learner Brain (Phase 3) can route practice to specific
  content, not just a module.
- Human review workflow as a first-class step, not an ad hoc founder pass.

**Dependencies**: Phase 3's skill-tag taxonomy needs to exist and be
stable before content can be tagged against it.

**Exit criteria**: content volume scales without a proportional increase
in founder/reviewer hours per published item.

---

## Phase 5 — AI Orchestrator + Multi-Product (Post PMF)

**Objectives**: Only pursue after PMF is confirmed on OET. Generalize the
platform (AI dispatch, Learner Brain, content pipeline) to a second exam
product (NCLEX/IELTS are the named candidates) without a rewrite.

**Features**:
- AI Orchestrator: multi-step AI workflows (e.g. LangGraph-style) replacing
  today's single-call-per-purpose dispatch, where a purpose genuinely needs
  multi-step reasoning rather than one scoring call.
- LiteLLM or equivalent evaluated as a replacement for the hand-rolled
  `ai_registry.py` dispatcher, if provider surface area grows enough to
  justify it.
- Second product onboarded using the `product`-scoped schema laid down in
  Phase 2 (`user_skill_stats.product`, `skill_observations.product`).

**Dependencies**: Phase 3 + 4 live and proven on OET; explicit PMF signal
(retention + revenue, not just usage) before starting.

**Exit criteria**: not defined yet — this phase is directional. Define exit
criteria when it's actually greenlit, not before.
