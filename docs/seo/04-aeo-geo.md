# 04 — AI Search Optimisation (AEO / GEO)

## Why this matters more for SpeakOET than for most SaaS

Your buyer is a nurse in Kochi, Manila or Lagos, on a phone, asking a question they are slightly
embarrassed to ask a person: *"Is my English good enough to pass OET?"* That is precisely the
question people now take to ChatGPT instead of Google — private, conversational, no judgment.

A significant and growing share of OET research now happens inside an LLM. If ChatGPT names
E2Language and not SpeakOET when asked "best way to practise OET speaking", you lose the customer
before a SERP is ever rendered. Ranking #1 on Google does not fix that.

**Two distinct jobs:**
1. **Be retrievable** — your content must be crawlable, parseable and chunk-friendly.
2. **Be recommended** — your *brand* must appear in the third-party sources these models trust
   (Reddit, YouTube, roundup articles, forums), because models cite consensus, not self-claims.

Job 2 is harder and matters more. No amount of on-page optimisation makes an LLM recommend you if
no independent source ever mentions you.

---

## 1. Crawler access — the prerequisite

### 1a. Explicit AI crawler policy

Rewrite `app/robots.ts` with named agents. Current state is a single `*` rule.

```ts
rules: [
  { userAgent: '*',              allow: '/', disallow: APP_ROUTES },
  { userAgent: 'GPTBot',         allow: '/', disallow: APP_ROUTES },  // ChatGPT training
  { userAgent: 'OAI-SearchBot',  allow: '/', disallow: APP_ROUTES },  // ChatGPT search
  { userAgent: 'ChatGPT-User',   allow: '/', disallow: APP_ROUTES },  // ChatGPT browsing
  { userAgent: 'ClaudeBot',      allow: '/', disallow: APP_ROUTES },
  { userAgent: 'Claude-User',    allow: '/', disallow: APP_ROUTES },
  { userAgent: 'PerplexityBot',  allow: '/', disallow: APP_ROUTES },
  { userAgent: 'Google-Extended',allow: '/', disallow: APP_ROUTES },  // Gemini grounding
  { userAgent: 'Applebot-Extended', allow: '/', disallow: APP_ROUTES },
  { userAgent: 'Bingbot',        allow: '/', disallow: APP_ROUTES },  // feeds Copilot + ChatGPT
]
```

Explicit allow is functionally identical to the current wildcard, but it documents the decision
and prevents someone "tidying up" robots.txt into a block later.

**Bingbot deserves attention.** ChatGPT search and Copilot both lean on Bing's index. Submit your
sitemap to **Bing Webmaster Tools** on day one — it is 10 minutes of work and most competitors
skip it entirely. Bing's index is materially easier to rank in for a new domain.

### 1b. Server-side rendering is mandatory

