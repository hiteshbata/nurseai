# Quality Platform

Planning document for SpeakOET's quality, testing, monitoring, and release
practice going forward. This is a proposal, not a locked decision set — items
here become real when pulled into [SPRINTS.md](SPRINTS.md), same as any other
work. No code, schema, or CI changed to produce this document.

Written at the close of RC1 (Adaptive Learning V1 — Speaking, Reading,
Listening, Writing), 2026-08-08. See [ROADMAP.md](ROADMAP.md) Phase 2 and
[RELEASES.md](RELEASES.md) for where this sits in the wider plan.

---

## 1. Current Quality Audit

### Testing

- **Backend**: 36 pytest files in `backend/tests/`. Coverage skews toward
  the areas that have burned the project before — auth/RBAC, rate limiting,
  cost tracking, subscription/billing, realtime adapters, the four
  Adaptive Learning insights modules (`test_speaking_insights.py`,
  `test_reading_insights.py`, `test_writing_insights.py`, and
  `test_observation_service.py`; listening insights has no dedicated file
  yet — gap noted below). No coverage tool wired in (no `pytest-cov` in
  CI) — test count is a proxy for coverage, not a measurement of it.
- **Frontend**: no unit/component test runner in the repo (no Jest/Vitest
  config). All frontend verification is `tsc --noEmit` + `next build` (CI)
  plus manual click-through.
- **E2E**: Playwright, 5 specs (`landing-csp`, `health`, `pricing-anon`,
  `login`, `signup`). Explicitly scoped as "RC1 smoke tests only... not a
  comprehensive E2E suite" (see `playwright.config.ts` header comment).
  Runs against an already-live target (local/RC1/prod), not a suite that
  exercises a scored session end-to-end.

**Strength**: test files exist exactly where the project has been hurt
before (billing, auth, rate limits) — the suite tracks real incident
history, not a generic template.

**Gap**: nothing exercises a full scored session (Speaking roleplay →
score → insights card) end-to-end, in either pytest or Playwright. Every
module's scoring path is unit-tested in isolation; the seam between AI
scoring, `skill_graph`, and the results-page render is only ever
verified by hand.

### Monitoring

- **Sentry**: wired frontend (`sentry-client.ts`) and backend
  (`main.py`), one shared project, environment split via
  `SENTRY_ENVIRONMENT` / `NEXT_PUBLIC_SENTRY_ENVIRONMENT`
  (`development` / `rc1` / `production`). Frontend suppresses events in
  `development` via `beforeSend`; backend skips `sentry_sdk.init` entirely
  in `development`. Frontend adds session replay (10% sampled, 100% on
  error) and 20% trace sampling — no equivalent backend trace sampling.
- **PostHog**: one project, same environment tag pattern
  (`environment` property registered globally), routed through a reverse
  proxy (`data.speakoet.com`) to dodge ad blockers. `capture_pageview`
  auto-on; manual events added ad hoc per feature (RC1 added
  `login_completed` and reading/listening `score_viewed`).

**Strength**: environment tagging is consistent and deliberate across
both tools — dev noise is suppressed, RC1 and production are
distinguishable in the same project rather than needing separate DSNs/
keys.

**Gap**: no documented alert policy (Sentry issue thresholds, PostHog
funnel/drop-off alerts). No dashboard maps events to the North Star
Metric (Weekly Active Practicers who complete a scored session) —
PostHog has the raw events, nothing aggregates them into that number
today.

### Documentation

`docs/` is a real, cross-linked operating system (Product OS pattern):
[ROADMAP.md](ROADMAP.md), [SPRINTS.md](SPRINTS.md),
[BACKLOG.md](BACKLOG.md), [DECISIONS.md](DECISIONS.md) (ADRs),
[ARCHITECTURE.md](ARCHITECTURE.md), [MODULES.md](MODULES.md),
[AI_SYSTEM.md](AI_SYSTEM.md), [DATABASE.md](DATABASE.md),
[RELEASES.md](RELEASES.md), [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md).
Definition of Done in [PRODUCT_OS.md](PRODUCT_OS.md) explicitly requires
doc updates in the same PR as the change they describe.

**Strength**: this is unusually disciplined for a solo/small-team project
— ADRs exist for real decisions (e.g. ADR-004, ADR-008), ROADMAP/BACKLOG/
SPRINTS separation prevents an ever-growing single TODO file.

