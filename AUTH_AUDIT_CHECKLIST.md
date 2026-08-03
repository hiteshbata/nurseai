# Auth & Routing — Production Audit Checklist

**Audit date:** 2026-08-02
**Score goal:** 100/100

---

## 🔴 Must Fix

| # | Issue | Files | Lines | Fix |
|---|---|---|---|---|
| M1 | **Infinite redirect loop for anonymous users** — `status === 'authenticated'` is `true` for anonymous sessions, so Home calls `/onboarding/status` → fails → pushes to `/dashboard`. Dashboard sees `is_anonymous` → pushes back to `/`. Local state resets on remount → infinite loop. Triggered when anonymous user navigates to `/` (bookmark, direct URL, or clicking the logo in the anonymous AppShell header). | `app/page.tsx` + `app/dashboard/page.tsx` | `page.tsx:75-76` `dashboard/page.tsx:84-85` | Add `!session?.user?.is_anonymous` guard to the effect in Home page, or redirect anonymous users to `/tools/oet-mock-test-free` instead of `/dashboard` (consistent with what Dashboard does for anonymous users). |
| M2 | **Anonymous user reaches `/onboarding` via client-side guard gap** — Middleware passes anonymous users (they have a valid `user` object). Onboarding page redirects `unauthenticated` but does NOT redirect `is_anonymous`. Anonymous user sees the full 5-step onboarding wizard, which writes to a profile they cannot have. | `app/onboarding/page.tsx` + `middleware.ts` | `onboarding/page.tsx:72-76` (only checks `unauthenticated`) | Add `is_anonymous` check in onboarding page. Redirect anonymous users to the free mock test or signup flow. |

---

## 🟡 Should Fix

| # | Issue | Files | Lines | Fix |
|---|---|---|---|---|
| S1 | **Onboarding status checked in 5 separate locations** — Any change to the onboarding API response shape, field name, or redirect logic must be synchronized across all 5 sites. Guaranteed divergence over time. | `app/page.tsx`, `app/dashboard/page.tsx`, `app/auth/login/page.tsx`, `app/auth/callback/page.tsx`, `app/onboarding/page.tsx` | `page.tsx:77`, `dashboard/page.tsx:96`, `login/page.tsx:116`, `callback/page.tsx:38`, `onboarding/page.tsx:99` | Extract to a shared function: `resolveOnboardingRedirect(): Promise<string>` that returns the correct path (`'/dashboard'`, `'/onboarding'`, `'/profile#practice-plan'`). Call from all 5 locations. |
| S2 | **No 401 interceptor in `api.ts`** — Access token expires mid-browsing. `api.ts` caches the token for 60 seconds. API calls between token expiry and `TOKEN_REFRESHED` event silently fail with 401. No retry-after-refresh, no user-facing error feedback. | `src/lib/api.ts` | `api.ts:24` (token cache) | Add a 401 response interceptor that waits for `TOKEN_REFRESHED` via `onAuthStateChange`, retries the request once, and only then shows a toast. |
| S3 | **Marketing Navbar visible for authenticated users on client-side `/` nav** — ConditionalLayout uses pathname only. An authenticated user doing `router.push('/')` sees Navbar + Footer + empty content (Home returns `null`) before the useEffect redirect fires. | `app/conditional-layout.tsx` + `app/page.tsx` | `conditional-layout.tsx:32-33` `page.tsx:88` | Home page should return a loading spinner instead of `null`, or ConditionalLayout should check auth state via `useSupabaseSession` and render AppShell wrapper for `/` when authenticated. |
| S4 | **Potential login→dashboard→login transient flash** — `signIn()` resolves before Supabase writes tokens to localStorage. If dashboard's `getSession()` reads null before the write completes, it redirects to `/auth/login`, which then detects the session and redirects back. | `src/lib/supabase.ts` + `app/dashboard/page.tsx` + `app/auth/login/page.tsx` | `supabase.ts:53`, `dashboard/page.tsx:78-80`, `login/page.tsx:57-59` | After `signIn()`, wait for `onAuthStateChange` to fire `SIGNED_IN` before calling `router.push` to dashboard. Or: dashboard should not redirect while `status === 'loading'`. Already the case, but `getSession()` may resolve with null before `onAuthStateChange` fires — add a short grace period for status=loading before treating null session as unauthenticated. |
| S5 | **`/mock-test` in `protectedPaths` is a dead route** — The real mock test lives at `/practice/mock`, which is already protected by the `/practice` prefix. No page exists at `/mock-test`. Config drift risk. | `frontend/middleware.ts` | `middleware.ts:12` | Either add the actual mock test route or remove the dead entry. The real routes that need explicit protection beyond `/practice` prefix should be documented. |
| S6 | **Subdomain matcher substring overmatch** — `about`, `blog`, `privacy`, `support`, `terms`, `learn`, `api` in the negative lookahead exclude any route containing those substrings (e.g. `/about-us-team` would skip middleware). | `frontend/middleware.ts` | `middleware.ts:121` | Use more specific patterns: `about(/.*)?$`, `blog(/.*)?$`, etc., or use `/^(about|blog|privacy|...)(/.*)?$/` alternation. |
| S7 | **Unprotected route `/tools/oet-mock-test-free` relies entirely on client-side anonymous auth** — Correct by design, but if the page has any server-rendered content that should be gated, it can't be. Document this as intentional. | `frontend/middleware.ts` | `middleware.ts:5-13` (protectedPaths list) | Add a comment documenting why `/tools` and its child routes are intentionally unprotected. Already partially documented in code comments but make explicit. |

