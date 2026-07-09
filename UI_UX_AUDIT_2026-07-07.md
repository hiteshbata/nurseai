# SpeakOET — Full Pre-Launch UI/UX Audit

**Date:** July 7, 2026
**Method:** Hands-on review of the running application (Next.js frontend on :3000, FastAPI backend on :8000) driven with Playwright/Chromium. A fresh test account (`audit-test-claude@example.com`) was registered; login, registration validation, all 5 onboarding steps, a live AI speaking session with a real scored result, the writing editor, and the mock test were exercised interactively. 27 routes crawled logged-out and logged-in at desktop + mobile viewports; responsive checks at 320/375/390/768/1024/1280/1440/1920px; contrast, focus order, landmarks, labels, and touch targets measured in-page.

**Dev-only artifacts flagged where relevant:** stale-chunk 404s from a pre-existing dev server instance (fixed by restart), the turbopack Sentry module error, and the red "1 error" dev overlay visible in screenshots may not apply to production — verify with `next build && next start`.

---

## Executive Summary

| Dimension | Score |
|---|---|
| Overall UI | **7.0 / 10** |
| Overall UX | **6.5 / 10** |
| Accessibility | **6.0 / 10** |
| Responsiveness | **8.5 / 10** |
| Visual design | **7.0 / 10** |
| Professional appearance | **6.5 / 10** |

### Would I ship this design? **NO — but it is close (2–3 weeks of fixes).**

The core product loop (pick scenario → read brief → talk to AI patient → 9-criteria examiner report) is genuinely impressive and better designed than most AI-tutor products at this stage. What blocks launch is not the core — it's the ring of broken and unfinished things around it: a Mock Test page that literally cannot be used, a landing page that promises 5 free sessions while the product gives 3, a results page that contradicts itself about pronunciation analysis, placeholder About/Support pages, a visible `·` encoding bug on the pricing page, and a missing favicon. Every one of them is the kind of detail a paying nurse notices right before deciding whether to trust you with ₹799/month.

**What's genuinely strong:** the landing page (clear promise, strong information hierarchy, India-specific voice), the auth screens (split-panel layout, social proof, proper labels and autocomplete), the speaking flow's stepper (Select → Read Brief → Practice → Results), the reading timer, the text fallback when the mic fails, and a results report whose feedback quality is a real differentiator. Zero horizontal overflow at any width from 320px to 1920px — rare at this stage.

**What drags it down:** feature surfaces at three different levels of finish (speaking = polished, writing = decent but off-brand orange, mock test = broken, about/blog/support = stubs), three competing accent colors across flows, a new-user dashboard that is a wall of eight empty states and three upsells, and marketing copy that doesn't match the product.

---

## Critical Issues — Fix Before Launch

### 1. Mock Test is non-functional — CRITICAL
**Where:** `/mock-test`
**Problem:** The page shows "Question 1 of 10" with Previous/Next buttons, but there is no way to answer anything — no text box, no recorder. Clicking *Next* does not even advance to question 2. The footer already reads "Answered: 0 of 10 · Skipped: 10" before the user has done anything.
**Why it matters:** "Mock test mode" is a listed Elite-plan feature (₹1499/mo). A paying user who finds a dead feature will churn and may dispute the charge.
**Fix:** Remove the route (and the feature bullet) until it works, or gate it behind an honest "Coming soon" state.

### 2. Landing page promises 5 free sessions; the product gives 3 — CRITICAL
**Where:** `/` (hero CTA "Start Free — 5 Sessions on Us", final CTA "Start with 5 Free Sessions") vs. navbar "Free · 0/3 sessions" and `/upgrade` "3 speaking scenarios per month".
**Why it matters:** This is the first number a new user verifies. Breaking it in the first 5 minutes destroys trust — and advertised-vs-delivered mismatches are a consumer-protection risk.
**Fix:** Pick one number and make it consistent everywhere (hero, FAQ, final CTA, plan cards, navbar pill).

### 3. Results page contradicts itself about pronunciation analysis — CRITICAL
**Where:** `/practice/speaking` → Results.
**Problem:** The Pronunciation Analysis card shows a green check — "No pronunciation issues detected. Your speech was clear and easy to understand" — directly above a footnote reading "Pronunciation analysis is currently unavailable." Both cannot be true. In the test session no speech occurred at all (text fallback was used), yet it still praised the "speech."
**Why it matters:** The examiner report is the product. If one card is visibly making things up, users will doubt the other nine criteria too.
**Fix:** When analysis is unavailable (or the turn was typed), show a neutral empty state — never a fabricated positive result.

### 4. "Cancel anytime in Settings" — but Settings has no subscription management — CRITICAL
**Where:** `/upgrade` (all three plan cards) vs. `/profile`.
**Problem:** Every plan card says "Auto-renews monthly · Cancel anytime in Settings." The Settings page shows email, plan name, and practice plan — no manage/cancel/billing section.
**Why it matters:** For auto-renewing payments in India (Razorpay e-mandates), a promised-but-missing cancel path is both a churn-support nightmare and a compliance problem.
**Fix:** Add a Billing section to Settings (plan, next charge date, payment method, cancel button) before taking a single subscription.