**Gap (drift, found during this audit)**: [SPRINTS.md](SPRINTS.md) itself
says its board "was not kept current for Sprints 2-4" —
[IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) is the real record. And
[RELEASES.md](RELEASES.md) → Release Candidates still shows RC1 with open
checkboxes (live-verification, merge to `main` for Reading/Listening/
Writing, founder approval) as of the last edit — if RC1 has in fact closed
since, that section needs an update pass before it's trusted as current
state. This is exactly the kind of drift the Product OS's own Definition
of Done exists to prevent — flagging it, not fixing it here (out of scope
for this documentation-only sprint).

### Release process

Covered in depth in [RELEASES.md](RELEASES.md) already — see Section 5
below for the forward-looking version. Current state: `feature/*` →
`develop` → `main`, CI-gated, no staging environment, no formal QA
function, live-verification substitutes for a QA environment.

---

## 2. Testing Strategy

| Layer | What belongs here | Owner today |
|---|---|---|
| **Unit** | Pure functions with clear inputs/outputs: `validate_and_normalize`, `normalize_writing_score`, rubric math, `skill_graph` EMA update, coaching-message selection. Fast, no network, no DB. | pytest |
| **Integration** | A router endpoint against a real (or realistically mocked) Supabase call: does `/speaking/score` actually write `user_skill_stats` and return the right `insights` shape. Current backend tests mostly live here already (e.g. `test_speaking_insights.py`). | pytest |
| **End-to-end** | A browser driving the real app against a real deployment target: login → start a module → finish a scored session → see the insights card. This is the layer that's thin today (5 smoke specs, no scored-session path). | Playwright |
| **Manual founder verification** | Anything touching auth, payments, or AI scoring, per the existing Definition of Done in [PRODUCT_OS.md](PRODUCT_OS.md) — a human click-through against the real deployed environment before calling a change done. Stays required even as Playwright grows; some judgment calls (does this feel right, is the AI response actually good) aren't assertable. | Founder |
| **Regression** | Re-running the existing suite (pytest + Playwright) on every PR via CI — already happens for pytest; Playwright is not yet in CI (see Section 3). | CI |
| **Performance** | Not tested today. Belongs at two levels: AI response latency (scoring/roleplay round-trip time — a real product-quality concern, not just infra) and page load (Core Web Vitals on the landing/practice pages, since SEO work already depends on this). No tooling wired in yet. | Unowned — see Technical Debt |
| **Security** | Partially covered by dedicated backend tests (RBAC, auth, rate limiting) plus the existing `.github/workflows/pentest.yml`. No dependency-vulnerability scanning (`npm audit`/`pip-audit`) wired into CI yet. | pytest + `pentest.yml`, gap in dependency scanning |
| **Accessibility** | Not tested today beyond ad hoc founder review (the 2026-07-31 frontend audit flagged specific a11y items, e.g. reduced-motion on score-reveal animations, still untriaged in [BACKLOG.md](BACKLOG.md)). Belongs as targeted Playwright checks (axe-core or equivalent) on the highest-traffic pages first — landing, signup, practice results — not a blanket sweep. | Unowned — see Technical Debt |

Do not add a testing layer that doesn't have a real gap it closes — e.g.
no visual-regression suite is proposed here; nothing in this project's
history suggests unintended visual drift has been a real cost yet.

---

## 3. Playwright Roadmap

Current suite (5 specs) stays as-is — it's correctly scoped as an RC1
smoke suite, not the target state. Proposed expansion groups, in priority
order. **Not implemented as part of this document** — each group becomes
its own backlog item / sprint when pulled in.