---

## 🟢 Nice to Improve

| # | Issue | Files | Lines | Fix |
|---|---|---|---|---|
| N1 | **No auth react context** — `useSupabaseSession()` is called independently in every component. Each call creates its own `useState` + `useEffect` + `onAuthStateChange` subscription. At scale (AppShell, Navbar, Footer, page components, Providers), this is N separate subscriptions to the same Supabase event channel. | `src/lib/supabase.ts` | `supabase.ts:34-67` | Wrap `useSupabaseSession` in a React Context provider so one subscription feeds all consumers. The `access_token` stability check (`supabase.ts:47`) should be preserved inside the context value. |
| N2 | **No BroadcastChannel for cross-tab auth sync** — If user signs out in Tab 1, Tab 2 only discovers it when `onAuthStateChange` fires (which relies on Supabase's internal polling or websocket). A BroadcastChannel would give instant cross-tab notification. | `src/lib/supabase.ts` | `supabase.ts:55` (onAuthStateChange) | Add `BroadcastChannel('supabase-auth-sync')` to notify all tabs on sign-out/sign-in, preventing stale UI in non-active tabs. |
| N3 | **Hard navigation on signOut** — `window.location.href = '/'` flushes all client state and forces a full page reload. Functional but jarring compared to a soft `router.push('/')`. | `app/components/AppShell.tsx` + `app/components/Navbar.tsx` | `AppShell.tsx:476` `Navbar.tsx:256` | Consider soft navigation after signOut (the `loggingOut` guard already handles the race). The hard nav may be intentional to clear all cached state — if so, document why. |
| N4 | **Home page mounts all landing sections even when redirecting** — The Home component imports and renders HeroSection, StatsBar, PricingSection, etc. even though authenticated users only see `null` and then redirect. All 10+ section components are tree-shaken into the bundle regardless. | `app/page.tsx` | `page.tsx:6-17` (imports), `page.tsx:99-111` (JSX) | Consider dynamic imports for the landing sections so they're code-split and never loaded for authenticated users redirected by middleware. Or use a server component wrapper that only renders the client-side redirect for auth users. |
| N5 | **Dashboard calls 6 parallel API endpoints on mount** — `fetchAll()` fires `/progress/stats`, `/onboarding/status`, `/sessions/usage`, `/scoring/criteria-averages`, and `/progress/history` simultaneously. No request deduplication or prioritization. All fail silently on catch. | `app/dashboard/page.tsx` | `dashboard/page.tsx:100-135` | Add `Promise.allSettled` with partial-success handling. Show per-section skeletons instead of all-or-nothing loading. |
| N6 | **Onboarding page calls `getUser()` redundantly** — Onboarding already has the session from `useSupabaseSession()`, but also calls `supabase.auth.getUser()` at line 133 just for the user metadata. | `app/onboarding/page.tsx` | `onboarding/page.tsx:133` | Use `session?.user?.user_metadata` from `useSupabaseSession()` instead of a separate network call. |
| N7 | **No typed session/user in `useSupabaseSession`** — `session.user` is typed as the generic Supabase `User` type. `user_metadata` is `any`. No compile-time safety for fields like `full_name`, `name`, `is_anonymous`. | `src/lib/supabase.ts` | `supabase.ts:34` | Define a typed `AppUser` extending Supabase `User` with known metadata fields. Cast in `useSupabaseSession`. |
| N8 | **Missing `Suspense` boundaries on practice pages** — Dashboard has a `<Suspense>` boundary. Practice pages (speaking, writing, reading, listening, mock, vocab) do not. Slow API responses show a frozen page. | `app/practice/speaking/page.tsx` etc. | various | Add per-page `<Suspense>` with skeleton fallbacks matching the page layout. |
| N9 | **`onboarding/status` API error silently swallows on Home page** — `.catch(() => router.push('/dashboard'))` at `page.tsx:80-81` treats any error (network, 500, rate-limit) the same as "not onboarded". User is redirected to dashboard which then also fails. | `app/page.tsx` | `page.tsx:80-81` | Distinguish 404 (no profile exists) from 5xx (server error). On server errors, stay on `/` or show an error state rather than bouncing to a broken dashboard. |

---

## Summary

| Severity | Count |
|---|---|
| 🔴 Must Fix | 2 |
| 🟡 Should Fix | 7 |
| 🟢 Nice to Improve | 9 |
| **Total** | **18** |

To reach 100/100, fix all 🔴 and 🟡 items. The 🟢 items are quality-of-life improvements that don't affect correctness or security.
