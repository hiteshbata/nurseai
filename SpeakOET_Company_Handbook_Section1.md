# SpeakOET Company Handbook

## Section 1: Company Overview

### Company Name

**SpeakOET**

*Source: `frontend/src/lib/site.ts` (`SITE_NAME`), `README.md`, `PRODUCT.md`*

### Website

**https://www.speakoet.com**

- Backend API is deployed separately at `api.speakoet.com`.

*Source: `README.md`, `frontend/src/lib/site.ts` (`SITE_URL`)*

### Product Summary

SpeakOET is a web application that helps Indian nurses prepare for the OET (Occupational English Test) — the English-proficiency exam required to register as a nurse in Australia, the UK, or New Zealand. The product's flagship mechanism is a live, real-time voice roleplay with an AI-simulated patient, scored against the official public 9-criteria OET Speaking rubric.

Beyond Speaking, the backend and frontend currently include routers/pages for **Reading**, **Listening**, **Writing**, a **Mock Test**, a **Vocab** module, and a **Hub** (study/skill-tracking area) — see `backend/app/routers/` (`reading.py`, `listening.py`, `writing.py`, `mock.py`, `vocab.py`, `hub.py`) and `frontend/app/` (`practice/`, `mock-test/`, `hub/`). Note: `README.md`'s "Not yet built: Reading and Listening" line and its "Not yet built ... full timed Mock Test" line are contradicted by the presence of these routers/pages and by `PRODUCT.md`, which explicitly flags the README note as **stale as of 2026-07-24**. Per this document's rule to describe the current production implementation, these modules should be treated as built at the code level; their exact production completeness/content coverage is not fully determinable from static repository inspection alone.

*Source: `README.md`, `PRODUCT.md`, `backend/app/routers/`, `frontend/app/`*

### Mission

Not documented. No file in the repository (`README.md`, `PRODUCT.md`, or elsewhere) contains an explicit mission statement.

The closest documented statement of purpose (labeled "Product Purpose" in `PRODUCT.md`):

> "SpeakOET is an AI coach that lets nurses practice every OET sub-test and get real, rubric-based feedback, so they can prepare for and pass OET without a human tutor or classroom course."

*Source: `PRODUCT.md`*

### Vision

Not documented. No forward-looking vision statement exists in the repository.

### Business Model

Subscription (SaaS), billed in Indian Rupees (INR) via **Razorpay**, with four tiers defined in `backend/app/core/plans.py`:

| Plan | Price (INR/month) | Speaking Sessions/mo | Key Access |
|---|---|---|---|
| Free Trial | ₹0 | 3 | Full 9-criteria AI scoring, standard voice, last 3 attempts |
| Basic | ₹299 | 20 | + Reading & Listening, last 10 attempts, email support |
| Pro | ₹799 | 40 | + Writing (with handwriting OCR), premium voice, unlimited history, priority email support |
| Elite | ₹1,499 | 80 | + Full Mock Tests (all 4 parts), pronunciation analysis, AI study plan, WhatsApp priority support |

- Both one-off orders and auto-renewing subscriptions are supported, with webhook-driven, signature-verified, idempotent grant logic (`README.md`).
- Paid periods run 30 days (`PLAN_PERIOD_DAYS`), with a 3-day grace period after expiry before access is revoked (`GRACE_PERIOD_DAYS`), per `backend/app/core/plans.py`.
- Feature gating by plan is centralized in `backend/app/services/plan_gating.py` (e.g., `has_writing_access`, `has_reading_access`, `has_mock_test_access`).

*Source: `backend/app/core/plans.py`, `backend/app/services/plan_gating.py`, `README.md`*

### Current Product Status

- Pre-launch / early stage: `PRODUCT.md` states explicitly, "No real testimonials, user results, or case studies exist yet — pre-launch/early stage."
- The product is live at speakoet.com (`README.md`).
- `README.md`'s feature list is confirmed stale in at least one place (see Product Summary above); this handbook should be revisited each time README/PRODUCT.md are updated.

