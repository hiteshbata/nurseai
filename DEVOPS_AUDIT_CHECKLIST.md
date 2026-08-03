# DevOps Audit Fix Checklist — SpeakOET

**Goal:** All scores → 100 after completion.  
**Generated:** 2026-08-02  
**Current Scores:** DevOps 38 · Deploy 42 · Reliability 45 · CI/CD 25 · Scalability 35 · Cost 72

---

## 🔴 MUST FIX (4 items — unblocks production launch)

| # | Item | Area | What To Do |
|---|------|------|------------|
| 1 | **Rotate & relocate all secrets** | Secrets Management | Rotate every key in `backend/.env` immediately. Remove the `.env` file from the repo working tree. Use Vercel dashboard env vars for frontend, Render dashboard env vars for backend. Keep a single `.env.example` template with placeholder values only. Delete `frontend/.env.local` and regenerate `VERCEL_OIDC_TOKEN` per machine. |
| 2 | **Provision Redis & set REDIS_URL** | Infrastructure | Create a Redis instance (Upstash free tier, Render Redis, or Redis Cloud). Set `REDIS_URL` in Render dashboard. Without this, rate limiting silently degrades to per-process memory on multi-instance deployments. |
| 3 | **Activate cron maintenance jobs** | Operations | Set `CRON_SECRET` env var in Render dashboard (`openssl rand -hex 32`). Create cron-job.org account. Add two jobs: `POST /admin/logs/prune` (weekly Sun 03:00 UTC) and `POST /admin/subscriptions/sweep-expired` (daily 03:00 UTC), both with `X-Cron-Secret` header. Verify both return 200. |
| 4 | **Adopt a database migration tool** | Database | Install Alembic (`pip install alembic`). Run `alembic init migrations/alembic`. Convert all 34 existing SQL files to Alembic revision files with matching `upgrade()` and `downgrade()` functions. Add `alembic upgrade head` to backend startup or Render build command. Add `alembic check` to CI. |

---

## 🟡 SHOULD FIX (8 items — resolve within first month post-launch)

| # | Item | Area | What To Do |
|---|------|------|------------|
| 5 | **Create infrastructure-as-code** | IaC | Create `vercel.json` at repo root with: framework `nextjs`, build/output config, environment variable references (not values), redirects from `next.config.js`, and headers. Create `render.yaml` with: service type `web`, build command, start command, env var references, health check path `/health`, instance type, and scaling rules. |
| 6 | **Add deployment jobs to CI** | CI/CD | Add a `deploy-staging` job to `.github/workflows/ci.yml` that triggers on PR, deploys to a Vercel preview environment, and runs Playwright smoke tests. Add a `deploy-production` job that requires manual approval via GitHub Environments and triggers only on main branch push after all checks pass. |
| 7 | **Create staging environment** | Environments | Provision a separate Supabase project for staging. Set up `staging.speakoet.com` DNS record pointing to a separate Vercel project (or Vercel preview alias). Set up a `staging-api` Render service. Seed staging database with anonymized test data. |
| 8 | **Add security scanning to CI** | CI/CD | Enable GitHub Dependabot for both `npm` (frontend) and `pip` (backend). Add `npm audit --production` step to frontend CI job. Add `pip-audit` step to backend CI job. Enable GitHub CodeQL analysis for JavaScript/TypeScript and Python. |
| 9 | **Add database backup verification** | Disaster Recovery | Confirm Supabase project has PITR (Point-in-Time Recovery) enabled. If not, upgrade plan or set up a `pg_dump` cron to external storage. Write a `docs/backup-restore.md` procedure. Schedule and execute a restore drill monthly — restore to a temporary database, verify data integrity, document the result. |
| 10 | **Create incident response runbook** | Operations | Write `docs/incident-response.md` with: alert trigger list, escalation contacts, playbooks for top 5 incidents (database unreachable, payment webhook 500ing, AI provider down, DNS/SSL expiry, high error rate), customer-facing status page URL, and postmortem template. |
| 11 | **Add Redis & speech provider health checks** | Health | Extend `GET /health` to: ping Redis (`redis_client.ping()`), skip if Redis not configured; check Deepgram, Azure Speech, and Google TTS by calling their cheapest/lightest API endpoints with a timeout. Return individual component statuses in the JSON response. Add `/ready` endpoint that checks ALL dependencies; keep `/health` as liveness (lightweight). |
| 12 | **Add graceful shutdown handler** | Operations | In `backend/app/main.py` lifespan, after `yield`: close all active WebSocket connections (from `speaking_realtime.py`), drain in-flight HTTP connections (wait for `ThreadPoolExecutor` if used), disconnect Redis client, flush PostHog event queue. |

---

## 🟢 NICE TO IMPROVE (12 items — continuous improvement)

