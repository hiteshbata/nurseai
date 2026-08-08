# Backlog

Everything not currently being built lives here, not in someone's memory or
a chat thread. If it's not in [SPRINTS.md](SPRINTS.md) as an active sprint,
it's in one of these five buckets.

Moving an item **into** Now requires it fit the current
[ROADMAP.md](ROADMAP.md) phase. Moving an item **out of** Never requires an
ADR explaining why the original rejection no longer holds.

---

## Now

Candidates for the next sprint, in the current roadmap phase (Phase 2 —
Trust & Reliability Hardening).

- Apply the two Learner Brain Foundation migrations to production and
  live-verify (finish the in-progress sprint — see [SPRINTS.md](SPRINTS.md)).
- Live-verify Adaptive Speaking V1's insights card against production
  traffic (code complete, QA-reviewed, and CTO-approved 2026-08-08 — the
  actual click-through on deployed `/speaking/score` hasn't happened yet;
  see [docs/IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md)).
- Triage the 29 findings from the 2026-07-31 frontend audit (5 P0 / 8 P1 /
  11 P2 / 5 P3) out of the founder's vault and into this backlog with real
  priority, instead of them sitting untracked.
- Confirm prod env vars for Turnstile CAPTCHA on study-plan generation
  (code is local-verified, not yet confirmed live per
  `project_captcha_rate_limit_study_plan_fixed`).
- Live-verify the still-unconfirmed hardening fixes: H4 (progress.py
  scenario_id), H5 (submit-test real MCQ grading), M3 (usage GET
  read-only), M6 (30-min session cap), M31 (scoring temperature=0.0) —
  all fixed in code, none yet confirmed against production traffic.

## Next

Queued after Now clears, still within Phase 2/3 scope.

- AI Model Registry admin UI click-through test with a real test admin
  account (deferred from the registry sprint — backend/frontend were
  verified by other means, but the actual admin flow was never clicked
  through).
- Learner Brain service layer: write to `skill_observations` alongside the
  existing `user_skill_stats` upsert in `skill_graph.py` (this is Phase 3
  work — only pull forward if Phase 2 closes early). Adaptive Speaking V1
  (Sprint 1, ADR-008) deliberately does not depend on this — see
  [DECISIONS.md](DECISIONS.md).
- Re-confirm the SECURITY DEFINER view fix from the 2026-07-26 Supabase
  advisor re-scan (flagged as unconfirmed in
  `project_audit_2026_07_13`).

## Later

Real, wanted, not urgent. Depends on Phase 3/4 work landing first.

- Cross-module Study Hub recommendation surface driven by the skill graph
  (needs weeks of `skill_observations` history to be meaningful — see
  [ROADMAP.md](ROADMAP.md) Phase 3). Distinct from Speaking's single-module
  rule-based recommendation shipped in Sprint 1 (ADR-008) — that one reads
  `user_skill_stats` directly, no `skill_observations` dependency.
- AI Content Factory (templated generation at volume) — see
  [CONTENT_STRATEGY.md](CONTENT_STRATEGY.md).
- Content metadata migration (skill tags, learning objectives, OET
  criteria, estimated duration, `ai_generated`/`human_reviewed` flags) and
  difficulty/specialty normalization proposed in
  [CONTENT_FOUNDATION.md](CONTENT_FOUNDATION.md) (Sprint 1.5, 2026-08-08) —
  proposal stage, needs review/approval before it's scheduled. Runs as
  parallel work alongside Adaptive Reading V1, which proceeds on the
  existing content library — not a blocker for it.
- Beginner-tier Reading and Listening content — currently zero items at
  that difficulty in either module (see
  [CONTENT_FOUNDATION.md](CONTENT_FOUNDATION.md) §1).
- WhatsApp integration — paused pending provider choice and use-case
  priority (reminders? lead nurture? support?). No architecture decided.
- AI cost/margin dashboard beyond what the admin panel already shows
  (deliberately deferred — the raw `ai_usage_events` data exists, the
  dashboard view does not).
- **UI / Animation Review** (flagged by the impeccable design hook during
  Sprint 1's Speaking results-page work, 2026-08-08 — pre-existing, not
  introduced by that change, deliberately not fixed inline to avoid
  derailing the sprint):
  - Review pronunciation loading spinner (`SpeakingSession.tsx`).
  - Review typing indicator animation (bounce-easing on the
    "patient is typing" dots).
  - Review OET score reveal animation (bounce/overshoot easing on the band
    reveal).
  - Confirm accessibility (reduced motion).
  - Confirm performance on low-end devices.

## After PMF

Do not start until retention + revenue signal confirms OET product-market
fit. See [ROADMAP.md](ROADMAP.md) Phase 5.

- Second exam product (NCLEX or IELTS) onboarded onto the
  `product`-scoped schema.
- AI Orchestrator (multi-step AI workflows, e.g. LangGraph-style) replacing
  single-call-per-purpose dispatch.
- LiteLLM (or equivalent) evaluated as a replacement for the hand-rolled
  `ai_registry.py` dispatcher.
- Formal QA environment / staging tier (today: solo dev, direct-to-prod via
  CI gate only — see [RELEASES.md](RELEASES.md)).

## Never

Rejected, with reason. Don't re-propose without a new ADR that addresses
the reason.

- **Fabricated social proof** (fake testimonials, invented user counts,
  made-up press) — violates Product Principle 4 in
  [PRODUCT_OS.md](PRODUCT_OS.md), non-negotiable regardless of growth
  pressure.
- **Sales-assisted onboarding** — violates Product Principle 3
  (fully self-serve). If a future enterprise/B2B channel genuinely needs
  this, it needs its own ADR, not a backlog item.
- **Gemini Live realtime adapter work** — no Gemini API key provisioned;
  OpenAI Realtime is the active `VOICE_PROVIDER`. Not rejected on merit,
  just genuinely blocked on a credential the founder hasn't obtained. Move
  to Next once a key exists.
- **AWS Bedrock provider wiring** — selectable in the AI Model Registry
  schema today but not implemented (`ai_registry.py` falls through to
  `openai_compatible` and fails cleanly). No current purpose needs it; adding
  the SigV4 signing family is real work with no demand behind it yet.
