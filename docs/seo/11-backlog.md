# 11 — Prioritised Backlog

**Columns:** Business Impact · SEO Impact · Difficulty · Time · Dependencies · Expected ROI.
Time is engineer- or writer-hours. ROI is judged over 12 months.

Ordering rule used throughout: **anything that unblocks revenue this month beats anything that
compounds next year — except when the compounding thing is cheap.**

---

# P0 — Must do immediately (weeks 1–4)

### P0.1 — Add Sanity blog posts to the sitemap
- **Business impact:** Medium — unlocks discovery for all existing and future CMS content
- **SEO impact:** **Very high** — sitemap is the primary discovery path on a new domain
- **Difficulty:** Trivial · **Time:** 2h · **Dependencies:** none
- **ROI:** **Extreme.** Two hours of work restoring indexation for every post you will ever
  publish. The best line-per-hour ratio in this document.

### ~~P0.2 — Verify server-side rendering on all marketing routes~~ — **DONE / PASSED 2026-07-26**
- Checked live: `/`, `/learn/oet-band-scores` and `/blog` all return full server-rendered HTML with
  body text present. GPTBot/ClaudeBot/PerplexityBot can read the site. **Was the biggest risk in
  the plan; it is not a risk.**
- **Residual work (1h, keep it):** add the curl assertion to CI so a future refactor of
  `Providers` / `ConditionalLayout` cannot silently break it. Stripping the auth provider's JS from
  marketing routes is now a performance item (P1.3), not an indexability one.

### P0.3 — Public, indexable `/pricing` page
- **Business impact:** **Very high** — direct commercial intent, currently 100% forfeited
- **SEO impact:** High · **Difficulty:** Low · **Time:** 6h
- **Dependencies:** none · **ROI:** **Very high.** Bottom-funnel traffic converts at 5–10×
  informational traffic. This page starts paying within weeks.

### P0.4 — Restructure `robots.ts` (specific disallows + named AI crawlers)
- **Business impact:** Medium now, **critical later** · **SEO impact:** Very high (preventive)
- **Difficulty:** Trivial · **Time:** 1h · **Dependencies:** none
- **ROI:** **Extreme as insurance.** If `/practice` stays prefix-disallowed, the entire programmatic
  engine ships to zero traffic and you may not notice for months.

### P0.5 — Structured data system (`FAQPage`, `Article`, `Breadcrumb`, `SoftwareApplication`)
- **Business impact:** Medium — rich results lift CTR
- **SEO impact:** **Very high** — and it is the single biggest lever on AI citation
- **Difficulty:** Medium · **Time:** 10h · **Dependencies:** none
- **ROI:** **High.** Build it once as typed helpers; every future page inherits it free.

### P0.6 — Internal linking system (breadcrumbs, related content, pillar structure)
- **Business impact:** Medium (session depth → signups) · **SEO impact:** **Very high**
- **Difficulty:** Medium · **Time:** 10h · **Dependencies:** tag field on content models
- **ROI:** **Very high.** With ~10 backlinks, internal links carry ~90% of the authority reaching
  any page. Also the mechanism that makes 1,200 programmatic pages crawlable rather than orphaned.

### P0.7 — 8 country/regulator landing pages
- **Business impact:** **Very high** — the highest-intent cluster in the niche
- **SEO impact:** Very high · **Difficulty:** Low technically, high research burden · **Time:** 16h
- **Dependencies:** P0.5 (schema), P0.6 (linking)
- **ROI:** **Very high.** "OET score for NMC" searchers have a booked exam and a wallet open.
  **Every fact must be human-verified against the regulator** — a wrong requirement here is worse
  than no page.

### P0.8 — Free tool: OET score calculator
- **Business impact:** High · **SEO impact:** Very high (links + AI citations + rankings)
- **Difficulty:** Low · **Time:** 8h · **Dependencies:** none
- **ROI:** **Very high.** Ranks, earns passive links, captures emails, and its result screen is the
  best natural place on the site to say "your Writing is 30 points short — here's the plan".

### P0.9 — Free scored mock test, no signup
- **Business impact:** **Very high** — your strongest conversion asset
- **SEO impact:** High ("free OET mock test" is a top-volume query)
- **Difficulty:** Medium · **Time:** 12h · **Dependencies:** existing mock product, rate limiting
- **ROI:** **Very high.** Demonstrates the product instead of describing it. Must be
  cost-capped — an ungated AI mock test is an unmetered expense.

### P0.10 — Migrate `/learn` to the CMS
- **Business impact:** High (indirect — unlocks publishing velocity)
- **SEO impact:** High · **Difficulty:** Medium · **Time:** 16h
- **Dependencies:** Sanity schema
- **ROI:** **Very high.** At 2–4 articles/week for a year, hard-coded pages mean ~150 deploys of
  pure content and a velocity ceiling exactly where velocity is the strategy. Also resolves the
  `/learn` vs `/blog` duplication.

