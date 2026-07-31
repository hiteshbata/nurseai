# 01 — Technical SEO Audit

Verified against the repository on 2026-07-26. Findings marked **[VERIFIED]** were confirmed in
code. Findings marked **[CHECK]** are the standard failure modes of a Next.js App Router SaaS on
Vercel that you must test on the live site.

Priority key: **P0 Critical** (costing traffic today) · **P1 High** (blocks growth within 30 days)
· **P2 Medium** · **P3 Low**.

---

## A. Indexability

### A1. Sanity blog posts are excluded from the sitemap — **P0 Critical (latent)** [VERIFIED LIVE]

**Finding.** `app/sitemap.ts:7-22` composes the sitemap from three sources: a hard-coded static
array, `learnArticles`, and `docsGuides`. `app/blog/[slug]/page.tsx` renders posts from Sanity
(`getBlogPosts()` in `app/blog/page.tsx:4`), and none of them appear in `/sitemap.xml`.

**Live check, 2026-07-26.** `/sitemap.xml` returns exactly **18 URLs** — 8 static + 5 `/learn` +
5 `/docs`. `/blog` renders **zero** `/blog/<slug>` links, so Sanity currently has no published
posts. **Nothing is being lost today.** The bug is latent, and it fires the moment you publish
your first CMS post — which under [06](06-content-calendar.md) is week 1.

**Why it still matters, and why it is still P0.** On a new domain with almost no external links,
the XML sitemap is Google's primary discovery mechanism. Fixing this *before* content starts
means every post is discoverable from the hour it publishes. Fixing it after 20 posts means 20
posts spent 3–6 weeks each in discovery limbo for no reason. Cost to fix now: 2 hours. Cost to
fix later: the same 2 hours plus a month of lost ranking runway.

**How to verify.**
```bash
curl -sL https://www.speakoet.com/sitemap.xml | grep -c "<loc>"   # 18 as of 2026-07-26
curl -sL https://www.speakoet.com/blog | grep -o 'href="/blog/[^"]*"' | sort -u
```
The second count must equal the number of `/blog/` entries in the sitemap. Then Search Console →
Pages → watch for blog URLs under "Discovered – currently not indexed".

