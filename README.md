# SpeakOET — AI OET Speaking Coach for Indian Nurses

Web app helping Indian nurses preparing for OET (to work in Australia, UK, or New Zealand) practice the Speaking sub-test with a live AI patient roleplay, scored against the official 9-criteria OET rubric.

Live at [speakoet.com](https://www.speakoet.com).

## Features

- **AI patient roleplay**: real-time voice conversation with an AI patient (OpenAI Realtime or Gemini Live, selectable per deployment) across 100+ clinically-written scenarios spanning beginner/intermediate/advanced difficulty
- **9-criteria OET scoring**: Empathy, Patient's Perspective, Providing Structure, Information Gathering, Information Giving, Intelligibility, Fluency, Appropriateness of Language, Grammar & Expression — scored against the public OET rubric
- **Writing practice** (Pro plan): submit written responses for AI evaluation
- **Progress dashboard**: band-score trend, per-criterion skill breakdown, practice streaks, milestone badges, recent-session history
- **AI coach summary**: personalized weekly strengths/focus-area writeup generated from a user's own score history
- **Subscription billing**: Free / Basic / Pro / Elite tiers via Razorpay (one-off orders and auto-renewing subscriptions), webhook-driven with signature verification and idempotent grant logic
- **Admin panel**: scenario management, user roles, logs, app-wide stats

**Not yet built:** Reading and Listening modules, full timed Mock Test (placeholder page live — speaking scenarios currently substitute for it).

## Tech Stack

- **Frontend**: Next.js 14 (App Router, TypeScript), Tailwind CSS, deployed on Vercel
- **Backend**: FastAPI (Python, async), deployed separately (`api.speakoet.com`)
- **Database/Auth**: Supabase (Postgres + Supabase Auth). Backend verifies access tokens locally (HS256 shared secret or JWKS, depending on project config) instead of round-tripping to Supabase Auth per request; RLS is defense-in-depth, actual authorization is enforced in the FastAPI layer since the backend uses the service-role key
- **AI scoring**: configurable provider (Gemini / OpenRouter / OpenAI) — see `AI_PROVIDER` in `backend/app/core/config.py`
- **Realtime voice**: OpenAI Realtime or Gemini Live, selected via `VOICE_PROVIDER`; Deepgram/Azure/Google available for non-realtime STT/TTS paths
- **Payments**: Razorpay
- **Rate limiting / caching**: Redis (sliding-window limiter; falls back to per-process memory if `REDIS_URL` unset — only correct for single-instance deployments)
- **Observability**: Sentry (frontend + backend), PostHog (product analytics)
- **CMS**: Sanity (blog)

## Project Structure

```
nurseai/
├── frontend/
│   ├── app/
│   │   ├── page.tsx, layout.tsx, globals.css
│   │   ├── auth/, dashboard/, practice/, onboarding/, upgrade/, profile/, admin/
│   │   ├── about/, blog/, docs/, learn/, privacy/, terms/, support/  (marketing/content, indexable)
│   │   ├── components/            # feature components (oet/, landing/, auth/, learn/, ui/)
│   │   └── hooks/
│   ├── src/lib/                   # api client, supabase client, site config, analytics
│   ├── next.config.js             # security headers, CSP
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, CORS, security headers, router registration
│   │   ├── core/                  # config, Supabase client, rate limiter, Redis, plan definitions
│   │   ├── routers/                # auth, speaking, speaking_realtime, writing, scoring, progress,
│   │   │                           # payments, admin, onboarding, profile, plans, sessions, submissions, ...
│   │   ├── services/               # AI scoring, coaching, realtime provider adapters, TTS/STT
│   │   └── schemas/
│   ├── tests/
│   └── requirements.txt
├── supabase-*.sql                 # schema + migration history (applied manually via Supabase SQL editor)
└── docker-compose.yml             # local dev only — see note below
```

## Local Development

### Prerequisites

- Node.js 18+, Python 3.10+
- A Supabase project (Postgres + Auth) — run the `supabase-*.sql` migrations against it in the order they were added
- API keys for whichever providers you're testing: at least one of Gemini/OpenRouter/OpenAI for scoring, Razorpay test keys for payments

### Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local   # fill in NEXT_PUBLIC_* vars
npm run dev
# http://localhost:3000
```

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env   # fill in SUPABASE_*, AI provider key(s), RAZORPAY_* etc.
uvicorn app.main:app --reload
# http://localhost:8000
```

`GET /docs` (Swagger UI) is only enabled when `SENTRY_ENVIRONMENT != "production"` — it's disabled on the live deployment by design.

> **Note on `docker-compose.yml`**: it predates the move to Supabase and still wires up a SQLite `DATABASE_URL` — it will not run the current backend as-is. Use the local dev commands above until it's updated.

See `.env.example` for the full list of environment variables (Supabase, AI providers, Razorpay, Redis, Sentry, PostHog, Sanity).

## API Overview

Backend routers (see `backend/app/routers/`): `auth`, `speaking`, `speaking_realtime` (websocket), `writing`, `scoring`, `progress`, `onboarding`, `profile`, `plans`, `sessions`, `submissions`, `payments` (incl. Razorpay webhook), `admin` (scenario/user/log management, cron-triggered maintenance endpoints), `grammar`, `comparison`, `scenario_generator`, `questions`.

Auth: Supabase-issued JWT as `Authorization: Bearer <token>`. Admin routes additionally require an `admin` role row in `user_roles`. Cron-only endpoints (`/admin/logs/prune`, `/admin/subscriptions/sweep-expired`) accept either an admin JWT or a shared `X-Cron-Secret` header for external schedulers.

## License

Proprietary — no LICENSE file is currently present in this repository.