### 5. Literal `·` rendered on the pricing page — CRITICAL (trivial fix)
**Where:** `/upgrade`, under all three Subscribe buttons.
**Problem:** The text renders as `Auto-renews monthly · Cancel anytime in Settings` — the escape sequence shows instead of the "·" character.
**Why it matters:** It sits directly under the payment buttons — the exact moment a user is judging whether this company is careful with money.
**Fix:** Replace the escaped string with the actual character (or `&middot;`).

### 6. About, Support, and Blog are placeholder stubs — CRITICAL
**Where:** `/about` ("Our story and mission coming soon"), `/support` (one email line), `/blog` (empty).
**Why it matters:** These are the pages skeptical buyers open to check whether the company is real. They're linked from the footer of every page, including checkout-adjacent ones.
**Fix:** Write minimal real content (3 paragraphs + a photo beats "coming soon"), or remove the links until the pages exist. Support at minimum needs a contact form or FAQ.

### 7. Onboarding is never enforced — and restarts from step 1 every time — HIGH
**Where:** `/onboarding`, login flow.
**Problem:** A brand-new account's first login lands directly on `/dashboard`; onboarding only appears if the user finds it. Returning to `/onboarding` after completing it restarts at "Step 1 of 5" as if nothing was saved (the data did save — Settings shows Target Band B). The final "Go to Dashboard" button hung on "Saving…" with no redirect.
**Fix:** Route un-onboarded users to `/onboarding` after first login; resume at the last incomplete step; on completion, redirect and never show the wizard again (deep-link goes to Settings → Practice Plan instead).

### 8. Writing and Mock Test are unreachable from navigation — HIGH
**Where:** Navbar (Dashboard · Speaking only).
**Problem:** `/practice/writing` and `/mock-test` exist and are sold as plan features, but no menu, dashboard card, or link leads to them. Meanwhile a free user who finds `/practice/writing` can use it, even though writing is a Pro feature on the pricing page.
**Fix:** Add "Writing" to the navbar (and a dashboard card); apply the same plan-gating logic used for speaking sessions.

### 9. New-user dashboard is a wall of empty states and upsells — HIGH
**Where:** `/dashboard`, first visit.
**Problem:** Before the first session the page stacks: empty exam-date card (a bare "—" with no way to set it), empty score trend, empty skills panel, empty streak grid, ten locked badges, empty sessions table — plus three monetization units (gradient plan banner, "AI Study Plan → Upgrade to Elite", locked AI Coach). The one thing a new user should do — start their first roleplay — is a dark card at the very bottom of the page.
**Fix:** First-run dashboard should be one hero action ("Start your first 5-minute roleplay") plus at most one upsell. Reveal analytics modules as they gain data. Make the exam-date card a one-click setter.

### 10. Login form bypasses browser validation and surfaces raw API errors — HIGH
**Where:** `/auth/login` (`noValidate` on the form, line ~145 of `frontend/app/auth/login/page.tsx`).
**Problem:** Submitting the empty form sends the request anyway and shows Supabase's raw error as a toast: "missing email or phone". A wrong password shows "Invalid login credentials" — accurate but cold, and only as a transient toast.
**Fix:** Remove `noValidate` or add field-level messages ("Enter your email"), and translate API errors to human copy ("That email and password don't match. Try again or reset your password.").

### 11. /admin bounces a logged-in user to the login screen — HIGH
**Where:** `/admin` as a non-admin.
**Problem:** An authenticated non-admin visiting `/admin` is redirected to `/auth/login?returnTo=/dashboard` — a login page for someone who is already logged in, with 401 errors in the console.
**Fix:** Redirect straight to `/dashboard` (optionally with a "You don't have access to that page" toast).

### 12. No favicon; every page has the identical title — HIGH
**Where:** All routes — `/favicon.ico` 404s on every load; every tab reads "SpeakOET — OET Speaking Practice for Nurses". A `favicon.svg` already exists in `/public` but is not wired up.
**Why it matters:** Generic tab icon + identical titles hurts SEO for the five `/learn` articles (which exist purely for SEO), makes multi-tab use confusing, and is the fastest "unfinished" signal there is.
**Fix:** Wire the icon and per-page `title`/`description` via the Next.js metadata API.

### 13. Sentry module error thrown on every page load (dev) — HIGH
**Where:** All routes — `sentry.client.config.ts` module factory error; also the red "1 error" dev overlay.
**Fix:** Verify it's dev/turbopack-only; if it reproduces in a production build, error monitoring is broken exactly when needed at launch.