| Priority | Group | Why this order |
|---|---|---|
| P0 | **Authentication** | Everything else depends on being logged in; login/signup specs already exist, next is session expiry + logout-revocation (already fixed in code per `project_logout_revocation_fixed` — no test locks it in). |
| P0 | **Billing** | Real money; Razorpay checkout confirmed working manually (2026-07-13) but has zero automated coverage. Highest cost-of-regression in the product. |
| P1 | **Speaking** | The flagship mechanism (live AI roleplay). Hardest to automate (audio/realtime) — start with the non-realtime edges: scenario selection, score display, insights card render — not the live voice loop itself. |
| P1 | **Reading / Listening / Writing** | Same insights-card pattern as Speaking, three times over — once one module's results-page flow is scripted, the other three are near-identical adaptations, not new design work. |
| P2 | **Dashboard** | Progress/band-trend display — lower risk (read-only, no scoring logic), but is the page a returning learner sees most often. |
| P2 | **Admin** | Lower traffic, but the AI Model Registry click-through test is already an explicitly named gap in [SPRINTS.md](SPRINTS.md)/[BACKLOG.md](BACKLOG.md) → Next. Covers that gap. |
| P3 | **SEO / Landing pages** | Lowest functional risk (mostly static content) but cheapest to script (no auth, no state) — good filler work between higher-priority groups, not a reason to delay them. |

Sequencing note: Billing and Authentication are P0 together because a
regression in either directly costs revenue or locks out every other
flow — everything below them is ordered by "flagship mechanism first,
static content last."

---

## 4. Monitoring Strategy

```
Development                    RC                          Production
------------                    --                          ----------
SENTRY_ENVIRONMENT=development  SENTRY_ENVIRONMENT=rc1      SENTRY_ENVIRONMENT=production
Sentry: suppressed              Sentry: reporting            Sentry: reporting, alerting
  (beforeSend returns null;      (same project, rc1 tag)      (same project, prod tag)
   backend skips init)
PostHog: usually unset          PostHog: reporting            PostHog: reporting
  (no key in local .env)         (environment=rc1)             (environment=production)
```

**Environment strategy**: one Sentry project, one PostHog project, told
apart by an `environment` tag/property rather than per-environment
keys/DSNs. This is already the implemented pattern (RC1 monitoring
work) — the proposal here is to keep it, not add per-environment
infrastructure. Splitting into separate projects only becomes justified
if RC-environment noise starts drowning out production signal in
practice, not preemptively.

**Alert strategy (proposed, not yet built)**:
- Sentry: alert on any new *unhandled* error type in `production`
  environment (not `rc1` or `development`) — a founder-facing
  notification (email is sufficient at this scale; no on-call rotation
  exists or is needed for a solo/small team).
- Sentry: alert if error *rate* on a paid-flow endpoint
  (`/speaking/score`, `/payments/*`) crosses a threshold, not just on
  first occurrence — catches degradation, not just novelty.
- PostHog: no automated alerting proposed yet. Funnel/drop-off alerting
  is real value but is Phase 5/Post-PMF-scale tooling — building it now
  is ahead of the traffic volume that would make it statistically
  meaningful.

**Event strategy**: PostHog events should map to the North Star Metric
(Weekly Active Practicers who complete a scored session) — every
module's "session scored" event already fires (`score_viewed` per
module, per RC1). The gap is a saved PostHog insight/dashboard that rolls
these four events up into the one North Star number, rather than
leaving that computation as an ad hoc query each time someone asks "how
are we doing." Building that dashboard is a five-minute PostHog task
when someone sits down to do it — not a code change, not this sprint.

**Release verification**: Sentry `environment=rc1` is the intended
signal for "did this release introduce new errors before it reaches
production" — this only works if something is actually deployed to an
`rc1`-tagged target and watched before merging to `main`. Confirm this
loop is real (a deployed RC1 environment exists and gets watched) as
part of closing out the current RC1 more than as new tooling.

---

## 5. Release Process

```
Development → Feature Complete → QA → Playwright → Founder Verification → RC → Production → Hotfix
```