### P0.11 — Programmatic infrastructure + quality gate
- **Business impact:** Very high (enables everything in [03](03-programmatic.md))
- **SEO impact:** **Very high, and very high risk if done wrong**
- **Difficulty:** High · **Time:** 24h · **Dependencies:** P0.4, P0.6, P0.10
- **ROI:** **Highest ceiling in the plan, highest downside.** The `isIndexable()` gate is not
  optional — Google's scaled-content-abuse action is site-wide.

**P0 total: ~110 hours.**

---

# P1 — Next (weeks 5–12)

### P1.1 — Root canonical fix + `buildMetadata()` helper
- Business: Low · SEO: High (preventive) · Difficulty: Low · **3h** · Deps: none
- **ROI: High.** Makes it structurally impossible to ship a page that self-canonicalises to `/`.

### P1.2 — Homepage title/description rewrite
- Business: Medium · SEO: High · Difficulty: Trivial · **1h** · Deps: none
- **ROI: Very high.** One hour to stop telling Google and every LLM that you only do Speaking.

### P1.3 — Core Web Vitals pass (images, fonts, scripts)
- Business: Medium · SEO: High · Difficulty: Medium · **10h** · Deps: none
- **ROI: High.** Audience is mid-range Android on 4G; LCP directly affects both ranking and bounce.

### P1.4 — Segmented sitemaps
- Business: Low · SEO: Medium (High diagnostically) · Difficulty: Low · **4h** · Deps: P0.11
- **ROI: High.** Turns "why isn't it indexing" from a guess into a per-template number.

### P1.5 — Rewrite 5 existing articles to answer-first format
- Business: Medium · SEO: High · Difficulty: Low · **12h** · Deps: P0.5, P0.10
- **ROI: High.** Existing pages with existing (small) equity — cheaper to improve than to replace.

### P1.6 — 4 product landing pages
- Business: **Very high** · SEO: High · Difficulty: Medium · **12h** · Deps: P0.3
- **ROI: Very high.** These are where organic traffic becomes revenue.

### P1.7 — Programmatic batch 1: 60 speaking role-plays
- Business: High · SEO: High · Difficulty: Medium · **30h** (mostly content) · Deps: P0.11
- **ROI: High** *if indexation ≥ 60%.* Measure before scaling. This is a test, not a launch.

### P1.8 — Q1 data report ("The OET Writing Report 2026")
- Business: Medium · SEO: **Very high** · Difficulty: Medium · **25h** · Deps: enough user data
- **ROI: Very high.** The only reliable way a startup earns institutional links. Produces links,
  AI citations, PR, social content and sales collateral from one effort.

### P1.9 — `llms.txt` + AI-crawler monitoring + prompt panel
- Business: Medium · SEO: Medium (High for AEO) · Difficulty: Low · **5h** · Deps: none
- **ROI: High.** Cheap, and it makes AI search measurable instead of anecdotal.

### P1.10 — Free tool: readiness quiz
- Business: High · SEO: Medium · Difficulty: Medium · **10h** · Deps: none
- **ROI: Very high.** Best lead magnet in the plan. "Am I ready?" is the question they came with.

### P1.11 — Noindex non-production hosts
- Business: Low · SEO: Medium · Difficulty: Trivial · **1h** · Deps: none
- **ROI: Medium.** Cheap insurance against duplicate-content dilution.

### P1.12 — Redirect and canonical host hygiene
- Business: Low · SEO: Medium · Difficulty: Low · **2h** · Deps: none
- **ROI: Medium.** Also establishes the permanent home for every future 301.

### P1.13 — Analytics: Bing, AI referrer channel, conversion attribution
- Business: **High** · SEO: Medium · Difficulty: Low · **5h** · Deps: none
- **ROI: Very high.** Without per-landing-page revenue attribution you cannot make the month-6
  decision about which templates to kill. This is what makes the whole plan steerable.

### P1.14 — 4 comparison/alternative pages
- Business: **Very high** · SEO: Medium · Difficulty: Low · **8h** · Deps: P0.3
- **ROI: Very high.** Competitor-brand intent is the cheapest conversion available anywhere.

### P1.15 — Programmatic batch 2: 180 writing samples
- Business: **Very high** · SEO: Very high · Difficulty: High (case notes are real work) · **60h**
- Deps: P1.7 indexation result
- **ROI: Very high.** Highest commercial intent of any programmatic template.

**P1 total: ~190 hours.**

---

# P2 — Later (months 4–8)