### 14. ✅ FIXED (indicator only) — In-session state says "Recording" while the app is idle — MEDIUM
**Where:** Practice session header.
**Problem:** The conversation header shows a red ● "Recording" with a running timer while the center panel says "Ready to begin — tap the orb below." For a nurse worried about being recorded, a false "Recording" indicator is exactly the wrong signal — and the timer starting before the user speaks feels unfair in a timed exam context.
**Fix:** Show "Recording" only while the mic is actually capturing; label the pre-start state "Not recording yet."
**Resolved 2026-07-08:** Header badge now reflects `session.isListening` instead of the always-on session-long recorder. Red pulsing "Recording" while actively listening; gray "Not recording yet" pre-first-turn; gray "Mic paused" between turns. Timer-fairness half of this item (timer starts on phase-open, not on first speech) is unaddressed.

### 15. ✅ FIXED (partially) — Scenario picker: 124 cards, no search, no pagination — MEDIUM
**Where:** `/practice/speaking`.
**Problem:** All 124 scenarios render as one endless list. Category chips (28px tall — under touch-target minimum) are the only filter; there's no search, no difficulty filter, no "recommended next", no visited/completed marker.
**Fix:** Add a search box, difficulty + "not yet tried" filters, and completed-state badges on cards; virtualize or paginate the list.
**Resolved 2026-07-08:** Search box (title/setting), difficulty select, and status select (All/Completed/Not yet tried) added; completed scenarios (from `GET /submissions?module=speaking`) get a green "Completed" badge; specialty pills bumped 28px→44px tall. Virtualization/pagination and "recommended next" still open.

