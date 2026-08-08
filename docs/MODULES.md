# Modules

Every product module, its purpose, current status, dependencies, and
approved future improvements. Status here must match reality — update this
file in the same PR that changes a module's state (see Definition of Done
in [PRODUCT_OS.md](PRODUCT_OS.md)).

---

## Speaking

**Purpose**: The flagship mechanism — live, real-time voice roleplay with
an AI patient, scored against the public 9-criteria OET Speaking rubric
(Empathy, Patient's Perspective, Providing Structure, Information
Gathering, Information Giving, Intelligibility, Fluency, Appropriateness of
Language, Grammar & Expression).

**Current status**: Live, feature-complete. 100+ clinically-written
scenarios across beginner/intermediate/advanced. Realtime voice via OpenAI
Realtime (`speaking_realtime.py`, `useRealtimeSpeakingSession.ts`); a
non-realtime path also exists (`useSpeakingSession.ts`). Already
code-split (M9, resolved 2026-08-07): `page.tsx` at 518 lines with
`SpeakingSession.tsx` lazy-loaded. **Adaptive Speaking V1** (Sprint 1,
ADR-008, 2026-08-08): every scored session's results page now shows
rule-based "Today's Speaking Insights" — strongest/weakest skill (weakest
prefers rolled-up `user_skill_stats` history via `get_weakness`, falling
back to this session's own scores for a new learner), a recommendation
reason, one actionable improvement, a confidence message, and a
recommended next scenario. Runs entirely on `user_skill_stats` as already
deployed — no new table, no migration. Code complete, pending
live-verification.

**Dependencies**: AI Model Registry (`patient_roleplay`,
`realtime_voice_openai_standard`/`_mini`, `speaking_scoring_free`/
`_premium` purposes), `scenario_generator.py` / `seed_scenarios.py` for
content, `pronunciation.py`, `skill_graph.py` (Learner Brain read/write),
`observation_service.py` (score validation), `coaching_messages.py`
(insight copy templates).

**Future improvements**: Gemini Live realtime adapter — blocked on no
Gemini API key provisioned, not a code gap (see
[BACKLOG.md](BACKLOG.md) → Never). Cross-module weakness routing (route a
detected weakness to Reading/Listening/Writing, not just another Speaking
scenario) once the full Learner Brain (Phase 3) lands.

---

## Reading

**Purpose**: OET Reading Part A/B/C practice — timed passages, MCQ and
short-answer questions, matching the real OET Reading format (see
[reference: OET Reading official format]).

**Current status**: Live, feature-complete (2026-07-24 onward). Content
pipeline uses `mistral-ocr` (via OpenRouter, `reading_ocr` purpose) for
PDF extraction; `reading_explanation` and `reading_content_rewrite`
purposes for AI-assisted content. Known gap: `logging.basicConfig()` is
never called in the extraction pipeline, so debug logs from that path are
silently invisible — not yet fixed.

**Dependencies**: AI Model Registry (`reading_ocr`,
`reading_explanation`, `reading_content_rewrite`, `explanation_mcq`
purposes), `reading_skills.py`, `oet_questions.py`.

**Future improvements**: Fix the invisible debug-logging gap. Content
volume growth once Content Brain (Phase 4) exists.

---

## Listening

**Purpose**: OET Listening practice — audio playback with transcript-based
scoring.

**Current status**: Live, feature-complete (shipped 2026-07-25), audio
playback live-confirmed. Content volume (tests/audio/answers) is the
current gap, not the feature itself. AI content-generation calls in this
pipeline still want a spot-check for quality.

**Dependencies**: AI Model Registry (`listening_ocr`,
`listening_audio_segmentation` purposes), `listening_audio.py`.

**Future improvements**: Add more content (tracked as an ongoing content
task, not an engineering task — see
[CONTENT_STRATEGY.md](CONTENT_STRATEGY.md)). Spot-check existing
AI-generated content for quality.

---

## Writing

**Purpose**: OET Writing practice — AI-evaluated written responses against
the official rubric (Pro plan feature).

**Current status**: Live, feature-complete (2026-07-25): official rubric
scoring, Claude-based OCR for handwritten/typed response capture, response
reorder and append fixes. Only remaining gap is content volume (more
writing scenarios), not functionality.

**Dependencies**: AI Model Registry (`writing_scoring`, `writing_ocr`,
`writing_content_extraction` purposes — `writing_ocr` is the one purpose
routed to Claude via OpenRouter rather than Gemini).

**Future improvements**: Add more writing scenarios/content.

---

## Mock Test

**Purpose**: Full timed OET Mock Test — all four sub-tests (Listening,
Reading, Writing, Speaking) in one session, producing an unlocked 4-band
report matching the real exam structure.

**Current status**: Complete (2026-07-25/26). All four sub-tests
live-verified end-to-end; unlocked band report confirmed working.

**Dependencies**: All four individual modules above, plus `mock.py` for
session orchestration and `mock_test_packs` (migration
`20260726000400_mock_test_packs.sql`) for packaged test sets.

**Future improvements**: None currently scoped — this module is
considered done pending new content packs (a content task, not an
engineering one).

---

## Admin

**Purpose**: Internal operations panel — RBAC, audit logging, AI cost/
margin visibility, AI Model Registry management, reminders, and lead
tracking.

**Current status**: Live. Covers RBAC, audit log (also backs AI Model
Registry rollback per ADR-003/007), AI cost tracking dashboard, AI Model
Registry UI (`/admin/ai-models`), reminders, lead tracking, and user
impersonation (hardened 2026-08-02 — no refresh token in client
`sessionStorage`).

**Dependencies**: `admin.py`, `admin_ai_models.py`, `audit_log` table,
`founder_metrics.py`, `alerts.py`.

**Future improvements**: Click-through UI test of `/admin/ai-models` with
real test credentials (deferred, see [BACKLOG.md](BACKLOG.md) → Next).

---

## Website

**Purpose**: Public-facing marketing site — landing pages, blog, pricing,
about/support/legal pages, SEO surface.

**Current status**: Live. Blog on Sanity CMS (wired 2026-07-12). SEO
fundamentals fixed 2026-07-12 (sitemap/robots domain bug, OpenGraph,
favicon), verified via Vercel preview. A separate 12-doc SEO master plan
(`docs/seo/`) exists; blog-sitemap interaction has a known latent bug not
yet triggered in practice.

**Dependencies**: Sanity CMS (env vars + domain alias needed for the blog
to be fully live per [Blog CMS memory] — verify current state before
assuming this is fully resolved), Next.js `sitemap.ts`/`robots.ts`.

**Future improvements**: Multi-channel growth per the SEO master plan —
SEO alone is not expected to reach the subscriber target.

---

## Authentication

**Purpose**: User identity, session management, and access control.

**Current status**: Live, hardened. Supabase Auth (GoTrue) is the actual
identity provider the frontend talks to directly — the backend's own
`/auth/register` and `/auth/login` endpoints are dead code, not in use.
Backend verifies JWTs locally (HS256 + JWKS, ADR-006, live-verified
2026-07-11). Logout revokes refresh tokens server-side (scope=global,
live-verified 2026-08-02). Auth error responses are generic (no `str(e)`
leaks) with server-side logging.

**Dependencies**: Supabase Auth, `get_current_user` (backend), RLS
policies (defense-in-depth per ADR-002).

**Future improvements**: None currently scoped. Consider removing the
dead `/auth/register`/`/auth/login` backend endpoints if confirmed truly
unused (ponytail: verify zero callers before deleting).

---

## Payments

**Purpose**: Subscription billing — Free/Basic/Pro/Elite tiers, one-off and
auto-renewing, via Razorpay.

**Current status**: Live, confirmed working by the founder 2026-07-13
(subscription checkout was a launch blocker, now resolved). Atomic
cost-tracking RPCs (item 30, live-applied 2026-08-02) prevent race
conditions on usage/session increment.

**Dependencies**: Razorpay, `payments.py`, `plans.py`,
`plan_gating.py`, `cost_tracking.py`.

**Future improvements**: None currently scoped.

---

## Analytics

**Purpose**: Product usage visibility and AI cost observability.

**Current status**: Live. PostHog is the primary daily analytics tool.
Sentry live on both frontend and backend (backend Sentry wired as part of
H7/CI work). GA and Search Console live. Microsoft Clarity is provisioned
but kept intentionally dormant (avoid dashboard sprawl — see
[feedback: prefer fewer dashboards]). `ai_usage_events` table tracks
per-call AI cost (purpose, latency, success/failure) as of the AI Model
Registry work.

**Dependencies**: PostHog, Sentry, `ai_cost_metrics.py`.

**Future improvements**: AI cost/margin dashboard beyond current admin
panel views — deliberately deferred (see [BACKLOG.md](BACKLOG.md) →
Later).