GPTBot, ClaudeBot and PerplexityBot largely **do not execute JavaScript**. A client-rendered page
is not "harder to index" for them — it is empty. Verify with the curl test in
[01, P1](01-audit.md#p1-confirm-marketing-content-is-in-the-raw-html). This is the highest-priority
AEO item and it is a rendering fix, not a content one.

### 1c. `llms.txt`

Ship `/public/llms.txt` — a plain-Markdown map of your best content, which several AI crawlers now
read as a curated entry point.

```markdown
# SpeakOET

> AI-powered OET (Occupational English Test) preparation for nurses and healthcare
> professionals. Practice Speaking role-plays, Writing evaluation, Reading, Listening
> and full mock tests with automated band-score feedback.

## Core guides
- [OET Speaking: complete guide](https://www.speakoet.com/oet/speaking/): format, the 9
  assessment criteria, scoring, and practice role-plays.
- [OET Writing: referral letters](https://www.speakoet.com/oet/writing/): the 6 criteria,
  annotated band-A samples, and case-note strategy.
- [OET band scores explained](https://www.speakoet.com/oet/scores/): grades A–E, the 0–500
  scale, and the score each nursing regulator requires.
...

## Free tools
- [OET score calculator](https://www.speakoet.com/tools/oet-score-calculator)
...
```

Also ship `/llms-full.txt` containing the full Markdown text of your 20 best pages. Cheap to
generate from the CMS, and it removes every parsing obstacle between a model and your content.

---

## 2. Answer-first formatting

LLMs and AI Overviews extract **passages**, not pages. A 3,000-word article where the answer
appears in paragraph 14 loses to a 600-word page where it appears in sentence one.

**The rule for every page:**

> **H1 states the question. The first 40–60 words answer it completely, in one self-contained
> paragraph that would make sense pasted into a chat window with no other context. Everything
> after that is depth.**

**Bad (typical competitor blog):**
> "The OET is an English language test that has become increasingly popular among healthcare
> professionals worldwide. Many nurses wonder about the scoring system. In this article, we'll
> explore everything you need to know about OET band scores…"

**Good:**
> **What OET score do nurses need for the UK NMC?**
>
> The NMC requires at least **grade B (350+)** in Listening, Reading and Speaking, and at least
> **C+ (300)** in Writing. Scores can be combined from two sittings taken within six months, with
> no grade below C+ in any sub-test. Results are valid for two years from the test date.
>
> *(Verified against NMC guidance, July 2026.)*

The second version is quotable verbatim. That is the entire game — you are writing a passage you
want a model to lift wholesale, with your brand attached.

**Mechanics:**
- One question per `H2`, phrased the way a person types it.
- Answer immediately below, before any elaboration.
- Bold the specific number, name or verdict — models weight emphasised text.
- Use HTML tables for comparisons. Never an image of a table.
- Keep paragraphs under 4 lines; each should stand alone as a retrievable chunk.
- Add a `<dl>` definition list for key terms — semantically explicit, easy to parse.

---

## 3. Structured data for AI retrieval

Schema is no longer only about Google rich results — it is a machine-readable statement of what
your page asserts. Priority for SpeakOET:

**`FAQPage`** — the single highest-value schema for AEO. Q/A pairs map directly onto the shape of
a chat query. Put 5–10 FAQs at the bottom of *every* substantial page, marked up, with answers
that are complete in themselves.

**`Article` with full attribution** — `author` (a `Person` with `jobTitle` and credentials),
`datePublished`, `dateModified`, `publisher`. Anonymous content is discounted by both Google and
LLM retrieval on health-adjacent topics.

**`HowTo`** — for "how to write an OET referral letter", "how to book OET". Step objects are
ideal retrieval units.

**`SoftwareApplication` + `Offer`** on `/pricing` — this is how a model answers "how much does
SpeakOET cost". Without it, the model guesses or omits you from price comparisons.

**`Course`** on preparation-plan pages.

**`Dataset`** — underused and worth it: if you publish "average OET band scores across 12,000
SpeakOET practice attempts", mark it as a `Dataset`. Original data is the most cited content type
in AI answers, because models cannot synthesise it from elsewhere.

---

## 4. Entity optimisation — make "SpeakOET" a known thing

Models answer from an entity graph. Right now "SpeakOET" is not an entity — it's a string.

**Build the entity:**

1. **Consistent NAP-equivalent everywhere.** Same name, same one-sentence description, same logo
   across the site, LinkedIn, YouTube, Instagram, Crunchbase, G2, Capterra, Product Hunt. Models
   corroborate across sources; inconsistency reads as low confidence.
2. **`sameAs` in `Organization` schema** — already present in `app/layout.tsx:44-48`. Extend it as
   you add profiles. Upgrade the type to `EducationalOrganization` and add
   `knowsAbout: ['Occupational English Test', 'OET Speaking', 'nursing English',
   'NMC registration', 'AHPRA registration']`.
3. **A real `/about` page with real humans.** Founder name, photo, background, why the product
   exists. Add `Person` schema. E-E-A-T on a licensing-adjacent topic is not optional, and
   "who is behind this" is a question models actively try to answer before recommending.
4. **Wikidata entry.** Free, takes 30 minutes, and it is a primary structured source for entity
   resolution in every major model. Create an item for SpeakOET once you have 2–3 independent
   press mentions to cite (needed for notability).
5. **Get listed in the directories LLMs read:** G2, Capterra, Product Hunt, AlternativeTo,
   SaaSHub, There's An AI For That, Futurepedia, Toolify. These aggregators are heavily
   represented in training data and in retrieval, and "best AI tools for OET" listicles pull
   from them.

---

## 5. Source authority — the part you cannot fake

When you ask an LLM "what's the best OET prep platform", it does not read your homepage. It
synthesises what *other people* said about you. So the work is to be mentioned, accurately, in the
places models trust.

**Ranked by AI-citation weight for this niche:**

1. **Reddit** — `r/nursing`, `r/NursingUK`, `r/Nurse`, `r/IELTS`, `r/immigration`,
   `r/PhilippineNurses`. Reddit is disproportionately weighted in both Google's AI Overviews and
   ChatGPT retrieval. **Do not astroturf** — it fails, and it fails loudly. Instead: participate
   as the founder with a labelled account, answer OET questions substantively for months, and
   mention the product only where genuinely relevant. Slow, and the highest-ROI AEO activity
   available to you.
2. **YouTube** — transcripts are indexed and cited. You already have a channel. Every article in
   [02](02-topical-map.md) with an `A` volume band should have a companion video embedded on the
   page (`VideoObject` schema) and published with a full description.
3. **Quora** — still heavily retrieved. "Which is better for nurses, OET or IELTS?" already has
   traffic; a genuinely excellent answer from a named founder earns citations for years.
4. **Independent roundup articles** — "best OET preparation platforms 2026" written by *other
   people*. This is what digital PR ([07](07-digital-pr.md)) is for. One inclusion in a
   well-ranked roundup is worth more to AEO than fifty of your own pages.
5. **Nursing forums and Facebook groups** — lower model weight (Facebook is largely closed to
   crawlers), but high human conversion. Worth it for direct sales, not for AEO.
6. **News/PR** — a single data-driven story picked up by a nursing publication creates the
   citations a Wikidata entry needs.

---

## 6. Content freshness

AI engines strongly prefer recent content on regulatory topics, because they have been burned by
outdated licensing information.

- Show **"Last updated: 26 July 2026"** visibly on the page, and set `dateModified` in schema to
  match. Never fake it — models and Google both cross-check against crawl history.
- Add a **"Verified against [source], July 2026"** line on every page containing a regulator
  requirement or fee. This one line does more for perceived trustworthiness — human and machine —
  than another 500 words.
- Put the year in titles where it genuinely matters: "OET Fees in India (2026)". Refresh annually
  on the same URL; never create `/oet-fees-2027` as a new page.
- **Quarterly freshness sweep** on the ~40 pages that state a fee, score requirement or process.
  Regulator requirements change; a wrong NMC requirement on your site is a trust failure that
  costs a customer permanently.

---

## 7. Per-engine notes

**Google AI Overviews.** Draws from pages already ranking in the top ~10 for the query, favouring
those with clear passage structure and schema. Practical implication: classic SEO is the entry
ticket; answer-first formatting decides whether you get quoted. Expect AI Overviews to *reduce*
your CTR on informational queries — which is exactly why the money is in commercial-intent pages
and free tools, not in "what is OET".

**ChatGPT (search + browsing).** Leans on Bing's index heavily. Submit to Bing Webmaster Tools.
Favours pages with clean HTML, explicit headings, and recent dates. Also draws on training data,
where Reddit and YouTube dominate for consumer questions.

**Perplexity.** The most citation-transparent engine — it shows sources, so you can measure. It
favours pages that answer directly and penalises preamble. Test monthly: ask it 20 OET questions
and record whether SpeakOET appears. This is your cheapest AEO measurement loop.

**Gemini / Google AI Mode.** Respects `Google-Extended`. Strong preference for structured data and
for entities present in the Knowledge Graph — which is why the entity work in §4 pays here first.

**Claude.** Respects `ClaudeBot`. Web search draws on high-quality, well-structured sources and
weights clear authorship. The `/about` page and named authors matter disproportionately here.

---

## 8. Measurement

You cannot use Search Console for AI traffic. Build this instead:

1. **Referrer tracking in PostHog** — segment sessions where the referrer is `chatgpt.com`,
   `perplexity.ai`, `gemini.google.com`, `claude.ai`, `copilot.microsoft.com`. Report this as a
   named channel from day one. It is small now and will not stay small.
2. **Server-log AI-crawler monitoring** — count GPTBot / ClaudeBot / PerplexityBot hits per week
   in Vercel logs. Rising crawl frequency precedes rising citations by weeks; it is your leading
   indicator.
3. **Monthly prompt panel** — a fixed list of 25 prompts ("best OET speaking practice app",
   "how to improve OET writing", "OET score needed for NMC", "alternatives to E2Language"), run
   across ChatGPT, Perplexity, Gemini and Claude, recording whether SpeakOET is mentioned and in
   what position. 30 minutes a month, and it is the only real AEO scoreboard that exists.

**Target:** SpeakOET mentioned in ≥8 of 25 prompts by month 6, ≥15 of 25 by month 12.