| # | Item | Area | What To Do |
|---|------|------|------------|
| 13 | **Add frontend smoke tests** | Testing | Write 5 Playwright tests: (1) landing page loads with CSP applied, (2) login flow redirects to dashboard, (3) /health returns 200, (4) anonymous user sees pricing page, (5) signup flow reaches onboarding. Add `npx playwright test` to CI frontend job. |
| 14 | **Upgrade Node 18 → 20** | Docker | Change `frontend/Dockerfile.dev:1` and `frontend/Dockerfile.prod:1` from `node:18-alpine` to `node:20-alpine`. Update `package.json` engines field. Run full test/build to verify compatibility. Node 20 is active LTS until April 2026. |
| 15 | **Add HEALTHCHECK to Dockerfiles** | Docker | Add to `backend/Dockerfile.prod`: `HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://localhost:8000/health || exit 1`. Add to `frontend/Dockerfile.prod`: `HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://localhost:3000/api/health || exit 1`. |
| 16 | **Add multi-stage Docker builds** | Docker | Split `frontend/Dockerfile.prod` into: Stage 1 (build) — `npm ci`, `COPY . .`, `npm run build`. Stage 2 (run) — `COPY --from=build /app/.next ./.next`, `COPY --from=build /app/node_modules ./node_modules`, `COPY --from=build /app/package.json .`, `COPY --from=build /app/public ./public`. Same `CMD ["npm", "start"]`. Reduces final image size. |
| 17 | **Add CDN for Supabase Storage** | CDN | Set up CloudFront distribution (or Cloudflare) in front of Supabase Storage bucket. Update CSP in `next.config.js` to allow the CDN domain. Update all Supabase Storage URLs in code to use CDN domain. Reduces egress costs and improves global load times for listening audio. |
| 18 | **Add WebSocket connection limits** | Scalability | In `speaking_realtime.py` WebSocket endpoint: add per-user limit (max 1 concurrent session), add global limit (reject with 503 when at capacity), add rate limit on new connections (1 per 5 seconds per user). Log when limits are hit. |
| 19 | **Add AI provider circuit breaker** | Resilience | Wrap all AI provider calls (scoring, realtime, STT, TTS) in a circuit breaker pattern: after N consecutive failures, stop calling that provider for T seconds, return graceful error to user. Fall back to alternate provider if configured. Log and alert on circuit trips. |
| 20 | **Replace `print()` with structured logging** | Observability | Replace all `print()` calls in `backend/app/main.py` and any router with `logging.getLogger(__name__).warning(...)` or `.info(...)`. Add `python-json-logger` to emit JSON-formatted logs. Ship logs to Better Stack / Logtail / Papertrail (any has a free tier). |
| 21 | **Align Docker dev database to PostgreSQL** | Dev/Prod Parity | Replace `DATABASE_URL=sqlite:///./nurseai.db` in `docker-compose.yml` with Supabase local development (`supabase start`). Point backend Docker at Supabase local's PostgreSQL instance. Add `supabase start` to dev setup instructions. Eliminates SQLite vs PostgreSQL drift. |
| 22 | **Enable TypeScript strict mode** | Code Quality | Set `"strict": true` in `frontend/tsconfig.json`. Fix type errors one file at a time. Start with `src/lib/*.ts`, then `app/hooks/*.ts`, then gradually enable for all files. Use `// @ts-expect-error` for known issues with migration plan. |
| 23 | **Add Next.js image optimization for Supabase** | Performance | Add Supabase Storage host to `images.remotePatterns` in `next.config.js`. Replace `<img>` tags for Supabase-hosted content with Next.js `<Image>` components. Gains: automatic resizing, lazy loading, WebP conversion, blur-up placeholders. |
| 24 | **Write operational runbook** | Documentation | Create `docs/runbook.md` with: architecture diagram, service inventory (with URLs/plans/owners), key rotation procedure, DNS management procedure, SSL certificate renewal schedule, common operations (restart backend, scale Render service, create admin user), debugging common issues (payment webhook retry, session stuck, AI provider timeout). |

---

## 🎯 Target Scores After Completion

| Metric | Current | Target | What Drives Improvement |
|--------|---------|--------|-------------------------|
| **CI/CD Maturity** | 25 | 100 | Items #6, #8, #13 — deploy pipeline, security scans, frontend tests |
| **DevOps Score** | 38 | 100 | Items #5, #6, #7 — IaC, deploy pipeline, staging env |
| **Deployment Readiness** | 42 | 100 | Items #3, #4, #5, #6, #7, #10, #12 — crons, migrations, IaC, staging, runbook, shutdown |
| **Infrastructure Reliability** | 45 | 100 | Items #2, #9, #11, #15, #17 — Redis, backups, health checks, Docker healthcheck, CDN |
| **Scalability** | 35 | 100 | Items #2, #18, #19, #23 — Redis, WebSocket limits, circuit breaker, image optimization |
| **Cost Efficiency** | 72 | 100 | Items #17, #24 — CDN for egress savings, runbook for operational efficiency |

---

## Execution Order

```
Phase 1 (This Week — Unblock Launch):
  Item 1 → Item 2 → Item 3 → Item 4

Phase 2 (Week 2-4 Post-Launch):
  Item 5 → Item 6 → Item 7 → Item 8 → Item 9 → Item 10 → Item 11 → Item 12

Phase 3 (Month 2-3):
  Item 13 → Item 14 → Item 15 → Item 16 → Item 17 → Item 18 → Item 19 → Item 20

Phase 4 (Month 3+):
  Item 21 → Item 22 → Item 23 → Item 24
```

---

**Verification:** After completing ALL 24 items, re-run this audit to confirm scores reach 100 across all metrics.
