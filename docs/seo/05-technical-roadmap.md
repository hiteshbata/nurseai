# 05 — Technical SEO Roadmap: Weeks 1–4

Copy-paste ready GitHub issues. File paths are real and verified against the repo.
Effort is in engineer-hours. `S` ≤ 2h · `M` = 2–8h · `L` = 8–24h · `XL` > 24h.

**Week themes:** 1 = stop the bleeding · 2 = make content indexable and semantic ·
3 = build the money pages · 4 = build the publishing machine.

---

# WEEK 1 — Foundation (stop the bleeding)

## Issue #1 — Add Sanity blog posts to the sitemap
**Labels:** `seo`, `P0`, `bug`

**Description**
`app/sitemap.ts` builds only from the static array, `learnArticles` and `docsGuides`. Every post
published through Sanity and rendered by `app/blog/[slug]/page.tsx` is absent from
`/sitemap.xml`. On a domain with near-zero external links, the sitemap is Google's main discovery
path, so every CMS post is taking weeks longer to index than it should.

Also fix `lastModified`: it is currently `new Date()` on every entry (`sitemap.ts:9,14,19`), which
tells Google every page changed on every deploy. Google learns to ignore the field entirely.

**Acceptance Criteria**
- [ ] `sitemap.ts` is `async` and fetches all published slugs + `_updatedAt` from Sanity
- [ ] `/sitemap.xml` contains one `<url>` per published blog post
- [ ] `lastModified` uses `_updatedAt` for blog posts, and a new explicit `updated` field on
      `LearnArticle` / `DocsGuide` for hand-written pages
- [ ] Draft/unpublished Sanity documents are excluded
- [ ] Sitemap generation does not fail the build if Sanity is unreachable (fall back to static
      routes, log the error)
- [ ] Sitemap resubmitted in Google Search Console **and Bing Webmaster Tools**

**Effort:** S (2h) · **Priority:** P0

---

## Issue #2 — Public, indexable pricing page
**Labels:** `seo`, `P0`, `conversion`

**Description**
`app/robots.ts:9` disallows `/upgrade`, which is the only page describing what SpeakOET costs.
"OET preparation cost", "OET practice price", "cheapest OET coaching online" are bottom-funnel
queries with buying intent and we are excluded from all of them. Competitors rank for these.

Create a public marketing `/pricing` route. Keep `/upgrade` as the authenticated checkout flow and
keep it disallowed.

**Acceptance Criteria**
- [ ] `app/pricing/page.tsx` exists, server-rendered, no auth dependency
- [ ] Shows every plan, price in INR **and** USD (auto-detect by region, allow manual switch),
      full feature comparison table as HTML
- [ ] `SoftwareApplication` + `Offer` JSON-LD with real prices
- [ ] 8 pricing FAQs with `FAQPage` schema (refunds, plan switching, free tier limits, currency)
- [ ] `/pricing` removed from any disallow rule; present in sitemap
- [ ] Primary CTA "Start free" → signup; secondary "Try a free mock test" → `/tools/oet-mock-test-free`
- [ ] `curl -s https://www.speakoet.com/pricing | grep -c "₹"` returns ≥1 (proves SSR)

**Effort:** M (6h) · **Priority:** P0

---

## Issue #3 — Lock in server-side rendering with a CI assertion
**Labels:** `seo`, `P1`, `ci`

**Description**
**Checked live 2026-07-26: this already passes.** `/`, `/learn/oet-band-scores` and `/blog` all
return full server-rendered HTML with `<h1>` and body text present, so GPTBot, ClaudeBot and
PerplexityBot — none of which execute JavaScript — can read the site today. The original 4–8h fix
is not needed.

What *is* needed is a guard. `Providers` wraps everything at `app/layout.tsx:68-70`. A future
refactor that makes it auth-dependent would silently make every marketing page invisible to AI
crawlers, with no error and no alert. Assert it in CI so that cannot happen quietly.