| Stage | Responsibility | Exit criteria |
|---|---|---|
| **Development** | Engineer (Claude + founder review) works on a `feature/*` branch off `develop`. | Code compiles, `ruff check --select F` clean, no obviously incomplete paths. |
| **Feature Complete** | Engineer. | Milestones in the relevant [SPRINTS.md](SPRINTS.md) entry checked off; docs updated in the same PR if an ADR/module/schema/roadmap change is involved (Definition of Done, [PRODUCT_OS.md](PRODUCT_OS.md)). |
| **QA** | CI, automatically. | `pytest` + `ruff` (backend), `tsc --noEmit` + `lint` + `build` (frontend) all green on the merge commit into `develop`. |
| **Playwright** | CI (once wired in — see Technical Debt) or manual (today). | Relevant smoke/regression specs pass against a running target. Today this step is manual/local (`npm run test:e2e`), not CI-gated. |
| **Founder Verification** | Founder. | Click-through of the actual feature against a real deployed environment (RC1 target or, absent one, local) — required for anything touching auth, payments, or AI scoring per existing Definition of Done. |
| **RC** | Founder + engineer, jointly. | An RC bundles related sprints (see [RELEASES.md](RELEASES.md) → Release Candidates pattern from RC1) and stays open until every bundled item is live-verified and merged `develop` → `main`. |
| **Production** | Vercel/Render, automatically on merge to `main`. | No manual promotion gate exists today by design (solo-team tradeoff) — the merge *is* the release. Monitoring (Sentry `production` tag) is the safety net, not a pre-merge gate. |
| **Hotfix** | Founder + engineer. | Branches directly off `main` (not `develop`) for anything production-broken and urgent; merges back to both `main` and `develop` so `develop` doesn't silently regress the fix on its next release. Not yet formally documented as a path — proposed here, since none has been needed yet. |

This mirrors what [RELEASES.md](RELEASES.md) already documents for
`feature/*` → `develop` → `main` and QA — the addition here is naming
the Hotfix path explicitly (currently undocumented because unneeded so
far) and calling out that "Playwright" and "Founder Verification" are
currently manual steps a future CI integration would formalize, not new
stages being invented.

---

## 6. Technical Debt Review

### Critical

*(None found.)* No open P0 security finding, no unbounded cost exposure,
no data-loss risk identified in this review — consistent with
[ROADMAP.md](ROADMAP.md) Phase 2 exit criteria already being close to met.

### High

- **Shared Adaptive Insights extraction.** `_build_speaking_insights`,
  and the equivalent logic in `writing.py`, `reading.py`, and
  `listening.py`, are four independent implementations of the same
  strongest/weakest/reason/improvement/confidence/next-action shape (see
  `docs/SPRINTS.md` Sprint 2/3's own "extraction deferred until Speaking,
  Reading, Listening and Writing each have one" note — that condition is
  now met). Four copies means a bug fix or copy change happens four
  times. Extract into one shared helper once RC1 is fully live-verified
  and stable — not before, to avoid refactoring code that's mid
  verification.
- **`run_sync` inconsistency.** Per [PRODUCT_OS.md](PRODUCT_OS.md)'s own
  Sprint 4 note: `_recommend_writing_scenarios` (and Speaking) wrap their
  blocking call in `run_sync`; Reading/Listening's equivalents call it
  unwrapped. If the unwrapped versions are blocking the event loop under
  real concurrent load, that's a real latency bug, not a style nit —
  worth confirming with a quick load check before deciding whether it's
  worth fixing.