**How to fix.** Make `sitemap.ts` `async`, pull slugs and `_updatedAt` from Sanity, and emit real
`lastModified` values. Details and acceptance criteria in [05 — Issue #1](05-technical-roadmap.md).

---

### A2. Robots disallow list will block future money pages — **P0 Critical** [VERIFIED]

**Finding.** `app/robots.ts:9` disallows `/dashboard`, `/practice`, `/mock-test`, `/profile`,
`/onboarding`, `/upgrade`, `/admin`, `/auth`.

Blocking the authenticated app is correct. Two entries are strategically wrong:

- **`/upgrade`** is your pricing surface. "OET preparation cost", "OET practice test price",
  "cheapest OET coaching" are bottom-funnel, high-conversion queries and you are excluded from
  all of them.
- **`/practice`** will collide with programmatic SEO. The moment you publish
  `/practice/speaking/role-play/cardiology` as a public preview page (the core of
  [03](03-programmatic.md)), this rule silently blocks your entire growth engine — and prefix
  matching means you will not get an error, just zero traffic.

**Why it matters.** A `Disallow` on a page that later becomes public is the most expensive kind of
SEO bug because it is invisible: no 404, no error, no alert. Traffic simply never arrives.

**How to verify.** `curl https://www.speakoet.com/robots.txt`. Then Search Console → URL
Inspection on `/upgrade` → expect "Blocked by robots.txt".

**How to fix.** Create a public marketing `/pricing` route (indexable) and keep `/upgrade` as the
authenticated checkout flow. Restructure disallows to be *specific* rather than prefix-greedy:
disallow `/practice/session`, `/practice/live`, not `/practice`. Move all programmatic public
pages under a namespace that is never disallowed — recommended: `/oet/…`.

---

### A3. Noindex leakage and staging exposure — **P1 High** [CHECK]

**Why it matters.** Vercel preview deployments (`*.vercel.app`) can be indexed and will compete
with production, splitting authority and creating exact-duplicate content on a domain that has
none to spare.

**How to verify.** `site:vercel.app speakoet` in Google. Also
`curl -I https://<preview>.vercel.app` and look for `X-Robots-Tag`.

**How to fix.** In `middleware.ts` (or `next.config`), add `X-Robots-Tag: noindex` for any host
that is not `www.speakoet.com`. One conditional, ~5 lines.

---

### A4. Soft-404s from empty states — **P2 Medium** [CHECK]

**Why it matters.** Programmatic pages with no content (a specialty with zero scenarios yet) that
return HTTP 200 with an empty shell are classified as soft-404s. Enough of them and Google
throttles crawl budget for the whole pattern — poisoning the pages that *do* have content.

**How to verify.** Search Console → Pages → "Soft 404". Also spot-check any dynamic route with a
nonsense slug: `/blog/asdkjhasd` should return a true 404, not a 200 shell.

**How to fix.** In dynamic routes, call `notFound()` when the data fetch is empty, and gate
programmatic page generation on a minimum content threshold (see [03](03-programmatic.md),
"Quality gate").

---

## B. Crawlability

### B1. Crawl budget wasted on app routes — **P2 Medium** [VERIFIED, mitigated]

Already handled by `robots.ts`. Keep it that way, but note the fix in A2 must not weaken it.
Authenticated routes must stay out.

### B2. Orphan pages — **P1 High** [VERIFIED]

**Finding.** `/docs` guides appear in the sitemap but I found no evidence of contextual internal
links from `/learn` articles into `/docs` or vice versa. Pages that exist only in the sitemap and
the footer receive almost no PageRank.

**Why it matters.** Internal links are the only authority-distribution lever you fully control.
On a new domain they are worth more than on an established one, because there is so little
external authority to distribute.

**How to verify.** Crawl the site with Screaming Frog (free up to 500 URLs — sufficient today).
Sort by "Inlinks". Anything with fewer than 3 internal inlinks is functionally orphaned.

**How to fix.** Add a `RelatedArticles` component driven by a shared tag field, and require every
new article to link to 3 siblings + 1 pillar + 1 product page. Enforce in the content template,
not by memory.

### B3. Crawl depth — **P2 Medium** [CHECK]

Every money page should be ≤3 clicks from the homepage. Once programmatic pages exist you will
need hub pages (`/oet/speaking/role-plays/`) with paginated or faceted indexes, otherwise page
2,000 sits 8 clicks deep and never gets crawled.

---

## C. Sitemap

### C1. Single monolithic sitemap will break at scale — **P1 High** [VERIFIED]

**Finding.** `app/sitemap.ts` returns one flat array. The protocol limit is 50,000 URLs / 50 MB,
which you will not hit — but the *diagnostic* limit matters far sooner: with one sitemap you
cannot tell which content type is failing to index.

**How to fix.** Use Next.js `generateSitemaps()` to emit segmented sitemaps:
`/sitemap/marketing.xml`, `/sitemap/learn.xml`, `/sitemap/blog.xml`, `/sitemap/roleplays.xml`,
`/sitemap/letters.xml`, `/sitemap/countries.xml`. Submit each separately in Search Console. Now
"blog indexes at 92%, role-plays index at 31%" is a fact you can act on instead of a guess.

### C2. `lastModified: new Date()` is a lie — **P1 High** [VERIFIED]

**Finding.** `app/sitemap.ts:9,14,19` set `lastModified` to the current timestamp on every build.
Every deploy tells Google that every page changed.

**Why it matters.** Google learns that your `lastModified` carries no information and stops using
it. You lose the ability to signal genuine freshness later — precisely when it matters for the
"updated for 2027" content refresh cycle.

**How to fix.** Use the real content timestamp: Sanity `_updatedAt` for blog, an explicit
`updated` field on `LearnArticle` and `DocsGuide` for hand-written pages.

### C3. Missing `changefreq` / `priority` — **P3 Low**

Google ignores both. Skip them. Mentioned only so nobody adds them later thinking it's a gap.

---

## D. robots.txt

Covered in A2. Two additions:

### D1. No AI-crawler policy — **P1 High** [VERIFIED]

**Finding.** `robots.ts` has a single `*` rule. `GPTBot`, `ClaudeBot`, `PerplexityBot`,
`Google-Extended`, `OAI-SearchBot`, `CCBot` are all governed by that one rule.

**Why it matters.** This is a strategic decision, not a technical one, and the default is
currently "allow everything". For SpeakOET that is **the correct choice** — you *want* to be the
source ChatGPT quotes when a nurse asks "how do I prepare for OET speaking". But it should be a
deliberate allow, written explicitly, because an explicit `Allow` for named AI agents also
documents the intent for whoever touches this file next.

**How to fix.** Add named rules allowing `GPTBot`, `OAI-SearchBot`, `ClaudeBot`,
`PerplexityBot`, `Google-Extended` on all public marketing routes, while still disallowing app
routes. See [04 — AEO/GEO](04-aeo-geo.md).

### D2. No `llms.txt` — **P2 Medium**

Not a standard Google honours, but increasingly consumed by AI crawlers and cheap to ship. See
[04](04-aeo-geo.md).

---

## E. Metadata (titles & descriptions)

### E1. Title template is good; homepage title is too narrow — **P1 High** [VERIFIED]

**Finding.** `app/layout.tsx:14` — default title is
`SpeakOET — OET Speaking Practice for Nurses`.

**Why it matters.** The product does Speaking, Writing, Reading, Listening, mock tests,
pronunciation and study plans. The title claims one of seven. You are excluded from head terms
like "OET practice test", "OET mock test online", "OET writing correction" at the exact moment a
searcher scans the SERP. Head-term titles are also what AI engines use to decide *what a brand
is* — you are training every LLM that SpeakOET is a speaking-only tool.

**How to fix.** `SpeakOET — AI OET Practice for Nurses: Speaking, Writing, Reading & Listening`
(66 chars). Keep the speaking emphasis on `/oet/speaking/` pillar pages where it belongs.

### E2. `keywords` meta is dead weight — **P3 Low** [VERIFIED]

`app/layout.tsx:18`. Google has ignored it since 2009. Harmless, but delete it so nobody
maintains it. Zero-risk cleanup.

### E3. No per-page description discipline for programmatic pages — **P1 High**

**Why it matters.** 2,000 pages sharing a templated description is a duplicate-content and
CTR problem simultaneously. Templates must interpolate at least two unique variables
(specialty + scenario type) and ideally a real data point ("847 nurses have practised this
role-play").

**How to verify.** After launch: Screaming Frog → Meta Description → "Duplicate". Target: 0.

---

## F. Canonicals

### F1. Canonicals present on hand-written pages — **P2 Medium** [VERIFIED, partial]

**Finding.** `app/learn/oet-band-scores/page.tsx:12` and `app/blog/page.tsx:12` both set
`alternates.canonical` correctly. Root sets `canonical: '/'` in `layout.tsx:19-21`.

**Risk.** A root-level canonical in the layout is inherited by any child route that does not set
its own. Any new page whose author forgets `alternates` will self-canonicalise to the homepage
and be dropped from the index. This is a landmine that fires silently as the team scales content.

**How to verify.** Crawl → compare `Address` vs `Canonical Link Element 1`. Any page whose
canonical is `https://www.speakoet.com/` and is not the homepage is broken.

**How to fix.** Remove `alternates.canonical` from the root layout, and add a shared
`buildMetadata()` helper in `lib/seo.ts` that *requires* a path argument. Make it impossible to
publish a page without a correct canonical.

### F2. www vs non-www, trailing slash, query params — **P1 High** [CHECK]

`SITE_URL` is `https://www.speakoet.com`. Verify that `speakoet.com` 301s to `www` (single hop),
that `http://` 301s to `https://`, and that `/learn/oet-band-scores/` and
`/learn/oet-band-scores` resolve to one canonical form. Then check UTM-tagged and
`?ref=` referral URLs — your referral program at `/refer` will generate shared links with query
strings, and those must self-canonicalise to the clean URL or you will index thousands of
duplicates.

---

## G. Structured Data

### G1. Only `Organization` schema exists — **P0 Critical** [VERIFIED]

**Finding.** `app/layout.tsx:36-49`. Well-formed, includes `sameAs` for Instagram/YouTube/LinkedIn
— good entity signal. Nothing else exists anywhere.

**Missing, in order of value to SpeakOET:**

| Schema | Where | Value |
|---|---|---|
| `FAQPage` | Every article, every country page, every programmatic page | Highest AI-citation value; LLMs preferentially retrieve Q/A-shaped chunks |
| `Article` / `BlogPosting` | `/learn/*`, `/blog/[slug]` | `author`, `datePublished`, `dateModified` — freshness + E-E-A-T |
| `BreadcrumbList` | All nested routes | SERP breadcrumbs; strongly reinforces site architecture |
| `SoftwareApplication` + `Offer` | `/pricing` | Price and rating in SERP; feeds "how much does X cost" AI answers |
| `Course` | `/oet/…` prep-plan pages | Eligible for course rich results |
| `HowTo` | "How to write an OET referral letter" | Step-by-step retrieval unit |
| `VideoObject` | Any page embedding YouTube | Video thumbnails in SERP |
| `Person` | Author bios | E-E-A-T on a YMYL-adjacent topic (immigration/licensing) |

**Why it matters most for you specifically.** OET advice touches visa, licensing and career
outcomes. Google applies elevated quality scrutiny. Explicit author, credential, and date markup
is the cheapest available E-E-A-T signal, and it is also exactly what determines whether an LLM
treats you as a citable source or as anonymous text.

**How to verify.** Rich Results Test + Schema Markup Validator on one URL per template. Then
Search Console → Enhancements.

**How to fix.** One `<JsonLd>` component, one `lib/schema.ts` with typed builders, applied per
template. See [05 — Issue #3](05-technical-roadmap.md).

### G2. `Organization` should become `EducationalOrganization` — **P2 Medium**

More specific type, plus add `foundingDate`, `areaServed`, and `knowsAbout: ['Occupational
English Test', 'nursing English', 'NMC registration']`. Entity clarity for AI retrieval.

---

## H. Open Graph & Social

### H1. OG is implemented — **P3 Low** [VERIFIED]

`layout.tsx:22-33` plus `app/opengraph-image.tsx`. Correct.

**Two gaps:**
- `openGraph.url` is hard-coded to `SITE_URL` at line 24, so every page shares the homepage URL in
  its OG tag. Should be per-page. **P2**.
- No `twitter:site` / `twitter:creator` handle. **P3**.

### H2. Per-article OG images — **P2 Medium**

Dynamic OG images with the article title rendered on them measurably lift share CTR on WhatsApp
and Facebook — which is where Filipino and Indian nursing communities actually share links. Given
your audience, WhatsApp preview quality is a *distribution* feature, not a vanity one. Use
`opengraph-image.tsx` per route segment.

---

## I. Core Web Vitals

### I1. Client-side auth check on marketing pages — **P1 High** [CHECK]

**Finding.** `app/conditional-layout.tsx` wraps everything, and `Providers` sits above it in
`layout.tsx:68-70`. If either subscribes to Supabase auth state at the root, every marketing page
ships and executes auth JS before paint.

**Why it matters.** INP and LCP on marketing pages. Also: a marketing page that depends on a
client-side session check risks rendering a logged-out shell to the crawler and flashing content
after hydration.

**How to verify.** PageSpeed Insights on `/` and `/learn/oet-band-scores` — field data (CrUX) not
lab. Also: view-source and confirm the article body text is present in raw HTML.

**How to fix.** Keep marketing routes fully static. Move `Providers` down into an
`(app)` route group so it never wraps `/learn`, `/blog`, `/pricing`, `/oet/*`.

### I2. LCP image — **P1 High** [CHECK]

Homepage hero image must use `next/image` with `priority`, explicit `width`/`height`, and modern
format. Target LCP < 2.0s on 4G — your users are on mobile networks in India, the Philippines and
Nigeria, not on fibre.

### I3. Font loading — **P2 Medium** [CHECK]

Use `next/font` (self-hosted, zero layout shift). Any `<link>` to fonts.googleapis.com is a
render-blocking third-party request and a CLS source.

### I4. Third-party scripts — **P2 Medium** [VERIFIED context]

Sentry + PostHog + GA + Clarity are all live (per project history). Four analytics scripts on a
marketing page is a real TBT/INP cost. Load PostHog and GA with `next/script strategy="lazyOnload"`,
and confirm Clarity is genuinely dormant. Measure before and after.

---

## J. Mobile

### J1. Mobile-first indexing is the only indexing — **P1 High** [CHECK]

Google indexes the mobile rendering. Anything hidden on mobile is functionally lower-weight.

**Verify:** Search Console → URL Inspection → "Test live URL" → screenshot; tap targets ≥ 48px;
no horizontal scroll at 360px width; base font ≥ 16px.

**SpeakOET-specific:** your audience skews heavily to mid-range Android on 4G. Test on a throttled
Moto-G-class profile in Chrome DevTools, not on a MacBook. A 1.8s LCP on desktop can be 6s there.

### J2. Table of contents and long articles on mobile — **P2 Medium** [VERIFIED context]

`components/learn/TableOfContents.tsx` exists. Confirm it collapses on mobile rather than pushing
the article body below the fold — a TOC that occupies the first screen hurts both engagement and
LCP.

---

## K. Internal Linking

### K1. No systematic internal linking — **P0 Critical** [VERIFIED]

**Finding.** `/learn` articles link back to `/blog` (`oet-band-scores/page.tsx:26`) and include a
`LearnCTA`. There is no sibling-to-sibling linking, no pillar structure, no breadcrumbs.

**Why it matters.** This is the highest-leverage, lowest-cost SEO work available to you. With
almost no backlinks, internal links are ~90% of the authority signal reaching any given page. It
is also the mechanism that makes 2,000 programmatic pages crawlable instead of orphaned.

**How to fix.**
1. Build the pillar/cluster structure from [02](02-topical-map.md).
2. Every cluster article links up to its pillar with descriptive anchor text; every pillar links
   down to all its children.
3. `RelatedContent` component, 3 links, tag-driven.
4. Breadcrumbs on every nested page with `BreadcrumbList` schema.
5. Rule: every article contains ≥1 contextual link to a product/conversion page using
   *natural* anchor text ("practise this role-play with AI feedback"), not "click here".

### K2. Footer link dilution — **P2 Medium**

`components/Footer.tsx` referenced site-wide. Keep footer links under ~25. A 60-link footer
flattens your architecture and tells Google nothing is more important than anything else.

---

## L. Duplicate Content

### L1. Programmatic templates are the main future risk — **P1 High**

**Why it matters.** 2,000 role-play pages where only the specialty name changes = mass thin
content. Google's 2024–2026 "scaled content abuse" policy explicitly targets this pattern, and
the penalty is site-wide, not page-level. This is the one way this plan can actively hurt you.

**How to fix — the quality gate (non-negotiable):** every programmatic page must contain
**≥60% unique content by token count**, and must include at least two of:
- a real playable role-play scenario written for that specialty,
- a real sample response with per-criterion scoring,
- specialty-specific vocabulary with definitions,
- genuine aggregate data ("average band 6.8 across 1,204 attempts").

Pages that fail the gate are `noindex` until they pass. Ship 300 that pass, not 3,000 that don't.

### L2. Country pages cannibalising each other — **P2 Medium**

"OET for Indian nurses" vs "OET for nurses in India" vs "OET requirements India" must be **one**
page, not three. Map keyword → URL once, in a spreadsheet, and treat it as the source of truth.

### L3. Existing overlap — **P2 Medium** [VERIFIED]

`/learn/oet-band-scores` and `/learn/oet-for-indian-nurses` both explain required scores. Decide
now which one owns "what OET score do I need" and make the other link to it.

---

## M. Pagination

### M1. Blog has no pagination — **P2 Medium** [VERIFIED]

`app/blog/page.tsx` renders `posts.map(...)` with no limit. At 200 posts this is one enormous page
with 200 links and a poor LCP.

**Fix.** Paginate at 12–20 per page, `/blog/page/2`, self-canonical each page (do *not* canonical
page 2 to page 1 — that de-indexes your posts), `noindex` from page 5 onwards only if quality
degrades. Add `rel=prev/next` for other engines; Google ignores it but Bing does not, and Bing
feeds ChatGPT search.

### M2. Programmatic hub pagination — **P1 High** (when programmatic ships)

Faceted navigation is where programmatic SEO projects die. Rule: **one canonical URL per facet
combination that has real search demand; every other combination is `noindex, follow`.**
`?sort=`, `?page=` beyond the first, and multi-facet combos must never be indexable.

---

## N. Redirects

### N1. Establish the redirect discipline before you need it — **P1 High** [CHECK]

**Verify now:** `http→https`, `non-www→www`, both single-hop 301. Redirect chains bleed authority
and slow crawl.

**Going forward:** you will restructure URLs when programmatic launches (`/learn/*` may become
`/oet/*`). Every change needs a 301 map in `next.config.js` `redirects()`, kept permanently. Never
delete a redirect; never 302 a permanent move.

### N2. `/learn` vs `/blog` structural decision — **P1 High** [VERIFIED]

You currently have two content systems (`app/learn/*.tsx` hard-coded, `/blog/[slug]` from Sanity)
serving the same purpose, cross-linking to each other, competing for the same queries. Pick one.

**Recommendation:** migrate all `/learn` articles into Sanity, serve them from `/learn/[slug]`
(keep the URLs — they may already have equity), and retire the hard-coded pages. `/blog` becomes
news/updates; `/learn` becomes evergreen educational content. Two purposes, one CMS.

---

## O. Broken Links

### O1. No monitoring — **P2 Medium**

**Verify.** Screaming Frog → Response Codes → Client Error 4xx (internal + external). Search
Console → Pages → "Not found (404)".

**Fix.** Monthly crawl. For a site your size this is a 10-minute recurring task; automate later
with a scheduled crawl only when the page count exceeds Screaming Frog's free tier.

### O2. `not-found.tsx` exists — **P3 Low** [VERIFIED]

Good. Make it useful: search box, links to top 6 articles, link to pricing. A 404 that recovers
the session is worth real money at scale.

---

## P. JavaScript Rendering

### P1. Marketing content in the raw HTML — **PASSED** [VERIFIED LIVE]

**Why it matters.** This is the failure mode that kills Next.js SaaS sites. If `Providers` or
`ConditionalLayout` (`layout.tsx:68-70`) forced client rendering, Googlebot would receive an empty
shell and queue the page for the render service — slower, rate-limited, sometimes skipped. AI
crawlers are worse: **GPTBot, ClaudeBot and PerplexityBot largely do not execute JavaScript at
all.** A client-rendered page is invisible to ChatGPT, full stop.

**Live check, 2026-07-26 — this passes.**

```bash
curl -sL https://www.speakoet.com/learn/oet-band-scores | grep -c "Grades and numeric"   # 1
```

`/` (64 KB), `/learn/oet-band-scores` (30 KB) and `/blog` (25 KB) all return full server-rendered
HTML with the `<h1>` and body text present. The `Providers` wrapper is not forcing client
rendering on marketing routes.

**What this means.** The most expensive item on the roadmap is already correct. Issue #3 in
[05](05-technical-roadmap.md) drops from 4–8 hours to a ~1-hour regression check. Do not skip the
check entirely though — **re-run this curl after any change to `Providers`, `ConditionalLayout` or
the root layout**, and add it as a CI assertion so a future refactor cannot silently break it.

**Remaining work (P2, not P0).** Marketing routes still ship the auth provider's JavaScript even
though they render server-side. That is an INP/TBT cost, not an indexability one. Moving
`Providers` into an `(app)` route group is now a performance optimisation, scheduled with I1.

### P2. `revalidate = 60` on the blog index — **P2 Medium** [VERIFIED]

`app/blog/page.tsx:5`. Reasonable, but 60 seconds means a Sanity fetch on nearly every crawl
window. Raise to 3600 and use Sanity webhooks → `revalidateTag()` for instant publish. Cheaper,
faster, fresher.

---

## Q. Image Optimization

### Q1. Audit every `<img>` — **P1 High** [CHECK]

**Verify.** `grep -rn "<img" frontend/app frontend/components` — every hit is a missed
optimisation. Also crawl → Images → "Missing Alt Text" and "Over 100kb".

**Fix.** `next/image` everywhere, explicit dimensions (CLS), `priority` on LCP image only,
`loading="lazy"` implicit elsewhere, AVIF/WebP via `next.config.images.formats`.

### Q2. Alt text as a ranking asset — **P2 Medium**

For SpeakOET, alt text is not just accessibility compliance: "OET Speaking role-play interface
showing real-time pronunciation feedback for a cardiology scenario" is an indexable description of
your differentiator, and Google Images sends meaningful traffic for "OET writing sample",
"OET referral letter format", "OET score report". Screenshots of the product on those pages are a
genuine traffic source.

### Q3. Sample letters and score reports should be HTML, not images — **P1 High**

The instinct is to screenshot a sample referral letter. Don't. Render it as real, selectable HTML
inside a styled container. Text is indexable, quotable by LLMs, and translatable. An image of a
letter is invisible to every engine that matters.

---

## Audit summary — what to fix first

| Priority | Issue | Doc ref |
|---|---|---|
| P0 | Blog posts missing from sitemap (latent — fix before publishing starts) | A1 |
| P0 | `/upgrade` blocked, no public pricing page | A2 |
| P0 | No `Article`/`FAQPage`/`Breadcrumb`/`SoftwareApplication` schema | G1 |
| P0 | No internal-linking system | K1 |
| ~~P0~~ | ~~Server-rendered HTML for AI crawlers~~ — **verified passing 2026-07-26** | P1 |
| P1 | Homepage title claims only Speaking | E1 |
| P1 | `lastModified` is always `now` | C2 |
| P1 | Root canonical inheritance landmine | F1 |
| P1 | No AI-crawler policy in robots | D1 |
| P1 | `/learn` vs `/blog` duplication | N2 |
| P1 | Segmented sitemaps needed before programmatic | C1 |
| P1 | Programmatic duplicate-content quality gate | L1 |