**Acceptance Criteria**
- [ ] CI step fetches `/`, `/pricing`, `/learn/oet-band-scores` and one blog post from the preview
      deployment and asserts a known body phrase is present in the raw HTML
- [ ] The step fails the build (not just warns) when the phrase is missing
- [ ] Documented in `docs/seo/` so the next engineer knows why the check exists

**Separate, lower-priority follow-up (rolled into Issue #11):** marketing routes still ship the
auth provider's JavaScript even though they render server-side. Moving `Providers` into an `(app)`
route group is now an INP/TBT optimisation, not an indexability fix.

**Effort:** S (1h) · **Priority:** P1

---

## Issue #4 — Restructure robots.ts: named AI crawlers + non-greedy disallows
**Labels:** `seo`, `P0`

**Description**
Single `*` rule today. Two problems: (a) `/practice` is disallowed by prefix, which will silently
kill the programmatic role-play pages planned for week 6; (b) no explicit AI-crawler policy.

**Acceptance Criteria**
- [ ] Disallows are specific, not prefix-greedy: `/practice/session`, `/practice/live` instead of
      `/practice`
- [ ] All future public programmatic pages live under `/oet/*`, which is never disallowed
- [ ] Named `allow` rules for `GPTBot`, `OAI-SearchBot`, `ChatGPT-User`, `ClaudeBot`,
      `Claude-User`, `PerplexityBot`, `Google-Extended`, `Applebot-Extended`, `Bingbot`
- [ ] `/upgrade`, `/dashboard`, `/profile`, `/onboarding`, `/admin`, `/auth` remain disallowed
- [ ] `/robots.txt` manually reviewed after deploy; Search Console robots tester shows `/pricing`
      and `/oet/` as allowed

**Effort:** S (1h) · **Priority:** P0

---

## Issue #5 — Noindex all non-production hosts
**Labels:** `seo`, `P1`

**Description**
Vercel preview deployments can be indexed and will duplicate production content.

**Acceptance Criteria**
- [ ] `middleware.ts` sets `X-Robots-Tag: noindex, nofollow` when host ≠ `www.speakoet.com`
- [ ] `curl -I https://<preview>.vercel.app` shows the header
- [ ] Production responses do **not** carry the header (verify explicitly — this is the
      dangerous failure mode)
- [ ] `site:vercel.app speakoet` returns nothing after 2 weeks

**Effort:** S (1h) · **Priority:** P1

---

## Issue #6 — Fix the root canonical inheritance landmine
**Labels:** `seo`, `P1`, `tech-debt`

**Description**
`app/layout.tsx:19-21` sets `alternates.canonical: '/'`. Any child route that forgets its own
canonical inherits it, self-canonicalises to the homepage, and drops out of the index. Silent
failure, no error. Guaranteed to bite once content velocity increases.

**Acceptance Criteria**
- [ ] Root canonical removed from `layout.tsx`; homepage sets its own in `app/page.tsx`
- [ ] `lib/seo.ts` exports `buildMetadata({ path, title, description, ... })` with `path`
      **required** by the type signature
- [ ] All existing pages migrated to `buildMetadata`
- [ ] `openGraph.url` is per-page, not hard-coded to `SITE_URL` (currently `layout.tsx:24`)
- [ ] Crawl confirms zero non-homepage pages canonicalising to `/`

**Effort:** M (3h) · **Priority:** P1

---

## Issue #7 — Rewrite the homepage title and description
**Labels:** `seo`, `P1`, `content`

**Description**
`layout.tsx:14` — `SpeakOET — OET Speaking Practice for Nurses`. The product covers Speaking,
Writing, Reading, Listening, mock tests, pronunciation and study plans. The title claims one of
seven, excluding us from head terms and — more damagingly — training every LLM that SpeakOET is a
speaking-only tool.

**Acceptance Criteria**
- [ ] Title: `SpeakOET — AI OET Practice for Nurses: Speaking, Writing, Reading & Listening`
      (≤ 60 chars visible, verify in a SERP preview tool)
- [ ] `SITE_DESCRIPTION` in `lib/site.ts` updated to name all four sub-tests + mock tests
- [ ] H1 on `/` matches the positioning
- [ ] `keywords` meta deleted from `layout.tsx:18` (ignored since 2009)
- [ ] OG and Twitter titles updated to match

**Effort:** S (1h) · **Priority:** P1

---

# WEEK 2 — Semantics and indexability

## Issue #8 — Structured data system
**Labels:** `seo`, `P0`, `schema`

**Description**
Only `Organization` schema exists (`layout.tsx:36-49`). Missing everything that drives rich
results and AI citation.

**Acceptance Criteria**
- [ ] `lib/schema.ts` with typed builders: `articleSchema`, `faqSchema`, `breadcrumbSchema`,
      `softwareApplicationSchema`, `courseSchema`, `howToSchema`, `videoSchema`, `personSchema`
- [ ] `<JsonLd data={...} />` component replaces the inline `dangerouslySetInnerHTML` block
- [ ] `Article` schema on all `/learn/*` and `/blog/[slug]` with `author` (`Person` +
      `jobTitle`), `datePublished`, `dateModified`, `publisher`
- [ ] `BreadcrumbList` on every nested route
- [ ] `FAQPage` on every page with an FAQ block
- [ ] `Organization` upgraded to `EducationalOrganization` with `knowsAbout` and `foundingDate`
- [ ] Every template validates clean in Rich Results Test + Schema Markup Validator
- [ ] Search Console → Enhancements shows zero errors after 2 weeks

**Effort:** L (10h) · **Priority:** P0

---

## Issue #9 — Segmented sitemaps
**Labels:** `seo`, `P1`

**Description**
One flat sitemap makes it impossible to diagnose which content type is failing to index — a
problem that becomes acute at 1,000+ programmatic pages.

**Acceptance Criteria**
- [ ] `generateSitemaps()` emits: `marketing`, `learn`, `blog`, `tools`, `countries`
      (+ `roleplays`, `letters` stubs ready for week 6)
- [ ] `/sitemap.xml` is a valid sitemap index referencing all children
- [ ] Each child submitted separately in Search Console and Bing Webmaster Tools
- [ ] Only `indexable = true` pages appear

**Effort:** M (4h) · **Priority:** P1

---

## Issue #10 — Internal linking system
**Labels:** `seo`, `P0`, `content`

**Description**
No sibling linking, no pillar structure, no breadcrumbs. With almost no backlinks, internal links
are ~90% of the authority reaching any page. Highest leverage per hour of any item in this
roadmap.

**Acceptance Criteria**
- [ ] `<Breadcrumbs />` component on all nested routes, with `BreadcrumbList` schema
- [ ] `<RelatedContent />` renders 3 tag-matched siblings; used on every article
- [ ] `tags: string[]` added to `LearnArticle`, `DocsGuide`, and the Sanity post schema
- [ ] Every article links: 1× up to its pillar, 3× sideways, 1× to a conversion page — enforced
      by a lint rule or a CI check, not by memory
- [ ] Footer trimmed to ≤ 25 links
- [ ] Crawl confirms every indexable page has ≥ 3 internal inlinks

**Effort:** L (10h) · **Priority:** P0

---

## Issue #11 — Core Web Vitals pass
**Labels:** `seo`, `P1`, `performance`

**Description**
Audience is mid-range Android on 4G in India, the Philippines and Nigeria. Desktop Lighthouse
scores are misleading here.

**Acceptance Criteria**
- [ ] All `<img>` replaced with `next/image`; explicit dimensions everywhere
      (`grep -rn "<img" frontend/app frontend/components` returns 0)
- [ ] Hero/LCP image has `priority`; AVIF+WebP enabled in `next.config`
- [ ] Fonts via `next/font`, self-hosted, `display: swap`
- [ ] PostHog / GA / Clarity loaded with `next/script strategy="lazyOnload"`; Clarity confirmed
      dormant or removed
- [ ] Mobile PageSpeed ≥ 90 on `/`, `/pricing`, one article
- [ ] LCP < 2.0s, CLS < 0.1, INP < 200ms in a throttled "Slow 4G / Moto G4" DevTools profile
- [ ] Vercel Speed Insights baseline recorded so regressions are visible

**Effort:** L (10h) · **Priority:** P1

---

## Issue #12 — Redirect and canonical host hygiene
**Labels:** `seo`, `P1`

**Acceptance Criteria**
- [ ] `speakoet.com` → `www.speakoet.com` in one 301 hop
- [ ] `http://` → `https://` in one 301 hop (no chains)
- [ ] Trailing-slash behaviour consistent and enforced in `next.config`
- [ ] Referral URLs (`/refer?ref=xyz`) self-canonicalise to the clean URL
- [ ] UTM-tagged URLs canonicalise to the clean URL
- [ ] `redirects()` map created in `next.config.js` as the permanent home for all future 301s

**Effort:** S (2h) · **Priority:** P1

---

## Issue #13 — Analytics and Search Console instrumentation
**Labels:** `seo`, `P1`, `analytics`

**Acceptance Criteria**
- [ ] Bing Webmaster Tools property verified, sitemap submitted
- [ ] Search Console: both www and non-www properties verified; domain property preferred
- [ ] PostHog custom channel group for AI referrers: `chatgpt.com`, `perplexity.ai`,
      `claude.ai`, `gemini.google.com`, `copilot.microsoft.com`
- [ ] Conversion events defined: `signup`, `first_practice_completed`, `checkout_started`,
      `subscription_started` — each attributable to landing page and channel
- [ ] A weekly Looker Studio (or PostHog) dashboard: organic sessions → signups → paid, by
      landing page

**Effort:** M (5h) · **Priority:** P1

---

# WEEK 3 — Money pages

## Issue #14 — Country and regulator landing pages (batch 1)
**Labels:** `seo`, `P0`, `content`

**Description**
The highest-conversion query cluster in OET: a nurse searching "OET score for NMC" has a test date
and a decision. We currently have one such page (`/learn/oet-for-indian-nurses`).

**Acceptance Criteria**
- [ ] 8 pages live: `/oet/uk`, `/oet/australia`, `/oet/ireland`, `/oet/new-zealand`,
      `/oet/canada`, `/oet/india`, `/oet/philippines`, `/oet/uae`
- [ ] Each: exact score requirement, regulator name + official link, score-combining rules,
      validity period, fee in local currency, full post-OET registration pathway
- [ ] Answer-first: the required score appears in the first 50 words, in bold
- [ ] `FAQPage` + `BreadcrumbList` schema on each
- [ ] Visible "Verified against [official source], July 2026" line
- [ ] Each links to `/pricing`, the relevant practice landing, and 3 sibling countries
- [ ] `/learn/oet-for-indian-nurses` 301s to `/oet/india`
- [ ] **Every requirement fact checked against the regulator's own site by a human before merge**

**Effort:** L (16h incl. research) · **Priority:** P0

---

## Issue #15 — Free tool: OET score calculator
**Labels:** `seo`, `P0`, `growth`

**Description**
Highest-volume, most-linkable tool in the niche. Nursing schools and forums link to calculators;
they do not link to blog posts.

**Acceptance Criteria**
- [ ] `/tools/oet-score-calculator` — enter raw Listening/Reading scores and Writing/Speaking
      grades → band, numeric score, and pass/fail against each of 8 regulators
- [ ] Works with no signup; result shareable via URL
- [ ] Result page CTA: "Your Writing is your weakest area — practise it free" → targeted signup
- [ ] Email capture *after* the result is shown, offering a personalised study plan
- [ ] `SoftwareApplication` + `FAQPage` schema
- [ ] Server-rendered shell so the explanatory content is crawlable even though the calculator
      is interactive
- [ ] Embeddable widget with an attribution backlink (`<iframe>` + copy-paste snippet)

**Effort:** M (8h) · **Priority:** P0

---

## Issue #16 — Free tool: full mock test, no signup
**Labels:** `seo`, `P0`, `growth`, `conversion`

**Description**
The mock test product already exists and is verified working. Exposing one free scored test at a
public URL is the single strongest conversion asset available — it demonstrates the product
instead of describing it.

**Acceptance Criteria**
- [ ] `/tools/oet-mock-test-free` — one complete 4-skill mock, playable with no account
- [ ] Sub-test scores shown free; **the full band report and per-criterion feedback require a
      free account** (this is the email capture)
- [ ] Abuse-limited by IP/fingerprint so it does not become an unmetered AI-cost sink
- [ ] Rate-limited and cost-capped on the AI calls (reuse existing rate-limit middleware)
- [ ] Landing content above the widget is server-rendered and targets
      "free OET mock test online"
- [ ] Post-test CTA: "Get your full band report" → signup → immediate upgrade prompt

**Effort:** L (12h) · **Priority:** P0

---

## Issue #17 — Product landing pages (batch 1)
**Labels:** `seo`, `P1`, `conversion`

**Acceptance Criteria**
- [ ] 4 pages: `/oet-speaking-practice`, `/oet-writing-correction`, `/oet-mock-test`,
      `/oet-practice-online`
- [ ] Each: H1 with the head term, live product demo or embedded GIF/video, 3 real testimonials,
      feature grid, pricing block, 6 FAQs with schema
- [ ] Each links to its pillar, 3 supporting articles, `/pricing`, and the relevant free tool
- [ ] Real product screenshots with descriptive alt text
- [ ] Mobile Lighthouse ≥ 90

**Effort:** L (12h) · **Priority:** P1

---

## Issue #18 — Rewrite the 5 existing `/learn` articles to answer-first format
**Labels:** `seo`, `P1`, `content`

**Description**
The 5 existing articles are decent but written as prose essays. Restructure for passage retrieval:
question-shaped H2s, 40–60 word direct answers, bold key facts, FAQ blocks.

**Acceptance Criteria**
- [ ] All 5 restructured: `what-is-oet-speaking`, `oet-band-scores`, `oet-vs-ielts`,
      `oet-speaking-tips`, `oet-for-indian-nurses`
- [ ] Each opens with a 40–60 word direct answer to its title question
- [ ] Each has 6+ FAQs with `FAQPage` schema
- [ ] Each expanded to 1,800+ words with genuinely new depth (not padding)
- [ ] Each has a visible "Last updated" date and named author with `Person` schema
- [ ] Each links up to a pillar, sideways to 3 siblings, and to 1 conversion page
- [ ] `oet-vs-ielts` gains a full HTML comparison table (no image)

**Effort:** L (12h) · **Priority:** P1

---

# WEEK 4 — The publishing machine

## Issue #19 — Migrate `/learn` from hard-coded TSX to the CMS
**Labels:** `seo`, `P0`, `tech-debt`, `velocity`

**Description**
`app/learn/articles.ts` plus one `.tsx` file per article means every new article is a code change,
a PR and a deploy. At 2 articles/week for 12 months that is ~100 deploys of pure content and a
hard ceiling on velocity at exactly the moment velocity is the strategy. Two parallel content
systems (`/learn` hard-coded, `/blog` from Sanity) also compete for the same queries — see
[01, N2](01-audit.md).

**Acceptance Criteria**
- [ ] Sanity schema for `learnArticle`: title, slug, excerpt, body (portable text), tags, author
      ref, publishedAt, updatedAt, faqs[], canonical override, `indexable` bool
- [ ] `app/learn/[slug]/page.tsx` renders from Sanity
- [ ] All 5 existing articles migrated with **URLs unchanged**
- [ ] Hard-coded `app/learn/*/page.tsx` files and `articles.ts` deleted
- [ ] `/blog` repositioned as news/updates; `/learn` as evergreen education; cross-links updated
- [ ] Sanity webhook → `revalidateTag()` for instant publish; `revalidate` on `/blog` raised from
      60 to 3600
- [ ] A non-engineer can publish an article end-to-end with no deploy — **verified by the founder
      actually doing it once**

**Effort:** L (16h) · **Priority:** P0

---

## Issue #20 — Programmatic page infrastructure
**Labels:** `seo`, `P0`, `growth`

**Description**
Scaffolding for [03](03-programmatic.md). Ship the plumbing in week 4 so content generation can
start in week 5.

**Acceptance Criteria**
- [ ] Supabase table `seo_pages`: `slug`, `template`, `dimensions jsonb`, `content jsonb`,
      `indexable bool`, `word_count int`, `created_at`, `updated_at`
- [ ] `isIndexable()` predicate enforcing the [03](03-programmatic.md) quality gate; pages failing
      it get `robots: { index: false, follow: true }` and are excluded from the sitemap
- [ ] `app/oet/speaking/role-play/[specialty]/[scenario]/page.tsx` renders from `seo_pages`
- [ ] ISR with `dynamicParams: true`; top 200 pre-rendered via `generateStaticParams`
- [ ] Auto-generated internal links: up to hub, 4 siblings, 1 conversion page
- [ ] Template-segmented sitemap wired to `WHERE indexable = true`
- [ ] PostHog property `seo_template` on pageviews so per-template conversion is measurable
- [ ] 10 pilot pages live and manually reviewed for quality before any batch generation

**Effort:** XL (24h) · **Priority:** P0

---

## Issue #21 — `llms.txt` and AI-crawler monitoring
**Labels:** `seo`, `P1`, `aeo`

**Acceptance Criteria**
- [ ] `/public/llms.txt` generated from the CMS at build time, listing core guides and tools
- [ ] `/llms-full.txt` with full Markdown of the top 20 pages
- [ ] Weekly report of GPTBot / ClaudeBot / PerplexityBot / OAI-SearchBot hits from Vercel logs
- [ ] Monthly 25-prompt AI panel documented as a recurring task with a results spreadsheet

**Effort:** M (5h) · **Priority:** P1

---

## Issue #22 — 404, orphan and broken-link sweep
**Labels:** `seo`, `P2`

**Acceptance Criteria**
- [ ] Full Screaming Frog crawl; zero internal 4xx/5xx
- [ ] Zero pages with fewer than 3 internal inlinks
- [ ] Zero duplicate titles or meta descriptions
- [ ] `not-found.tsx` upgraded: search box, top 6 articles, link to `/pricing`
- [ ] Crawl checklist saved to `docs/seo/` as a repeatable monthly task

**Effort:** M (4h) · **Priority:** P2

---

## Issue #23 — Per-page OG images
**Labels:** `seo`, `P2`, `growth`

**Description**
Indian and Filipino nursing communities share links primarily on WhatsApp. Preview quality is a
distribution feature, not a vanity one.

**Acceptance Criteria**
- [ ] `opengraph-image.tsx` per route segment, rendering the page title over brand template
- [ ] `openGraph.url` per page (currently hard-coded at `layout.tsx:24`)
- [ ] `twitter:site` / `twitter:creator` added
- [ ] Verified in the WhatsApp, LinkedIn and X preview debuggers

**Effort:** M (4h) · **Priority:** P2

---

## Week-by-week effort summary

| Week | Issues | Hours | Theme |
|---|---|---|---|
| 1 | #1–#7 | ~18h | Stop the bleeding (#3 dropped from 4–8h to 1h — SSR already passes) |
| 2 | #8–#13 | ~35h | Semantics + indexability |
| 3 | #14–#18 | ~60h | Money pages |
| 4 | #19–#23 | ~53h | Publishing machine |
| | | **~166h** | ≈ 4 focused engineer-weeks |

If it is one part-time engineer, this is 8–10 calendar weeks. **Do not reorder to do the easy
items first.** #1, #3, #14 and #16 carry most of the value; everything else is support.
