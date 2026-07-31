# SpeakOET — SEO & Organic Growth Master Plan

**Prepared:** 2026-07-26
**Domain:** https://www.speakoet.com (new, low authority)
**Goal:** 4,000+ paying subscribers, built on a defensible organic moat.

This plan is written against the **actual repository**, not a generic template. Every technical
finding below was verified in `frontend/app/` on 2026-07-26.

---

## Documents

| # | Document | What it answers |
|---|---|---|
| 01 | [Technical SEO Audit](01-audit.md) | Every issue to check, verified findings, fixes, priority |
| 02 | [Topical Authority Map](02-topical-map.md) | 300+ page ideas as pillar → support → FAQ → tool → landing |
| 03 | [Programmatic SEO Strategy](03-programmatic.md) | Auto-generated page templates + volume estimate |
| 04 | [AI Search Optimisation (AEO/GEO)](04-aeo-geo.md) | ChatGPT / Gemini / Claude / Perplexity / AI Overviews |
| 05 | [Technical Roadmap — Weeks 1–4](05-technical-roadmap.md) | Copy-paste GitHub issues with acceptance criteria |
| 06 | [12-Month Content Roadmap](06-content-calendar.md) | Weekly publishing plan, ranked by traffic × conversion |
| 07 | [Digital PR & Link Strategy](07-digital-pr.md) | Realistic, non-spammy backlink acquisition |
| 08 | [Competitor Analysis](08-competitors.md) | OET Official, E2Language, Swoosh, Benchmark, OET Online |
| 09 | [Conversion-Focused SEO](09-conversion.md) | CTA / lead magnet / internal-link spec per page type |
| 10 | [KPIs & Targets](10-kpis.md) | 30 / 90 / 180 / 365-day measurable targets |
| 11 | [Prioritised Backlog](11-backlog.md) | P0 → P3 with impact, effort, dependencies, ROI |

---

## Where SpeakOET actually stands today (verified)

**What already exists and works:**
- `app/robots.ts` — correct, blocks app routes, points at sitemap.
- `app/sitemap.ts` — exists, covers static + `/learn` + `/docs`.
- `app/layout.tsx` — `metadataBase`, title template, OpenGraph, Twitter card, `Organization` JSON-LD.
- `app/opengraph-image.tsx` — dynamic OG image.
- 5 hand-written `/learn` articles with per-page canonicals and a table of contents.
- 5 `/docs` guides.
- Sanity-backed blog at `/blog` and `/blog/[slug]` (live, `revalidate = 60`).
- Referral program (`/refer`) — a compounding loop most competitors do not have.

**Verified live on 2026-07-26 — one piece of good news first:**

`/`, `/learn/oet-band-scores` and `/blog` all return **full server-rendered HTML** with body text
present. The most expensive item on the roadmap is already correct, which means GPTBot, ClaudeBot
and PerplexityBot can read you. That saves ~8 hours and removes the biggest risk from this plan.
`/sitemap.xml` returns 18 URLs; `robots.txt` is live and well-formed.

**The eight things that are actually costing you money right now:**

1. **Sanity blog posts are missing from the sitemap.** `app/sitemap.ts:7-22` builds from
   `learnArticles` and `docsGuides` only. Live sitemap = 18 URLs (8 static + 5 learn + 5 docs),
   and `/blog` currently lists zero posts — so **nothing is lost yet**. The bug is latent and it
   fires on your first CMS post, which is week 1. Fix it now: 2 hours, and it is the single
   highest-ROI line of code in the repo.
2. **No public pricing page.** `/upgrade` is `Disallow`ed in `robots.ts:9` (confirmed live).
   "OET preparation price/cost" is bottom-funnel commercial intent and you are not competing for
   it at all.
3. **No `Article` / `FAQPage` / `SoftwareApplication` / `BreadcrumbList` schema.** Only
   `Organization` exists. You are giving up rich results and — more importantly in 2026 — the
   structured chunks that AI answer engines prefer to cite.
