# SpeakOET — Product Documentation

*Written for a Custom GPT knowledge base. Explains what SpeakOET is and how it works, in plain English, based only on what is actually built in the codebase (not on outdated docs).*

---

## 1. What Is SpeakOET?

SpeakOET is a web app that helps Indian nurses prepare for the **OET (Occupational English Test)** — the English exam nurses must pass to work in Australia, the UK, or New Zealand.

The core idea: instead of hiring a human tutor or taking a classroom course, a nurse practices with an AI. The flagship feature is a **live voice conversation with an AI-simulated patient**, which is then scored using the real, official OET Speaking rubric (9 criteria).

- Live at: **speakoet.com**
- API runs separately at: **api.speakoet.com**
- Stage: pre-launch / early stage — the product has no real customer testimonials or case studies yet.

### Who it's for

Indian nurses who:
- Are preparing for OET to work abroad (Australia, UK, New Zealand, and others — see the "Target Countries" pages)
- Speak English as a second language
- Are studying around nursing shift work, on a tight exam timeline
- Mostly use a phone or laptop, often on Indian mobile/home internet

### The core problem it solves

Getting realistic speaking practice and honest, rubric-based feedback for OET normally requires a human tutor or a paid classroom course. SpeakOET tries to replace that with a self-serve AI product nurses can use on their own schedule.

---

## 2. What the Product Actually Does (Features)

SpeakOET is organized around the 4 parts of the real OET exam, plus supporting tools.