*Source: `PRODUCT.md`, `README.md`*

### Primary Users

Indian nurses preparing for the OET to register as nurses in Australia, the UK, or New Zealand. Specifically described in `PRODUCT.md` as:

> "ESL speakers, studying around shift work, on a fixed exam timeline, mostly on phone or laptop over Indian mobile/home internet."

*Source: `PRODUCT.md`*

### Problems Being Solved

- OET candidates otherwise rely on human tutors or classroom courses to get realistic speaking practice and rubric-based feedback — SpeakOET aims to replace that dependency with a self-serve AI alternative (`PRODUCT.md`, Product Principles: "Affordable, fully self-serve alternative to human tutors and classroom courses — no sales-assisted onboarding required").
- Lack of realistic, rubric-scored practice: the product's stated principle is that "Practice must feel exam-real (live roleplay, real rubric) so confidence transfers to the actual test" (`PRODUCT.md`).

*Source: `PRODUCT.md`*

### Core Value Proposition

- **Full-syllabus depth over single-skill depth**: per `PRODUCT.md`, positioning is built on covering all four OET sub-tests (Speaking, Writing, Reading, Listening) with real rubric-based scoring, explicitly differentiated from being "just a Speaking-practice app or a static question bank."
- **Live AI patient roleplay** is called out as the flagship mechanism — real-time voice conversation scored on the public 9-criteria OET Speaking rubric (Empathy, Patient's Perspective, Providing Structure, Information Gathering, Information Giving, Intelligibility, Fluency, Appropriateness of Language, Grammar & Expression).
- Ship-honesty is a stated product principle: "never state a module, result, or proof point that isn't real yet" (`PRODUCT.md`).

*Source: `PRODUCT.md`, `README.md`*

### Current Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router, TypeScript), Tailwind CSS, deployed on Vercel |
| Backend | FastAPI (Python, async), deployed separately at `api.speakoet.com` |
| Database / Auth | Supabase (Postgres + Supabase Auth). Backend verifies access tokens locally (HS256 shared secret or JWKS); Supabase RLS is defense-in-depth, with authorization primarily enforced in the FastAPI layer (backend uses the service-role key) |
| AI scoring | Configurable provider — Gemini / OpenRouter / OpenAI (`AI_PROVIDER` in `backend/app/core/config.py`) |
| Realtime voice | OpenAI Realtime or Gemini Live, selected via `VOICE_PROVIDER`; Deepgram/Azure/Google available for non-realtime STT/TTS paths |
| Payments | Razorpay |
| Rate limiting / caching | Redis (sliding-window limiter; falls back to per-process memory if `REDIS_URL` is unset — correct only for single-instance deployments) |
| Observability | Sentry (frontend + backend), PostHog (product analytics) |
| CMS | Sanity (blog) |

*Source: `README.md` ("Tech Stack" section)*

### Repository Overview

The repository (`nurseai`) is a monorepo containing:

- `frontend/` — Next.js application (marketing site, authenticated app, admin panel)
- `backend/` — FastAPI application (API, business logic, AI provider adapters)
- `supabase/`, `supabase-*.sql` — database schema and migration history (applied manually via the Supabase SQL editor, per `README.md`)
- `docs/` — supporting documentation (contents not itemized in this section; see later handbook sections)
- `agent/`, `scripts/`, `studio/` — present at the repository root; purpose not documented in `README.md` or `PRODUCT.md`
- Root-level planning/audit documents: `BUILD_PROMPT.md`, `KILO_BUILD.md`, `KILO_BUILD_PLAN.md`, `NURSEAI_BUILD_PLAN.md`, `AUTH_AUDIT_CHECKLIST.md`, `DEPLOYMENT_CHECKLIST.md`, `DEVOPS_AUDIT_CHECKLIST.md`, `MIGRATIONS.md`, `PERFORMANCE.md`, `SECRET_ROTATION_CHECKLIST.md`, `UI_UX_AUDIT_2026-07-07.md` — these exist but their contents are out of scope for Section 1.
- `docker-compose.yml` — explicitly noted in `README.md` as **out of date**: "it predates the move to Supabase and still wires up a SQLite `DATABASE_URL` — it will not run the current backend as-is."
- **License**: Proprietary — `README.md` states no LICENSE file is currently present in the repository.

> *Screenshot suggestion: insert a top-level directory listing screenshot here for new-employee onboarding orientation.*

*Source: repository root listing, `README.md`*

### Folder Structure Summary

```
nurseai/
├── frontend/
│   ├── app/
│   │   ├── page.tsx, layout.tsx, globals.css
│   │   ├── auth/, dashboard/, practice/, onboarding/, upgrade/, profile/, admin/
│   │   ├── mock-test/, hub/                       # present in repo; not listed in README's tree
│   │   ├── about/, blog/, docs/, learn/, privacy/, terms/, support/  (marketing/content)
│   │   ├── components/            # feature components (oet/, landing/, auth/, learn/, ui/)
│   │   └── hooks/
│   ├── src/lib/                   # api client, supabase client, site config, analytics
│   ├── next.config.js             # security headers, CSP
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, CORS, security headers, router registration
│   │   ├── core/                  # config, Supabase client, rate limiter, Redis, plan definitions
│   │   ├── routers/                # auth, speaking, speaking_realtime, writing, reading, listening,
│   │   │                           # mock, vocab, hub, scoring, progress, payments, admin,
│   │   │                           # onboarding, profile, plans, sessions, submissions, ...
│   │   ├── services/               # AI scoring, coaching, plan gating, realtime provider adapters, TTS/STT
│   │   └── schemas/
│   ├── tests/
│   └── requirements.txt
├── supabase-*.sql                 # schema + migration history (applied manually via Supabase SQL editor)
└── docker-compose.yml             # local dev only — currently out of date, see note above
```

*Source: `README.md` "Project Structure" section, cross-checked and extended against actual `backend/app/routers/` and `frontend/app/` directory listings*

> *Screenshot suggestion: insert an IDE file-tree screenshot of `frontend/app/` and `backend/app/routers/` here for new-employee orientation.*

---

## Missing Information

The following could not be determined from the repository and require input from a human team member:

- **Mission statement** — no explicit company/product mission is documented anywhere in the repo.
- **Vision statement** — no forward-looking vision is documented.
- **Legal entity name, incorporation details, or company registration information** — not present in the repository.
- **Team/founder information** — not documented in any repository file reviewed for this section.
- **Exact current completeness of Reading, Listening, Vocab, and Mock Test modules** — `PRODUCT.md` explicitly flags the scope/ship-date for these as "Open/undecided," and the README's feature list is confirmed stale in at least one place. Code (routers/pages) exists for all of them, but content coverage and production readiness cannot be verified from static files alone.
- **Purpose of `agent/`, `scripts/`, and `studio/` top-level directories** — present in the repo but undocumented in `README.md` or `PRODUCT.md`.
- **Contents of `docs/` directory** — not itemized in this section.
- **Brand voice/tone and formal visual identity guidelines** — `PRODUCT.md` states: "No formally confirmed voice/tone or visual identity beyond the current live site — treat as open rather than inferred."
- **Accessibility/WCAG compliance level** — `PRODUCT.md` states this is "not yet set."
- **Company-wide business metrics** (user counts, revenue, MRR/ARR) — not present in the repository (by design; `PRODUCT.md` warns against fabricating such figures).
- **Root-level `package.json`** — none exists at the repository root; only `frontend/package.json` and `package-lock.json` (root) were found, and the root lockfile's corresponding manifest could not be located.