### 16. ✅ FIXED (partially) — Contrast: level letters, muted helper text, RECOMMENDED badge — MEDIUM
**Where:** `/dashboard`.
**Problem:** "Current Level" letter grade (`text-accent`, emerald-500) measured 2.59:1 against a 3:1 minimum; the chart empty-state helper text ("Not enough sessions yet…", `text-slate-400`) measured 2.56:1 against a 4.5:1 minimum; the "⭐ RECOMMENDED FOR YOU" badge (`text-teal-600`) measured 3.58:1 against a 4.5:1 minimum.
**Fix:** Darken each to a shade that clears its WCAG AA threshold with margin.
**Resolved 2026-07-08:** `text-accent` → `text-emerald-700` (~5.6:1) for the level-grade text in [hero-cards.tsx](frontend/app/components/oet/hero-cards.tsx) and [progress-section.tsx](frontend/app/components/oet/progress-section.tsx); `text-slate-400` → `text-slate-500` (~4.9:1) for the chart empty state in [ProgressChart.tsx](frontend/app/components/ProgressChart.tsx); `text-teal-600` → `text-teal-700` (~5.6:1) for the badge in [RecommendedCaseCard.tsx](frontend/app/components/oet/RecommendedCaseCard.tsx). Verified live on `/dashboard`. Navbar "Upgrade" pill contrast and the green→amber gradient banner (items #19 and #21 in the ranked list) were fixed separately this session too (`emerald-700` pill, solid navy `#0F2356` banner). Remaining unaddressed: "Ready for today's OET practice?" borderline 4.49:1 line, and manual verification of white text on any remaining gradients.

---

## Page-by-Page Review

Ratings are /10: Overall · Visual · UX · A11y · Professional. Performance is not scored per page — the dev server distorts it — but no page ships notably heavy assets (the app uses zero images, which keeps it fast).

| Page | Overall | Vis | UX | A11y | Pro | Notes |
|---|---|---|---|---|---|---|
| **Landing `/`** | 8 | 8 | 8 | 6 | 8 | Best page in the product. Strong hero ("AI patient that responds"), problem-led sections, India-specific pricing and testimonials, FAQ. Weaknesses: h1 renders "OET Speakingwith" (missing space/break between spans); "5 free sessions" claim contradicts product; testimonials/counters ("Join 447 nurses") need to be real or removed; nav "Upgrade" pill fails contrast (2.5:1). |
| **Login `/auth/login`** | 7.5 | 8 | 7 | 7 | 8 | Handsome split panel, Google SSO, labeled fields, password toggle, autocomplete. Raw API error copy; noValidate; error shown only as toast; at 1920px the layout floats with uneven white gutters. |
| **Register `/auth/register`** | 7.5 | 8 | 7 | 7 | 8 | Consistent with login. No password-strength hint or requirements; no terms/privacy line at signup; confirm-password mismatch caught only on submit. |
| **Forgot password** | 7 | 8 | 7 | 7 | 7 | Single clear field. Copy should confirm "we've sent a link if that email exists." |
| **Onboarding `/onboarding`** | 5 | 4 | 5 | 6 | 4 | Completely off-brand: generic blue-600 buttons, unstyled native selects, default focus states — feels like a different product than the emerald/navy app around it. Flow content is good (country, exam date, target band, diagnostic offer, plan summary). Not enforced; restarts at step 1; "Saving…" dead-end; disabled Continue with no explanation of missing required fields. |
| **Dashboard `/dashboard`** | 6 | 7 | 5 | 6 | 6 | Rich, well-crafted modules — but 8 empty states + 3 upsells on first run, primary action buried at page bottom, "Days until exam" is a dead "—", heading levels jump (h1→h3), "Get 40 sessions" banner pitches Pro numbers at a free user without saying it's Pro. |
| **Speaking list `/practice/speaking`** | 6.5 | 7 | 6 | 6 | 7 | Clean cards with difficulty + category chips. 124 cards, no search/pagination; chips under 44px touch size; no completed/tried markers. |
| **Scenario brief** | 8.5 | 8 | 9 | 7 | 9 | The stepper (Select → Read Brief → Practice → Results), task list, reading timer and "Start Early" mirror the real OET flow beautifully. Best-designed step in the app. |
| **Live session** | 7.5 | 8 | 7 | 6 | 8 | Smart split layout (brief stays visible), orb with "Tap to speak", text fallback input, End Session. ~~False "Recording" state~~ ✅ Fixed 2026-07-08; orb sits below the fold at 900px height; no captions/transcript during the call; no mute or replay-patient control. |
| **Results** | 8 | 8 | 8 | 7 | 8 | The differentiator: 9 criteria each with specific, quoted feedback, band score, strengths/focus areas, examiner summary, transcript. Marred by the pronunciation contradiction and three stacked upsells before the scores. |
| **Writing list + editor** | 6.5 | 6 | 7 | 6 | 6 | Works end-to-end with case notes and "Submit for Scoring". But it introduces a third accent (orange) unseen anywhere else, isn't in the nav, and isn't plan-gated as pricing says it should be. No word count target/timer visible in list cards. |
| **Mock test `/mock-test`** | 1 | 4 | 0 | 5 | 1 | Broken: no answer mechanism, Next doesn't advance, "Skipped: 10" pre-filled. Must not ship. |
| **Settings `/profile`** | 5.5 | 7 | 5 | 7 | 6 | Clean read-only account card + editable practice plan. Missing: change password, billing/cancel (promised on /upgrade), notification prefs, delete account (privacy expectation), sign-out on the page itself. |
| **Upgrade `/upgrade`** | 6.5 | 7 | 7 | 6 | 5 | Clear 4-plan comparison, popular highlight, INR pricing. `·` bug under every button; "MOST POPULAR" ribbon + "Most Popular" pill duplicated on the same card; free plan says 3 sessions vs landing's 5; no yearly option or savings framing; no FAQ (refunds, payment methods) at the decision point. |
| **About / Support / Blog** | 2 | 3 | 2 | 6 | 2 | Placeholders. Also: on these pages the logged-out navbar shows "Dashboard / Speaking" links (different from the marketing navbar on the landing page) — two nav systems for the same logged-out visitor. |
| **Learn articles (×5)** | 6.5 | 6 | 7 | 7 | 7 | Solid SEO content, readable measure. All share the same generic title tag (kills the SEO purpose); no table of contents, author, date, or in-article CTA design beyond links. |
| **Privacy / Terms** | 6 | 6 | 6 | 7 | 6 | Real content present. Fine for launch. |

---

## Component Review

| Component | Verdict |
|---|---|
| **Buttons** | **Inconsistent.** Four primary styles across flows: emerald pill (marketing/auth), navy (session/results), blue-600 (onboarding), orange (writing). Radii vary (full-round vs 12px). Heights consistent (44px) in auth but not elsewhere. Consolidate to one primary + one secondary + one destructive, tokenized. |
| **Inputs & selects** | **Split personality.** Auth inputs are excellent (labels, focus ring, hover, autocomplete, password toggle). Onboarding uses bare native selects with default styling. Date field is a native date input showing "dd-mm-yyyy". Style selects to match text inputs. |
| **Cards** | **Mostly consistent** — white, 1px border, ~12–16px radius, soft shadow. Scenario, dashboard, and plan cards feel like one family. Writing cards break it with orange CTAs. |
| **Navbar** | **Two systems.** Marketing navbar (How It Works/Features/Pricing) on `/`, app navbar (Dashboard/Speaking) when logged in — but public subpages show the app navbar to logged-out users. Missing: Writing/Mock links, active-page indicator. |
| **User menu** | **Good.** Name, email, plan status, Upgrade, Dashboard, Settings, red Sign Out. Email truncates with ellipsis correctly. |
| **Toasts** | react-hot-toast, top-center. Used for both validation and success — validation belongs inline next to the field. Raw API strings leak through. |
| **Badges / chips** | Difficulty chips (easy/medium/hard) use green/amber/red consistently. Category filter chips are 28px tall (touch target fail) and the selected state is subtle. |
| **Progress bars** | Four different progress visuals (onboarding blue bar, plan-usage white-on-gradient, journey emerald bar, brief reading timer). Unify thickness/radius via a token. |
| **Tables** | Recent Sessions table is clean on desktop; at 390px the ACTION column truncates ("ACTIO"). Switch to stacked rows or cards on mobile. |
| **Modals / dialogs** | Almost none used — flows are full-page, which is a good choice. End-session confirmation works. Ensure it traps focus and closes on Esc. |
| **Charts (recharts)** | Score trend renders an empty panel with helper text pre-data — acceptable, but the empty module shouldn't occupy prime dashboard space on day one. |
| **Icons / logo** | Lucide icons used consistently; logo waveform+stethoscope is distinctive and renders in light/dark variants. No favicon derived from it yet. |
| **Empty states** | Present everywhere but text-only ("No sessions yet"). None offer an action button — every empty state should link to the act that fills it. |
| **VoiceOrb** | The signature component. Idle/listening states read well; add a visible "AI is speaking" vs "your turn" distinction and a subtle level meter so users trust the mic is hearing them. |

---

## Accessibility Report

**Working well:** `lang="en"` set; header/nav/main/footer landmarks on all pages; every form input has a real `<label>` (0 unlabeled found on any page); focus rings visible on every element tabbed through; password toggle has an aria-label; zero unnamed buttons/links across the five audited routes; autocomplete attributes on auth fields.

**Issues found (WCAG references):**

- **Contrast (1.4.3):** measured failures — ~~navbar "Upgrade" pill white-on-emerald 2.54:1 at 12px~~ ✅ Fixed 2026-07-08 (`emerald-700`); ~~"Current Level" letter grade 2.59:1 (needs 3:1 at 48px)~~ ✅ Fixed 2026-07-08 (`emerald-700`, ~5.6:1); ~~muted helper text "Not enough sessions yet…" 2.56:1~~ ✅ Fixed 2026-07-08 (`slate-500`, ~4.9:1); ~~"⭐ RECOMMENDED FOR YOU" 3.58:1~~ ✅ Fixed 2026-07-08 (`teal-700`, ~5.6:1); "Ready for today's OET practice?" 4.49:1 (borderline) still open. ~~Text on the green→amber gradient banner could not be measured automatically~~ ✅ Fixed 2026-07-08 — banner replaced with solid navy `#0F2356` + white text.
- **Touch targets (2.5.8):** category chips 28px tall; navbar links ~20px; footer links 20px; show-password toggle 16×16 (verify padding extends hit area to ≥24px); "Upgrade" pill 24px tall.
- **No skip-to-content link (2.4.1):** keyboard users must tab through the navbar on every page.
- **Page titles (2.4.2):** every page identical — screen-reader users can't tell pages apart in the tab list.
- **Heading hierarchy (1.3.1):** dashboard jumps h1→h3; footer uses h4s without preceding levels.
- **Dynamic announcements (4.1.3):** session state changes ("Recording", patient reply arriving, score ready) have no `aria-live` region — a blind user gets silence during the core flow. The conversation transcript area should be `aria-live="polite"`.
- **Onboarding selects:** native (accessible by default — keep that when restyling; don't replace with non-semantic divs).
- **Disabled-button dead ends:** onboarding Continue and session Send are disabled with no hint of why — pair disabled states with visible helper text.

---

## Responsive Report

**Headline result: zero horizontal overflow** on all tested routes (`/`, `/dashboard`, `/practice/speaking`, `/upgrade`, `/auth/register`) at 320, 375, 390, 768, 1024, 1280, 1440 and 1920px. Cards stack correctly, the auth left panel hides below lg, plan cards go single-column, the hamburger menu appears on mobile.

- **390px dashboard:** Recent Sessions table truncates its last column ("ACTIO…"); page height balloons to ~4,800px — the empty-module problem is worse on mobile.
- **320px:** layouts hold, but chip rows wrap into 3 lines on the scenario page; acceptable.
- **1920px:** auth pages float mid-canvas with asymmetric white bands left/right of the navy panel; landing sections cap width nicely but the hero could use more breathing room at ultra-wide.
- **Live session at short viewports:** at 900px height the orb + End Session sit at the very bottom edge; on a 768px-tall laptop the orb risks clipping below the fold while "Recording" runs — test 1366×768 explicitly.
- Mock test and writing pages were not stress-tested at all widths (one is broken, one is behind a long editor) — re-run after fixes.

---

## Design System Report

The app has the raw material of a system — navy `#0F2356`, emerald-500, gray scale, 12px radii, Segoe/system sans — but it's applied per-flow, not from tokens:

- **Color fragmentation:** emerald (marketing/auth/speaking) vs blue-600 (entire onboarding flow) vs orange (writing CTAs) vs navy (session/results primaries). Pick: navy = primary action, emerald = brand/success/positive delta, one accent for warnings. Kill blue and orange or assign them real semantic jobs.
- **Radius:** auth inputs/buttons 12px (`rounded-xl`), pills fully round, onboarding 8px, plan cards 16px. Standardize on a 3-step radius scale.
- **Type scale:** generally consistent (12/14/16/18/24/30+), but letter-grade displays (48px) and dashboards mix weights ad hoc. Define display/heading/body/caption tokens.
- **Spacing:** Tailwind default scale keeps things mostly aligned; dashboard modules use inconsistent internal padding (14–24px). Pick card padding once.
- **Buttons/inputs:** extract the auth-page input and button styles into shared components — they're the best-executed controls in the app; onboarding should import them, not reinvent.
- **Shadows:** subtle and consistent where used; onboarding card shadow is heavier. Tokenize two elevations.
- **Recommendation:** create `components/ui/` primitives (Button, Input, Select, Card, Chip, ProgressBar) with class-variance-authority (already a dependency!) and refactor onboarding + writing to consume them. That single refactor fixes 80% of the inconsistency in this report.

---

## UX Improvements

- **Shorten the path to the "wow":** the AI-patient conversation is the magic. Offer a 60-second guest demo on the landing page (one scripted exchange, no signup) — the current funnel requires register → confirm email → login → find scenario before any magic happens.
- **First-run checklist** instead of empty dashboard: "1. Set your exam date · 2. Do the 5-min diagnostic · 3. Get your baseline band." Three checkboxes beat eight empty modules.
- **Make "Days until exam" tappable** — it's the single highest-leverage motivator in test prep and it's currently a dead dash.
- ~~**Post-session momentum:** Results ends with "Try Another Scenario / Go to Dashboard." Add "Retry this scenario targeting your weakest criterion (e.g. Empathy 1/6)" — turns feedback into a loop.~~ ✅ Fixed 2026-07-08.
- **Recommend, don't list:** the 124-scenario list should lead with 3 recommended cards ("based on your weakest criteria") above the browse-all grid.
- **Session affordance:** auto-start listening after the patient finishes speaking (with a visible toggle), or at least pulse the orb — "tap to speak" each turn adds friction to a conversation that's supposed to feel natural.
- **Reduce upsell density:** one contextual upsell per screen. Results currently shows three before the first score.
- **Consolidate the two navbars** and add an active-state underline so users always know where they are.
- **Login → destination:** after sign-in the app calls the onboarding-status API before navigating; do it optimistically or in middleware so the click feels instant.

---

## Visual Improvements

- **Typography:** adopt a distinctive display face for headings; fix the hero's missing space ("OET Speakingwith"); tighten h1 line-height on mobile.
- **Spacing:** normalize card padding (20px) and section rhythm (64/96px) on marketing pages; dashboard modules need a consistent 16px internal grid.
- **Colors:** execute the token consolidation above; replace the green→amber gradient banner (reads as a warning gradient and likely fails contrast) with a navy or emerald solid.
- **Icons:** keep Lucide, one stroke weight; replace emoji used as UI (🎤, ⭐, 🎉) with icons for a more premium feel.
- **Cards:** add hover elevation on interactive cards only — currently static cards and clickable cards look identical.
- **Buttons:** one primary style; give destructive/ending actions (End Session) an outline-danger treatment instead of ghost gray.
- **Forms:** style native selects, add password-strength meter, inline validation messages under fields.
- **Navigation:** active link indicator; slightly larger hit areas; move the plan pill ("Free · 1/3") into the user menu on mobile to reduce clutter.
- **Empty states:** add a small illustration or icon + one action button each.
- **Loading states:** add skeleton cards for dashboard and scenario list; label the post-session wait ("Scoring your conversation — about 15 seconds") with a progress indicator, since it's the longest wait in the product.
- **Error states:** design one friendly error card pattern (icon, plain-English message, retry) and use it for API failures; never show raw backend strings.
- **Animations:** the orb is a great canvas — give it distinct idle/listening/speaking motion; add a small band-reveal moment on Results (respecting reduced-motion) to celebrate completion.

---

## Inspiration

| Page | Look at | What to learn |
|---|---|---|
| Landing | **Speak** (speak.com), **Duolingo**, **Linear** | Speak sells an AI speaking partner with an interactive demo right in the hero — exactly this product. Duolingo: making a test-prep brand feel warm, not clinical. Linear: type discipline and restrained motion that make a small team look enterprise-grade. |
| Dashboard | **Duolingo**, **WHOOP / Rise** habit apps, **Notion "getting started"** | Duolingo's single dominant CTA ("Continue lesson") + streak flame; habit apps' progressive disclosure of stats; Notion's checklist-driven first run. |
| Practice session | **ChatGPT voice mode**, **ELSA Speak**, **Speak** | ChatGPT voice: orb state language (idle/listening/thinking/speaking) users already understand. ELSA: pronunciation feedback UI with word-level highlights. Speak: turn-taking cues and live captions during AI conversation. |
| Results report | **ELSA Speak reports**, **Grammarly editor panel**, **Stripe Radar review UI** | Grammarly: criteria as expandable inline annotations on the transcript rather than cards above it. Stripe: presenting a score + reasons with calm authority. ELSA: band-progress framing ("you're 0.5 from B"). |
| Pricing | **Notion**, **Cursor**, **Cal.com** | Notion: feature-table comparison below cards. Cursor: confident 3-plan simplicity, annual toggle. Cal.com: trust row (payment logos, cancel policy, FAQ) directly under the buy buttons. |
| Onboarding | **Duolingo**, **Headspace**, **Vercel signup** | Duolingo: one question per screen with instant selection advancing automatically. Headspace: warm copy that builds motivation while collecting data. Vercel: brand-consistent controls throughout — the thing this one is missing most. |

---

## Priority Roadmap

### Immediate — before any public launch
- Remove or fix Mock Test; remove the Elite bullet until it exists
- Align free-session count everywhere (5 vs 3)
- Fix pronunciation-analysis contradiction on Results
- Fix `·` on /upgrade; remove duplicate "Most Popular"
- Add Billing/cancel section to Settings (or change the plan-card copy)
- Favicon + per-page titles/meta descriptions
- Replace About/Support/Blog stubs with real minimal content or unlink them
- Enforce onboarding for new users; fix resume + "Saving…" dead-end
- Fix /admin redirect for non-admins
- Verify the Sentry client error doesn't occur in the production build
- Fix hero "OET Speakingwith" text run-together
- Humanize auth error messages; remove noValidate or add inline validation

### High priority — first two weeks after the above
- First-run dashboard: single hero CTA + 3-step checklist; hide empty analytics modules
- Add Writing to navigation and gate it by plan; decide Mock Test's plan story
- ~~True "Recording" state~~ ✅ Fixed 2026-07-08 (indicator only — aria-live announcements still open) + aria-live announcements in the session
- ~~Scenario search + filters + completed markers~~ ✅ Fixed 2026-07-08 (pagination/virtualization still open)
- ~~Contrast fixes (Upgrade pill, level letters, muted text, RECOMMENDED badge, gradient banner)~~ ✅ Fixed 2026-07-08 — touch-target sizes still open
- Tokenized Button/Input/Select/Card components; refactor onboarding + writing onto them
- Exam-date setter on the dashboard card
- Scoring-wait progress state after End Session

### Medium priority
- Recommended-scenarios row
- ~~Retry-weakest-criterion CTA on Results~~ ✅ Fixed 2026-07-08
- Single unified navbar with active states; move plan pill into user menu on mobile
- Skip link, heading-order fixes, mobile sessions table → cards
- Password strength meter; change-password and delete-account in Settings
- ~~Reduce upsell density on Results; one contextual upsell rule~~ ✅ Fixed 2026-07-08
- Per-article SEO metadata + TOC for /learn pages
- Landing demo widget (guest mini-conversation)

### Nice to have
- Orb state animations (idle/listening/AI-speaking) + live captions
- Band-reveal celebration on Results (reduced-motion aware)
- Annual pricing toggle; feature comparison table; payment-trust row
- Dark mode for the app itself; replace emoji-as-UI with icons
- Streak reminders / WhatsApp nudges (ties into the paused WhatsApp integration)

---

## Final Verdict

**As lead designer I would not approve a public launch this week — and I'd expect to approve it within two to three weeks.** The reasoning: this product's competitive moat is *trust in its examiner feedback*. Every blocker on the Immediate list is a trust leak — a broken feature that's on the price list, a number that doesn't match between ad and app, a feedback card that contradicts itself, a payment page with an encoding bug, "coming soon" where the company story should be. None of them is hard to fix; all of them are fatal to a first impression when the user is a nurse about to spend ₹799 of her own money on her migration dream.

The core experience — brief → conversation → 9-criteria report — is already at a quality level that justifies charging. Fix the ring around the core, unify the design language onto the auth/speaking flow's standard, and this ships with confidence.

---

## Top 50 UI/UX Improvements — Ranked by Impact

1. **Fix or remove Mock Test** — a dead paid feature is the single worst thing shipping today (`/mock-test`).
2. **Make the free-session count consistent** — landing says 5, product gives 3 (`/`, `/upgrade`, navbar).
3. **Fix the pronunciation-analysis contradiction** — never show fabricated positive feedback (Results).
4. **Add Billing/cancel to Settings** or stop promising "Cancel anytime in Settings" (`/upgrade`, `/profile`).
5. **First-run dashboard = one clear action** — hero "Start your first roleplay" + checklist; hide empty modules (`/dashboard`).
6. **Enforce onboarding after first login** — it's where personalization data comes from (login flow).
7. **Replace About/Support/Blog stubs** with real content or unlink them (footer, all pages).
8. **Fix `·` under Subscribe buttons** (`/upgrade`).
9. **Add favicon + per-page titles/descriptions** (all routes, biggest SEO lever for `/learn`).
10. **Verify/fix the Sentry error on every page load** in a production build.
11. **Unify the design system** — one Button/Input/Select/Card set; refactor onboarding off blue-600 and writing off orange.
12. **Add Writing (and future Mock Test) to navigation** and plan-gate them consistently.
13. ~~Scenario search + filters + completed markers~~ ✅ **FIXED 2026-07-08** — 124 unsearchable cards today (`/practice/speaking`); search box, difficulty/status filters, completed badges, 44px touch targets added. Pagination/virtualization not done.
14. ~~True "Recording" indicator~~ ✅ **FIXED 2026-07-08** — only red when the mic is live (session); badge now tracks `session.isListening` instead of the always-on background recorder.
15. **Scoring-wait progress state** — "Scoring your conversation, ~15s" after End Session.
16. **Humanize auth errors + inline validation** — kill "missing email or phone" (`/auth/login`).
17. **Fix hero text "OET Speakingwith"** (`/`).
18. **Make "Days until exam" a one-tap setter** (`/dashboard`).
19. ~~**Contrast: navbar Upgrade pill 2.5:1**~~ ✅ **FIXED 2026-07-08** → `emerald-700` (all pages).
20. ~~**Contrast: level letters, muted helper text, RECOMMENDED badge**~~ ✅ **FIXED 2026-07-08** → `emerald-700` / `slate-500` / `teal-700`, all ≥4.9:1 (dashboard).
21. ~~**Verify white text on the green→amber banner**~~ ✅ **FIXED 2026-07-08** → replaced with solid navy `#0F2356` (dashboard).
22. **Fix /admin → login dead-end for signed-in users.**
23. **Onboarding resume + fix "Saving…" hang** (`/onboarding`).
24. **Recommended-scenarios row above the grid** — recommendation exists on the dashboard; bring it to the picker.
25. ~~**"Retry weakest criterion" CTA on Results**~~ ✅ **FIXED 2026-07-08** — Results now shows an emerald "Retry — Focus on {criterion} ({score}/6)" button above the existing actions, computed from the lowest-scored criterion and re-launching the same scenario (`handleRetryWeakest` in [page.tsx](frontend/app/practice/speaking/page.tsx)).
26. ~~**Reduce Results upsells from three to one** contextual unit.~~ ✅ **FIXED 2026-07-08** — added a single `activeUpsell` priority variable (premium-trial retention > locked-criteria Pro unlock > Elite pronunciation) in [page.tsx](frontend/app/practice/speaking/page.tsx) so only one of the three banners can render per view; [PlanUsageBanner.tsx](frontend/app/components/PlanUsageBanner.tsx) had its own "Upgrade to X" CTA stripped down to usage info only.
27. **aria-live on conversation + session states** — the core flow is silent to screen readers.
28. **Touch targets ≥44px** — category chips, navbar links, footer links, password toggle.
29. **Skip-to-content link** (all pages).
30. **Heading hierarchy fixes** — no h1→h3 jumps (dashboard, footer).
31. **Single navbar system with active-page indicator** — public subpages currently show the app nav to logged-out users.
32. **Mobile sessions table → stacked cards** — ACTION column truncates at 390px (`/dashboard`).
33. **Style native selects + date input** to match the (excellent) auth inputs (onboarding, forms).
34. **Explain disabled buttons** — "Select a country to continue" under a disabled Continue (onboarding, session Send).
35. **Password strength hint on register** + terms/privacy line (`/auth/register`).
36. **Change password + delete account in Settings** (`/profile`).
37. **Login redirect without the blocking status call** — navigate optimistically (auth flow).
38. **Empty states get action buttons** — every "No X yet" links to creating X (dashboard).
39. **Orb state animations** — distinct idle / listening / AI-speaking motion + level meter (session).
40. **Live captions during the AI conversation** — comprehension support and accessibility in one (session).
41. **Auto-listen after patient finishes (toggleable)** — remove tap-per-turn friction (session).
42. **Keep the orb above the fold** at 768px-tall laptops (session layout).
43. **Remove duplicate "Most Popular" markers**; add annual toggle + trust row (`/upgrade`).
44. **Landing guest demo** — one scripted AI-patient exchange before signup (`/`).
45. **Real numbers only** — "Join 447 nurses", testimonials, star ratings must be verifiable or removed (`/`, auth panels).
46. **Skeleton loading for dashboard + scenario grid** (perceived performance).
47. **Replace emoji-as-UI with Lucide icons** (🎤/⭐/🎉 in dashboard, results, onboarding).
48. **Hover/pressed states on interactive cards only** — clickable vs static must look different (scenario grid, dashboard).
49. **SEO furniture for /learn** — unique titles, meta, TOC, author/date, inline CTA (5 articles).
50. **Band-reveal celebration on Results** (reduced-motion aware) — make the payoff feel like one.

---

*Web version of this report: https://claude.ai/code/artifact/7d5bcf5c-803a-4c7c-b49e-2c770226e806*
*Test account used: `audit-test-claude@example.com` (exists in Supabase — delete when no longer needed).*