| Module | What it does | Who can use it |
|---|---|---|
| **Speaking** | Live voice roleplay with an AI patient; AI scores the conversation on the 9 official OET criteria (Empathy, Patient's Perspective, Providing Structure, Information Gathering, Information Giving, Intelligibility, Fluency, Appropriateness of Language, Grammar & Expression). Includes 100+ pre-written clinical scenarios (beginner/intermediate/advanced). | All plans (limited number of sessions per month depending on plan) |
| **Writing** | Practice writing a referral letter — either type it, or take a photo of a handwritten letter and let AI read it (OCR) before scoring it against the real rubric. Includes a "scan with your phone while practicing on your laptop" handoff feature. | Pro and Elite plans |
| **Reading** | Practice reading passages and answering questions (multiple-choice and short-answer), or take a full timed Reading test. Includes a dictionary lookup that automatically saves new words into a personal vocabulary deck, and a "mistakes" notebook of wrong answers to review later. | Basic, Pro, and Elite plans |
| **Listening** | Same idea as Reading, but with audio instead of text — full timed listening tests with AI-generated two-speaker audio, wrong-answer notebook, and cached explanations. | Basic, Pro, and Elite plans |
| **Full Mock Test** | Combines Listening, Reading, Writing, and two Speaking roleplays into one timed, exam-like sitting. All 4 band scores are revealed together at the end. | Elite plan (one free trial attempt is available to non-logged-in visitors) |
| **Pronunciation Analysis** | Deeper phoneme-level pronunciation feedback (using Azure Speech). A simpler pattern-based version is available to other plans. | Elite plan |
| **AI Study Plan** | A personalized, AI-written weekly study plan based on a user's weak areas. | Elite plan |
| **Vocabulary Deck** | A spaced-repetition flashcard system (cards are added automatically when a user looks up a word during Reading practice). | All logged-in users |
| **Study Hub** | A daily "home base" page showing streaks, a short daily to-do list built from the user's weakest skills, and how many vocabulary cards are due. It doesn't do any scoring itself — it just summarizes progress from the other modules. | All logged-in users |
| **Progress Dashboard** | Shows score trends over time, a breakdown by scoring criterion, practice streaks, and history of past attempts. History length depends on plan (Free: last 3, Basic: last 10, Pro/Elite: unlimited). | All logged-in users |
| **AI Coach Summary** | A short AI-written summary of strengths and focus areas, generated from a user's own past scores (needs at least 3 sessions of history). | All logged-in users |
| **Grammar Coaching** | Personalized AI grammar teaching based on mistakes the user actually made. | All logged-in users (can be turned off globally via a feature flag) |
| **Attempt Comparison** | AI compares two of a user's own past attempts at the same scenario side by side. | All logged-in users (choice of attempts limited by plan history) |
| **Referral Program** | Every user gets a personal referral code (e.g. "HITESH42"). Referring a friend earns bonus practice sessions once the friend completes their first session. | All logged-in users |

### Free public tools (no login required)

- **OET Score Calculator** — works out entirely in the browser, no AI call.
- **AI Study Plan Generator** — a free lead-generation tool: enter self-reported scores, get an AI-generated study plan.
- **Free Mock Test Trial** — lets a visitor try one full mock test without creating an account first.

### Marketing / content pages

- Country-specific landing pages (Australia, Canada, India, Ireland, New Zealand, Philippines, UAE, UK)
- A blog (content managed in Sanity CMS)
- A "Learn" section with OET explainer articles (band scores, Listening, Reading, Speaking tips, OET vs IELTS, etc.)
- A help-center style "Docs" section (getting started, billing, how to practice Speaking/Writing)
- Standard pages: About, Pricing, Privacy Policy, Terms, Support/Contact

---

## 3. Business Model & Pricing

SpeakOET is a **subscription product**, billed monthly in Indian Rupees through **Razorpay**. Both one-time payments and auto-renewing subscriptions are supported.

| Plan | Price | Speaking sessions/month | What's included |
|---|---|---|---|
| **Free Trial** | ₹0 | 3 | Full 9-criteria AI scoring, AI patient conversation, standard voice, last 3 attempts saved |
| **Basic** | ₹299/month | 20 | Everything in Free, plus Reading & Listening practice, last 10 attempts saved, email support |
| **Pro** | ₹799/month | 40 | Everything in Basic, plus Writing practice (with handwriting photo scoring), a more natural AI voice, unlimited attempt history, priority email support |
| **Elite** | ₹1,499/month | 80 | Everything in Pro, plus the Full Mock Test, pronunciation analysis, the AI study plan, and WhatsApp priority support |

**Billing details:**
- A paid period lasts 30 days. If a renewal payment fails or is late, there's a 3-day grace period before the plan is downgraded.
- Payment receipts are plain receipts, **not GST tax invoices** — SpeakOET is not GST-registered.
- Discount coupon codes are supported.
- Refunds can be issued by admin staff through Razorpay, with an automatic plan downgrade if the refunded plan is still active.

---

## 4. Accounts, Roles & Access

### User accounts
- Sign-up/login is handled by Supabase Auth (email/password, plus magic-link/OAuth callback support).
- New users go through an onboarding flow that asks about their exam date, target band score, destination country, prior OET attempts, nursing specialty, and how many days a week they can study. This personalizes their study plan and dashboard.
- A user can permanently delete their own account, which removes their data across the system (submissions, session history, payment records, etc.).

### Staff roles (admin panel access)
Staff accounts have one of five roles, each one including all permissions below it:

| Role | Can do |
|---|---|
| **support** | View/search users, grant manual plan changes or bonus sessions, view failed payments, view expiring subscriptions |
| **analyst** | Everything support can, plus view the audit log and business analytics (revenue, churn, AI costs) |
| **admin** | Everything analyst can, plus manage scenarios/content, view app logs, generate refunds, change most settings |
| **owner** | Everything admin can, plus change the global AI spending cap and permanently delete users |
| *(user)* | Regular customer — no admin access |

A staff member can never grant another user a role higher than their own.

---

## 5. Admin Panel — What Staff Can Do

The admin panel (internal tool, not visible to customers) lets staff:

- **Manage content**: create/edit/delete Speaking scenarios, and upload/extract new Reading, Listening, and Writing content from PDFs (an AI reads the PDF and pre-fills the content for a staff member to review before saving).
- **Manage Mock Tests**: assemble pre-built "Mock Test packs" from existing content, rather than randomizing content per attempt.
- **Manage coupons**: create and edit discount codes.
- **Change settings live**: toggle features on/off instantly without a new deployment (e.g. turn off Writing practice, switch the AI voice provider, change pricing text) — this is a safety "kill switch" mechanism.
- **Control AI spending**: see and adjust a global daily spending cap on AI costs; the system automatically stops making AI calls if the cap is hit.
- **Manage users**: search users, view their plan/usage/scores, manually change their plan, grant bonus sessions, temporarily log in as a user to help debug an issue (logged for accountability), suspend or ban accounts, and (owner-only) permanently delete a user.
- **View an audit log**: a combined timeline of admin actions, moderation actions, and impersonation events.
- **View business analytics**: revenue (MRR/ARR), churn, plan breakdown, and a dedicated AI cost/margin report (cost per plan, top-spending users, 30-day cost trend).
- **Handle failed payments**: see declined charges and send reminder emails.
- **View error logs**: application errors reported by the system, with the ability to mark them resolved.
- **Manage subscriptions**: see who's expiring soon, send renewal reminders, or cancel a subscription.

### Automated maintenance (scheduled jobs)

A handful of housekeeping tasks run automatically on a schedule (triggered by an external scheduler, not something built into the app itself):
- Delete old logs, transcripts, and cost-tracking records (kept for 90–180 days)
- Downgrade users whose subscription has expired past the grace period
- Send "your subscription is expiring soon" reminder emails
- Send "your payment failed" reminder emails
- Keep the internal user list in sync with the login system

---

## 6. How Scoring & AI Work (Plain-English Summary)

- All plans get scored against the **same full 9-criteria OET rubric** — there's no "cheaper, shallower scoring" for lower plans. What differs by plan is the *quality of the AI model* used and the *voice* used in Speaking practice (Pro/Elite get a more natural-sounding voice and a better AI model).
- The AI provider used for scoring and for the live voice conversation is configurable behind the scenes (the team can switch between different AI companies' models without a new app release).
- A free user gets one "premium trial" session — their very first session is scored at the higher Pro-tier quality, to show them what the paid experience feels like.
- Live voice sessions have a hard time limit (5 minutes) to control cost, with a warning shown near the end.
- There is a global daily AI spending cap that automatically halts AI-cost-generating features if exceeded — a financial safety net for the business.

---

## 7. Technology Stack (High Level)

| Layer | Technology |
|---|---|
| Website (frontend) | Next.js (React), hosted on Vercel |
| Backend/API | Python (FastAPI), hosted separately |
| Database & Login | Supabase (Postgres database + built-in authentication) |
| AI text scoring | Configurable — Google Gemini, OpenRouter, or OpenAI, depending on deployment settings |
| AI voice conversation | OpenAI Realtime or Google Gemini Live (switchable) |
| Payments | Razorpay |
| Blog content | Sanity (a content management system) |
| Error tracking | Sentry |
| Product analytics | PostHog |

*(Full technical stack details are documented separately for engineering audiences; this summary is intentionally simplified.)*

---

## 8. Known Gaps, Legacy Bits & Things to Double-Check

These are honest notes from reading the actual code — useful context so nobody assumes something works differently than it does:

- The publicly-linked `/mock-test` page is not a real page — it just redirects visitors to `/practice/mock`, kept alive so old links/bookmarks still work.
- A few backend endpoints (a generic "questions" endpoint, and an old generic "submit test" endpoint) look like earlier, now-unused versions of features that Reading/Listening/Writing/Speaking each now handle with their own dedicated, more specific logic.
- The Mock Test's final Speaking score is currently just a simple average of the two roleplay scores — the code itself notes this could later be upgraded to a smarter combined AI re-score if more precision is needed.
- The Listening admin content-upload tool does not yet have the same "recover a partially-failed large PDF upload" safety net that the Reading tool has — if a very large listening paper fails partway through processing, an admin currently has to retry one section at a time.
- The AI voice model used for the Gemini option is a "preview" (not final/stable) model as of this writing.
- The old `README.md` file in the repo claims Reading, Listening, and the full Mock Test are "not yet built" — this is **out of date**. All three exist and work in the current code. This documentation reflects the current code, not that old note.

---

## Founder Information Needed

Information that only the founder (or another business owner) can provide, since it isn't in the codebase:

- Company mission and vision statements (not written down anywhere in the repo)
- Legal company name, registration/incorporation details
- Whether/when the company plans to register for GST
- Team and founder background information
- Target launch date and current real user/revenue numbers
- Official brand voice, tone, and visual identity guidelines (none formally documented yet)
- Accessibility (WCAG) compliance target
- Final scope and timeline for anything still marked "open" internally — e.g., how complete Reading/Listening/Vocab content is expected to be at launch
- Purpose of the `agent/`, `scripts/`, and `studio/` folders in the repository (present but undocumented)
- Any customer support policies, refund policy wording, or SLA commitments not visible in code

---

## Repository Files Used

**Backend routers** (`backend/app/routers/`): `auth.py`, `speaking.py`, `speaking_realtime.py`, `writing.py`, `reading.py`, `listening.py`, `mock.py`, `vocab.py`, `hub.py`, `scoring.py`, `progress.py`, `payments.py`, `admin.py`, `onboarding.py`, `profile.py`, `plans.py`, `sessions.py`, `submissions.py`, `questions.py`, `grammar.py`, `comparison.py`, `scenario_generator.py`, `leads.py`, `referrals.py`, `tools.py`

**Backend schemas/config**: `backend/app/schemas/user.py`, `backend/app/schemas/onboarding.py`, `backend/app/core/config.py`, `backend/app/core/plans.py`, `backend/app/services/plan_gating.py`

**Frontend** (`frontend/app/`): `page.tsx`, `dashboard/page.tsx`, `hub/page.tsx`, `onboarding/page.tsx`, `upgrade/page.tsx`, `admin/page.tsx`, `admin/settings/page.tsx`, `mock-test/page.tsx`, `sessions/[id]/page.tsx`, `oet/india/page.tsx`, `practice/mock/page.tsx`, `refer/page.tsx`, `blog/[slug]/page.tsx`, `pricing/page.tsx`, plus directory listings of `practice/`, `auth/`, `admin/`, `docs/`, `learn/`, `oet/`, `tools/` subfolders

**Site/config**: `frontend/src/lib/site.ts`

**Top-level docs**: `README.md`, `PRODUCT.md`
