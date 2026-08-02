# Core Web Vitals baseline

Lab data from Lighthouse 13.4.1, desktop preset, headless Chrome, run 2026-08-02
against production (`www.speakoet.com`). No field data (CrUX/Sentry Performance)
yet -- see gaps below.

| Page | LCP | CLS | TBT | Perf | A11y | Best Practices | SEO |
|---|---|---|---|---|---|---|---|
| Landing (`/`) | 1.1s | 0.001 | 130ms | 87 | 96 | 73 | 100 |
| Blog (`/blog`) | 686ms | 0.001 | 0ms | 98 | 96 | 73 | 100 |
| Dashboard | not measured -- requires auth | | | | | | |
| Speaking practice | not measured -- requires auth | | | | | | |

All measured LCP/CLS numbers are comfortably inside Google's "good" thresholds
(LCP < 2.5s, CLS < 0.1). No INP measurement here -- Lighthouse is lab-only and
doesn't produce INP; that number can only come from field data (see below).

## Best Practices score (73) root cause -- fixed

Both pages were losing points to blocked network requests, not a real
performance problem:

- PostHog's loader fetches config/assets from `us-assets.i.posthog.com`, but
  CSP `connect-src`/`script-src` only allowlisted the API host
  `us.i.posthog.com` -- every page load was silently dropping PostHog config
  requests, which could mean incomplete analytics.
- Cloudflare's own RUM beacon (`static.cloudflareinsights.com`) was blocked by
  `script-src` for the same reason.

Fixed in `frontend/next.config.js` (added both hosts to the CSP). Re-run
Lighthouse after the next deploy to confirm best-practices climbs.

## Gaps (not done here)

- **Dashboard / Speaking practice pages**: both require a logged-in session
  (`/dashboard`, `/practice/speaking` 307-redirect anonymous requests to
  `/auth/login`). Lighthouse can't authenticate on its own -- needs a
  logged-in Playwright/Puppeteer session with real test credentials to
  measure these two.
- **Field data**: not pulled into this doc, but the plumbing already exists:
  `frontend/src/lib/sentry-client.ts` has `tracesSampleRate: 0.2`, so Sentry
  Performance is already collecting real-user transaction data -- check the
  Sentry dashboard's Performance tab directly rather than re-instrumenting.
  CrUX has no data yet (needs enough real Chrome traffic on speakoet.com to
  populate publicly) -- check https://pagespeed.web.dev periodically or
  Search Console's Core Web Vitals report once traffic volume supports it.