4. **Content volume is ~11 indexable pages.** Competitors have 400–3,000. You cannot win topical
   authority from 11 pages regardless of how good they are.
5. **`/learn` articles are hard-coded `.tsx` files.** Every new article is a code deploy. This
   caps publishing velocity at exactly the moment velocity is the whole game.
6. **Zero programmatic surface.** Your product generates role-plays, sample letters and scored
   feedback. None of that is exposed as indexable pages. This is your unfair advantage and it is
   currently switched off.
7. **No country/regulator landing pages.** Every OET nurse searches "OET score for NMC",
   "OET for AHPRA", "OET for Philippines nurses". These are the highest-conversion queries in
   the entire niche.
8. **No free tool.** Free tools are the cheapest links, the cheapest emails, and the cheapest
   AI-search citations in education.

---

## The founder-level honest math

You asked for 4,000 paying subscribers "as quickly as possible". Here is the arithmetic rather
than the pitch.

Assume a realistic funnel for a high-intent, deadline-driven exam product:

| Step | Rate | Why this number |
|---|---|---|
| Organic visitor → free signup | 6–9% | Exam prep converts far above generic SaaS; the visitor has a booked test date |
| Free signup → paying | 6–10% | Deadline pressure + score anxiety; higher than the 2–4% SaaS norm |
| **Visitor → paying** | **~0.5–0.8%** | Compound of the above |

To reach 4,000 paying customers **from organic alone** you need roughly **550,000–800,000
cumulative organic sessions**. On a brand-new domain that is not a 12-month outcome from content
alone. A realistic organic-only trajectory is **1,200–1,900 paying subscribers by month 12**,
with month 12 exit-rate high enough to hit 4,000 somewhere in **month 16–20**.

**So the plan does not rely on SEO alone.** It stacks four compounding loops:

1. **Programmatic SEO** — thousands of long-tail pages that each contain a real, playable
   product asset (see [03](03-programmatic.md)). This is the volume engine.
2. **Free tools** — band-score calculator, referral-letter checker, OET readiness quiz. These
   earn links, emails and AI citations that articles never will.
3. **The referral loop you already built** — every paying nurse in a WhatsApp cohort of 40
   colleagues is a distribution channel. SEO acquires the seed; referral multiplies it.
4. **YouTube + Instagram** (accounts already exist per `layout.tsx:44-48`) — OET is a
   *performance* skill; video demonstrably outconverts text, and YouTube is itself the second
   search engine and a heavy AI-Overview citation source.

Weight of contribution to the 4,000 by month 12–14: SEO ~45%, referral ~25%, social/video ~20%,
paid/partnerships ~10%. SEO is the largest single channel and the only one that compounds
without ongoing spend — which is why it gets the biggest investment. But planning as though it
is the *only* channel is how founders miss the number.

---

## The moat, in one paragraph

Every competitor sells OET content. Content is copyable. What is not copyable is
**a page that contains a working AI role-play for the exact specialty a nurse searched for,
graded against the real OET criteria, with the transcript and score visible before signup.**
That is a page a blogger cannot write and an LLM cannot fabricate. Build 2,000 of those and you
own the long tail structurally, not editorially. Everything in this plan points at that outcome.

---

## Order of operations (if you read nothing else)

**Weeks 1–4:** fix the technical foundation ([05](05-technical-roadmap.md)) — sitemap, schema,
CMS-driven content, public pricing page, country pages. Nothing else matters until crawl and
indexation are clean.

**Weeks 5–12:** ship the first programmatic template (role-plays by specialty) + first free tool
+ 2 articles/week. Target: 400 indexable pages by end of month 3.

**Months 4–8:** scale programmatic to ~1,500 pages under quality gates, launch digital PR,
build the comparison and country clusters.

**Months 9–12:** consolidate — prune what didn't index, double down on what converts, push
authority via PR and partnerships.
