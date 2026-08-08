# Architecture

Summary of the approved architecture only. **Do not redesign anything
here** — if something below looks wrong or incomplete, raise it as a new
ADR proposal in [DECISIONS.md](DECISIONS.md), don't just change the code.

Every component is marked **V1** (live today), **Future** (approved
direction, not built), or **Post PMF** (directional only, not committed —
see [ROADMAP.md](ROADMAP.md) Phase 5).

---

## System map

```
                        ┌─────────────────────────┐
                        │   Frontend (Next.js)     │  V1
                        │   Vercel                 │
                        └────────────┬─────────────┘
                                     │ HTTPS
                        ┌────────────▼─────────────┐
                        │   Backend (FastAPI)       │  V1
                        │   Render                  │
                        │   - authz enforced here    │
                        │     (ADR-002)              │
                        └───┬───────────────┬────────┘
                            │               │
              ┌─────────────▼───┐   ┌───────▼─────────────┐
              │ Supabase         │   │ AI Model Registry    │  V1
              │ (Postgres + RLS  │   │ ai_registry.py        │
              │  + Auth + Storage)│   │ (ADR-003)             │
              └──────────────────┘   └───────┬───────────────┘
                                              │ purpose -> provider/model
                              ┌───────────────┼────────────────┐
                              │               │                │
                        ┌─────▼────┐   ┌──────▼─────┐   ┌──────▼──────┐
                        │ OpenAI    │   │ Google      │   │ Deepgram /   │  V1
                        │ Realtime  │   │ Gemini      │   │ Google TTS   │
                        │ (voice)   │   │ (scoring/   │   │ (STT/TTS,    │
                        │           │   │  OCR/etc.)  │   │  string      │
                        │           │   │             │   │  lookups)    │
                        └───────────┘   └─────────────┘   └──────────────┘

     ┌──────────────────────────── Future (Phase 3+) ─────────────────────────────┐
     │                                                                             │
     │   Module scoring ──writes──▶ Observation Contract ──rollup──▶ Learner Brain │
     │   (Speaking/Writing/         (skill_observations,             (skill_graph   │
     │    Reading/Listening)         ADR-001, append-only)            + Study Hub    │
     │                                                                 recs)         │
     │                                                                              │
     │   Content Brain (AI Content Factory + human review) ──tags──▶ Knowledge Brain │
     │                                                              (skill-tag       │
     │                                                               taxonomy)       │
     │                                                                              │
     │   AI Orchestrator (multi-step workflows) — replaces single-call dispatch    │
     │   only where a purpose needs multi-step reasoning                            │
     └──────────────────────────────────────────────────────────────────────────────┘
```

---

## Learner Brain

**Status: V1 (schema) / Future (service layer, Phase 3)**

The system that tracks what a learner is weak at, across modules, and
recommends what to practice next.

- **V1 today**: `user_skill_stats` (current-state EMA per
  `user_id, product, skill_tag`) and `skill_graph.py`'s `get_weakness`
  query, used within the Study Hub for single-module weakness display.
  Adaptive Speaking V1 (Sprint 1, ADR-008) reads this same EMA to drive a
  same-session, rule-based "practice this next" recommendation for
  Speaking, deliberately without touching `skill_observations`.
  `skill_observations` (append-only raw log) exists as a table but nothing
  writes to it yet.
- **Future (Phase 3)**: service-layer writes into `skill_observations`
  alongside the existing `user_skill_stats` upsert (ADR-004), a
  rollup/decay job, and a cross-module Study Hub recommendation surface.

See [ROADMAP.md](ROADMAP.md) Phase 3 and ADR-001/ADR-004 in
[DECISIONS.md](DECISIONS.md).

## Knowledge Brain

**Status: Future (Phase 4)**

The system that tags content (scenarios, reading passages, listening
scripts) against the same `skill_tag` taxonomy the Learner Brain uses, so a
detected weakness can route to specific content, not just a module. No
schema or code exists yet. Depends on the skill-tag taxonomy from Phase 3
being stable before content can be tagged against it.

## Content Brain

**Status: Future (Phase 4)**

AI-assisted content generation at volume, with human review as a required
step (not a replacement for it). Today's content pipeline (AI-assisted
generation, e.g. `generate_scenario_library.py`, `seed_scenarios.py`, per
existing scoring purposes like `scenario_library_generation`) is the
starting point this scales up, not a separate system. See
[CONTENT_STRATEGY.md](CONTENT_STRATEGY.md).

## AI Orchestrator

**Status: Future (Post PMF, Phase 5)**

Multi-step AI workflows (evaluated: LangGraph-style), for purposes that
genuinely need multi-step reasoning rather than one scoring call. Today
every purpose is a single call through the AI Model Registry
(primary → one fallback → graceful failure). Do not build this ahead of a
concrete purpose that needs it — the registry's single-call model has
handled every purpose so far, including scoring, OCR, and content
generation.

## Learning Engine

**Status: V1**

The per-module scoring pipelines that already exist and are live:
Speaking (real-time roleplay + 9-criteria rubric via `ai_scoring.py`),
Writing (OCR + official rubric), Reading (MCQ + short-answer grading),
Listening (audio + transcript scoring), and Mock Test (all four,
composited into a band report). See [MODULES.md](MODULES.md) for
per-module detail. This is the system that produces the observations the
Observation Contract (Future) will eventually capture uniformly.

## Observation Contract

**Status: V1 (first instance) / Future (formalized, module-wide)**

The append-only write target every scoring pipeline eventually writes a
graded result into. `skill_observations` (live schema, no writers yet) is
the first concrete instance. See ADR-001 in [DECISIONS.md](DECISIONS.md)
for the immutability rule and [DATABASE.md](DATABASE.md) for the table
shape.

## Core Personalization Loop

**Status: Future (Phase 3), depends on Observation Contract having real
writers**

```
Learner practices a module
        │
        ▼
Learning Engine scores it (V1, live)
        │
        ▼
Score written to Observation Contract (Future — service layer not built)
        │
        ▼
Learner Brain rolls it into current skill state (Future — rollup job not built)
        │
        ▼
Study Hub surfaces "practice this next" (Future — recommendation surface not built)
        │
        └──────────────► back to top
```

Today, the loop stops after step 1 for personalization purposes — scoring
happens and is shown to the learner, but nothing downstream of
`user_skill_stats`'s current-state read closes the loop into a
recommendation. Closing it is the entire point of Phase 3. Adaptive
Speaking V1 (Sprint 1, ADR-008) is a narrower, single-module version of
this same idea, built on `user_skill_stats` as it exists today rather than
waiting on this diagram's Observation Contract and rollup-job boxes —
see [DECISIONS.md](DECISIONS.md) for why that's a deliberately smaller
scope, not a preview of this loop.

---

## What is explicitly NOT part of this architecture

- No multi-tenant / white-label support. One product, one brand.
- No client-side authorization trust. See ADR-002 — backend enforces every
  check itself.
- No hardcoded AI model IDs at call sites. See ADR-003.
- No mutable "history" table — history is append-only or it doesn't exist
  (ADR-001).