- **Playwright not in CI.** The 5 RC1 smoke specs exist and pass locally
  but nothing runs them on push/PR. Highest-leverage, lowest-effort item
  on this list once the team is ready to also run a browser in CI (Note:
  the user's standing instruction for this sprint is "do not implement
  CI" — logged here as a finding, not being actioned in this pass.)

### Medium

- **`validate_and_normalize` adoption is inconsistent in shape, not
  coverage.** All four modules call it, but Writing pre-processes through
  a local `normalize_writing_score` first (deliberate, per CTO
  instruction, since Writing's raw ranges aren't uniform 0-6). Not a bug —
  but worth a one-line ADR note (or an addendum to ADR-004) recording
  *why* Writing's call site looks different, so a future reader doesn't
  "fix" it into uniformity and break the rescaling.
- **No coverage measurement in CI.** 36 backend test files is a good
  sign but not a number — `pytest-cov` (already implicitly available via
  `pip install pytest`'s ecosystem, no new heavy dependency) would turn
  "looks well-tested" into a real, trackable percentage.
- **No dependency vulnerability scanning.** Neither `npm audit` nor
  `pip-audit`/`safety` runs in CI. Cheap to add, currently invisible risk.
- **Listening has no dedicated insights test file** (`test_speaking_insights.py` /
  `test_reading_insights.py` / `test_writing_insights.py` exist;
  listening's equivalent logic is presumably covered indirectly via
  `test_listening_audio.py` or not at all — worth a direct look before
  RC1's live-verification gate closes).

### Low

- **Documentation drift** — [SPRINTS.md](SPRINTS.md) admits its own
  board is stale for Sprints 2-4; [RELEASES.md](RELEASES.md)'s RC1
  checklist may be stale if RC1 has since closed (see Section 1). Low
  severity because [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) is the
  designated source of truth for exactly this reason — but worth a
  cleanup pass so a future reader doesn't have to know that caveat.
  Listening's "Part A/B/C" copy has a standing `TODO` for friendlier
  labels (Sprint 3 note) — cosmetic, no functional impact.
- **Ruff scoped to `F` only.** Deliberate (documented in `ci.yml`
  comments) — the fuller ruleset is a separate, larger cleanup, correctly
  not bundled into standing CI up. No action implied here beyond noting
  it's a known, intentional gap rather than an oversight.

---

## 7. Engineering Standards

Codifying practice that's already mostly followed, per
[PRODUCT_OS.md](PRODUCT_OS.md)'s existing Definition of Done and
Development Rules — this section doesn't introduce new obligations, it
names the ones already implicit so future work can be checked against
them explicitly.

- **Sprint completion**: a sprint is done when every milestone in its
  [SPRINTS.md](SPRINTS.md) entry is checked, status is set to Complete,
  and [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) has a matching
  entry. A sprint is not done because code merged — see RC1 itself, where
  "code-complete" and "done" were correctly kept distinct until
  live-verification.
- **QA gates**: CI green (pytest + ruff backend, typecheck + lint +
  build frontend) is necessary, not sufficient. Anything touching auth,
  payments, or AI scoring additionally needs founder live-verification
  before being called done.
- **Documentation**: any change touching an ADR, module status, schema,
  or roadmap phase updates the relevant doc in the *same PR*, not a
  follow-up. A decision not recorded in [DECISIONS.md](DECISIONS.md)
  is not a locked decision, per existing Frozen Decisions rule.
- **Git workflow**: `feature/*` → `develop` → `main`, per
  [RELEASES.md](RELEASES.md). No direct-to-`main` merges except the
  Hotfix path proposed in Section 5.
- **Release notes**: every merge to `main` gets an entry in
  [RELEASES.md](RELEASES.md) → Recent releases — already the practice,
  keep it.
- **Playwright requirements**: any new user-facing flow that reaches
  Feature Complete gets at least one smoke spec before its RC closes —
  matches how RC1 added its 5 specs alongside the four Adaptive Learning
  modules, rather than as an afterthought.
- **Founder approval**: required before an RC's Production stage,
  per Section 5 — not a formality, since founder click-through is the
  project's actual QA environment substitute today.

---

## Documentation created/updated

1. **Created**: `docs/QUALITY_PLATFORM.md` (this document).
2. **Not updated**: `docs/PRODUCT_OS.md` — reviewed, no change needed.
   It already links the full doc set and its Definition of Done already
   covers CI/live-verification/docs-in-same-PR; this document
   references it rather than duplicating or amending it. Add a one-line
   link to `QUALITY_PLATFORM.md` in its document-set list at the top when
   this proposal is formally adopted, not before.

## Quality Platform roadmap

Testing Strategy (Section 2) and Playwright Roadmap (Section 3) define
the target state; Monitoring Strategy (Section 4) and Release Process
(Section 5) are near-current-state with named gaps (CI-gated Playwright,
alert policy, Hotfix path). None of this is scheduled — it becomes real
when a specific item is pulled into an active sprint.

## Technical debt priorities

High: shared Adaptive Insights extraction, `run_sync` consistency,
Playwright-in-CI (blocked on user instruction this sprint). Medium:
`validate_and_normalize`/`normalize_writing_score` ADR note, coverage
measurement, dependency scanning, Listening insights test gap. Low:
SPRINTS.md/RELEASES.md drift cleanup, Listening part-label TODO. No
Critical items found.

## Recommended next engineering milestone

Close RC1 for real: confirm which of the open checkboxes in
[RELEASES.md](RELEASES.md) → Release Candidates are actually still open
(the doc may itself be stale, per Section 1's drift finding), finish
live-verification and the `develop` → `main` merges, then take the
Shared Adaptive Insights extraction (Section 6, High) as the first
Quality Platform-driven cleanup — it only becomes safe to do once all
four modules are done shifting under RC1 verification.