| Task | Business | SEO | Difficulty | Time | Deps | ROI |
|---|---|---|---|---|---|---|
| Complete scores cluster (24 pages) | High | High | Low | 30h | P0.10 | High |
| Complete exam cluster (28 pages) | Medium | Very high | Low | 35h | P0.10 | High |
| Remaining country hubs (14 pages) | High | High | Low | 25h | P0.7 | High |
| Programmatic: country × profession (95) | High | High | Medium | 30h | P0.11 | High |
| Programmatic: abbreviations (395) | Low | High | Medium | 50h | P0.11 | Medium |
| Programmatic: vocabulary sets (75) | Low | Medium | Low | 25h | P0.11 | Medium |
| Preparation cluster (26 pages) | High | High | Low | 32h | — | High |
| Per-page OG images | Medium | Low | Low | 4h | — | Medium — WhatsApp sharing is real distribution here |
| 4 more free tools | Medium | High | Medium | 30h | — | High |
| College outreach (100 emails + 6 partnerships) | Medium | High | Low effort/high patience | 20h | — | High |
| Agency partnership programme | **Very high** | Low | Medium | 25h | — | **Very high — B2B revenue, not just links** |
| Q2 + Q3 data reports | Medium | Very high | Medium | 50h | user data | High |
| Video for top 20 articles | Medium | Medium | High | 60h | — | Medium — real, but expensive |
| Careers cluster (26 pages) | Low | Very high | Low | 32h | — | Medium |
| Nursing English cluster (26 pages) | Low | High | Low | 32h | — | Medium — best link magnet |
| 404/orphan/broken-link sweep | Low | Medium | Low | 4h | — | Medium |
| Blog pagination | Low | Medium | Low | 3h | — | Low until ~60 posts |

---

# P3 — Future (months 9+)

| Task | Business | SEO | Difficulty | Time | ROI |
|---|---|---|---|---|---|
| Grammar cluster (24 pages) | Very low | High | Low | 30h | Medium — authority + AI citations only |
| Vocabulary support (28 pages) | Very low | High | Low | 32h | Medium |
| Programmatic: source × destination (85) | High | Medium | Medium | 35h | Medium — high value, needs annual accuracy upkeep |
| Programmatic: practice sets (100) | Medium | High | Very high (audio) | 100h | Medium |
| City coaching pages (45) | Medium | Medium | Medium | 30h | **Low–negative unless real local content exists.** Only with ≥2 local testimonials per city |
| Profession expansion (doctors, pharmacists) | High | High | Medium | 40h | High — **but it is a product decision, not an SEO one** |
| Multilingual (Tagalog, Hindi, Malayalam) | Medium | Medium | High | 80h | Medium — most nurses search in English; validate demand first |
| Scholarship programme | Low | Medium | Low | 15h + cost | Medium — only if genuinely awarded |
| Wikidata entry | Low | Medium | Low | 2h | Medium — needs press mentions first |
| Conversion-rate A/B testing on top 20 pages | **Very high** | None | Medium | 30h | **Very high — do this in month 10, not month 24** |
| Content pruning + consolidation | Medium | High | Low | 20h | High from month 9 onward |

---

## The 10 things to do first, in order

If the backlog is overwhelming, this is the sequence. It is ordered by ROI per hour, not by tidiness.

1. **P0.1** Sitemap fix — 2h
2. **P0.4** robots.ts restructure — 1h
3. **P1.2** Homepage title — 1h
4. **P0.3** `/pricing` page — 6h
5. **P0.8** Score calculator — 8h
6. **P0.7** 8 country pages — 16h
7. **P0.9** Free mock test — 12h
8. **P0.6** Internal linking — 10h
9. **P0.10** CMS migration — 16h
10. **P0.2 residual** SSR assertion in CI — 1h

**That is 73 hours — under two focused weeks — and it covers most of the recoverable value.**
Everything after it compounds; everything in it pays this quarter.

---

## Resourcing

| Role | Commitment | Cost estimate | Why |
|---|---|---|---|
| Engineer (you or a contractor) | ~20h/week, months 1–3, then ~8h/week | — | P0 and P1 technical work |
| OET-qualified nurse-writer | Part-time from month 3 | $800–1,500/mo (India/Philippines) | Credibility, clinical accuracy, named author for E-E-A-T. **Best marketing hire available at this stage.** |
| Founder | ~10h/week | — | The 30 money pages, community presence, partnerships. Not delegable — nobody else knows the customer. |
| Ahrefs or Semrush | 1 month, then quarterly | ~$100–200/mo | Baseline + competitor gap. Do not subscribe year-round yet. |
| Screaming Frog | Free tier | $0 | Sufficient below 500 URLs; buy the licence around month 4 |
| Sanity | Existing | Free tier likely sufficient | Already wired |

**Total incremental cash: roughly $1,000–1,800/month from month 3.** That is a small marketing
budget by design, and the plan is built to fit it.
