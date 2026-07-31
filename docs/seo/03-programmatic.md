# 03 — Programmatic SEO Strategy

## The thesis

Every other OET site publishes *articles about* practice. SpeakOET can publish *the practice
itself*, at URL granularity, for every specialty, scenario, letter type, country and profession a
nurse might search for.

That is the difference between a page that says "here's how to write a referral letter for a
diabetic patient" and a page that contains a real case-note set, a real band-A sample letter with
per-criterion annotation, and a button that grades the reader's own attempt in 30 seconds. The
first is copyable in an afternoon. The second requires your product.

**This is the moat.** Everything else in this plan is table stakes.

---

## The non-negotiable quality gate

Read this before the templates. Google's scaled-content-abuse policy (enforced aggressively since
2024) is a **site-wide** action, not a page-level one. A programmatic project done badly does not
underperform — it takes the whole domain down. The gate:

**A page may be indexed only if it satisfies ALL of:**

1. **≥400 words of genuinely unique body content**, where "unique" means it does not appear on any
   other URL on the domain. Template boilerplate does not count toward the 400.
2. **≥60% unique tokens** relative to its sibling pages in the same template.
3. **At least two unique assets** from: a written scenario, a scored sample response, a
   specialty-specific vocabulary set with definitions, a real FAQ block, or aggregate user data.
4. **A real search-demand signal** — the head keyword has measurable volume, OR the page is part
   of a set where the parent term has volume and the entity is real (a real specialty, a real
   country, a real abbreviation).
5. **A working interactive element** — the actual role-play, the actual checker, the actual test.

**Implementation:** a `isIndexable(page)` predicate in the generator. Pages that fail get
`robots: { index: false, follow: true }` and are excluded from the sitemap. They still exist,
still pass link equity, still work for users who find them — they just do not enter the index
until they're good enough.

**Launch discipline:** publish in batches of 100–300, wait 3–4 weeks, measure indexation rate in
Search Console. Below 60% indexed = the template is thin; fix it before the next batch. Do not
ship 3,000 pages in week one. A new domain dumping 3,000 URLs is the single clearest spam signal
you can send.

---

## Template 1 — Speaking role-plays by specialty × scenario

**URL:** `/oet/speaking/role-play/[specialty]/[scenario]`
**Example:** `/oet/speaking/role-play/cardiology/explaining-medication`
**Target query pattern:** "OET speaking role play cardiology", "OET role play card medication
counselling", "OET speaking practice diabetes"

**Page contains:**
- The full role-play card (nurse's card, visible; patient's card, summarised) — unique per page
- A one-click **live AI role-play** using the existing speaking engine
- A model transcript at band B and band C, side by side, with the differences annotated
- 15–25 specialty-specific phrases with function labels
- Criterion-by-criterion notes on what this scenario tests most
- 5 FAQs specific to that scenario
- Aggregate data once you have it: "average intelligibility score on this scenario: 6.2"

**Dimensions**
- **Specialties (40):** cardiology, respiratory, endocrinology/diabetes, oncology, paediatrics,
  neonatal, maternity/midwifery, gynaecology, orthopaedics, neurology, stroke, renal/dialysis,
  gastroenterology, urology, dermatology, rheumatology, haematology, infectious disease,
  emergency, ICU/critical care, theatre/perioperative, recovery/PACU, anaesthetics support,
  palliative care, geriatrics, dementia care, mental health, addiction, learning disability,
  community nursing, district nursing, practice nursing, occupational health, school nursing,
  health visiting, wound/tissue viability, stoma care, diabetes specialist, pain management,
  rehabilitation.
- **Scenario types (10):** explaining a diagnosis, medication counselling, pre-procedure
  explanation, post-procedure/discharge advice, lifestyle advice, reassuring an anxious patient,
  handling a refusal, breaking bad news, speaking to a relative, addressing a complaint.

**Pages: 40 × 10 = 400.** Realistically ~280 survive the quality gate initially (not every
combination is clinically sensible — "breaking bad news" in school nursing is a stretch). Curate.

---

## Template 2 — Writing samples by letter type × specialty

**URL:** `/oet/writing/sample/[letter-type]/[specialty]`
**Example:** `/oet/writing/sample/referral-letter/diabetes`

**Page contains:**
- A complete unique case-note set (the hardest and most valuable asset — this is what nurses
  actually search for and cannot find free)
- A band-A model letter, rendered as **selectable HTML, never an image**
- A band-C version of the same letter with inline annotations showing exactly what dropped it
- Criterion table: Purpose / Content / Conciseness / Genre & Style / Organisation / Language
- "Grade your own attempt" — the existing AI evaluator, one free use
- Specialty-specific letter vocabulary
- 4 FAQs

**Dimensions**
- **Letter types (6):** referral letter (to specialist), referral letter (to GP), discharge
  letter, transfer letter, letter of advice to patient/carer, letter to a community service.
- **Specialties (35):** as above, minus the ones where letters are implausible.

**Pages: 6 × 35 = 210.** Expect ~180 to pass the gate.

This template is the strongest commercial performer in the whole plan: "OET writing sample" and
its long tail is the highest-volume, highest-desperation query cluster in OET, and the searcher is
weeks from an exam.

---

## Template 3 — Medical abbreviations

**URL:** `/medical-abbreviations/[abbreviation]`
**Example:** `/medical-abbreviations/prn`

**The trap:** one page per abbreviation with a two-line definition is textbook thin content, and
there are ~1,500 abbreviations. Do not do that.

**The fix — make each page substantial:**
- Full expansion + pronunciation
- Meaning in clinical context, with 3 real usage examples in sentences
- **OET-specific guidance: may you use this in a referral letter, or must you expand it?**
  (This is the unique angle nobody else covers and it is exactly what nurses need.)
- Related abbreviations, commonly confused abbreviations
- UK vs US vs AU usage differences where they exist
- A short quiz item

**Volume strategy:** ship the **top 350 abbreviations** as individual pages (these have real
search volume — "what does prn mean", "bd medical abbreviation"). The remaining ~1,100 live on
**45 grouped hub pages** by body system and context ("respiratory abbreviations",
"drug frequency abbreviations", "abbreviations in nursing notes"), each covering 20–30 terms
properly.

**Pages: 350 + 45 = 395.**

---

## Template 4 — Vocabulary sets by specialty × theme

**URL:** `/oet/vocabulary/[specialty]` and `/oet/vocabulary/[theme]`

**Page contains:** 40–60 terms with definition, plain-English patient equivalent, an example
sentence in a clinical context, collocations, a pronunciation clip (you have TTS), and a linked
flashcard deck.

**Dimensions:** 40 specialties + 35 themes (pain, wounds, medication routes, vital signs,
mobility, nutrition, hygiene, infection control, mental state, consent, escalation, equipment,
investigations, results, allergies, discharge, safeguarding, end of life, …).

**Pages: 75.** Low count, high quality, strong internal-link hub value.

---

## Template 5 — Country × profession requirement pages

**URL:** `/oet/[destination-country]/[profession]`
**Example:** `/oet/australia/nursing`, `/oet/uk/pharmacy`

**Page contains:** exact score requirement, regulator name and link, whether score combining is
allowed, validity period, fee in local currency, test centres, the full registration pathway
after OET, and a free readiness check.

**Dimensions:** 12 destination countries × 12 OET professions (nursing, medicine, dentistry,
pharmacy, physiotherapy, occupational therapy, optometry, podiatry, radiography, speech pathology,
veterinary science, dietetics).

**Pages: 144.** Curate hard — not every profession registers via OET in every country, and
publishing a page claiming otherwise is a trust failure on a YMYL-adjacent topic. Expect ~95 valid.

---

## Template 6 — Source country × destination country migration guides

**URL:** `/oet/from-[source]/to-[destination]`
**Example:** `/oet/from-india/to-uk`

**Page contains:** the full pathway (OET → CBT → visa → OSCE → PIN for UK), fee in source
currency, timeline, common rejection reasons for that corridor, embassy/verification steps,
and testimonials from nurses on that exact corridor.

**Dimensions:** 14 source countries × 7 realistic destinations.

**Pages: 98.** These are extremely high conversion — a nurse searching "OET India to UK process"
is spending money this month — but they demand real accuracy. Budget for annual review.

---

## Template 7 — Listening & reading practice sets

**URL:** `/oet/listening/practice/[topic]` and `/oet/reading/practice/[topic]`

Each page = one real practice set with audio/text, questions, answers, transcript, and explanation
for every distractor. 60 listening topics + 60 reading topics.

**Pages: 120.** Content-production heavy (audio recording), so this trails the others. But
"free OET listening practice test" is one of the highest-volume queries in the niche and currently
served almost entirely by low-quality PDF farms and YouTube.

---

## Template 8 — City-level coaching pages

**URL:** `/oet-coaching/[city]`
**Example:** `/oet-coaching/kochi`

**Honest assessment: this is the riskiest template in the plan.** "OET coaching in Kochi" has
genuine commercial volume, but a page whose only unique content is the city name is exactly what
the scaled-content policy targets, and local-intent searchers may bounce when they discover you
are not a physical institute.

**Only do this if each page carries real local content:** the actual test centres in that city
with addresses, local fee in INR/PHP, a comparison of local physical institutes' pricing versus
online, and testimonials from nurses in that city. If you cannot produce that, skip the template
entirely — the downside (site-wide thin-content signal) outweighs the upside.

**Dimensions if pursued:** 45 Indian cities + 15 Philippine + 10 Gulf. **Pages: 70.**
Gate at "do we have ≥2 real testimonials from this city" — which conveniently means this template
launches in month 8+, once you have users.

---

## Volume summary

| Template | Theoretical | Passing quality gate | Launch wave |
|---|---|---|---|
| 1. Speaking role-plays | 400 | ~280 | Wave A (week 6) |
| 2. Writing samples | 210 | ~180 | Wave A (week 8) |
| 3. Medical abbreviations | 1,495 | 395 | Wave B (month 4) |
| 4. Vocabulary sets | 75 | 75 | Wave B (month 4) |
| 5. Country × profession | 144 | ~95 | Wave A (week 10) |
| 6. Source × destination | 98 | ~85 | Wave C (month 6) |
| 7. Practice sets | 120 | ~100 | Wave C (month 7) |
| 8. City coaching | 70 | ~45 (conditional) | Wave D (month 8+) |
| **Total** | **2,612** | **~1,255** | |

Add the 372 hand-written pages from [02](02-topical-map.md) and the 12-month target site size is
**~1,600 indexable pages** — enough to dominate the long tail of a niche this size, and small
enough to keep every page genuinely good.

**Do not chase 2,600.** 1,255 pages that all pass the gate will out-rank 2,600 where half are
thin, because the thin half drags the good half down.

---

## Technical implementation notes

**Rendering.** Every programmatic page must be statically generated (`generateStaticParams`) or
ISR-cached. Never client-rendered — see [01, P1](01-audit.md#p1-confirm-marketing-content-is-in-the-raw-html).
AI crawlers do not run JavaScript.

**Build time.** 1,300 pages of `generateStaticParams` will slow Vercel builds. Use ISR with
`revalidate` and `dynamicParams: true`, pre-rendering only the top ~200 by expected traffic.

**Data source.** Put the dimension data in Supabase, not in TypeScript files. You already have the
pattern wrong in `app/learn/articles.ts` (hard-coded) — do not repeat it at 1,300× scale. A
`seo_pages` table with `slug`, `template`, `dimensions jsonb`, `content jsonb`, `indexable bool`,
`updated_at` lets non-engineers add pages and lets the sitemap query `WHERE indexable = true`.

**Sitemaps.** One segmented sitemap per template via `generateSitemaps()`. This is how you
diagnose which template is failing to index.

**Internal linking.** Every programmatic page links: up to its hub, sideways to 4 siblings, and
out to 1 conversion page. Generate these links from the data model, not by hand.

**Content generation.** Use Claude to draft, but every page needs a human clinical review pass
before `indexable = true`. Wrong clinical content on a nursing site is a trust and liability
problem, not just an SEO one. Budget one reviewer-hour per 8 pages.

**Measurement.** Tag every programmatic URL with its template in PostHog. You need to answer
"which template produces paying subscribers" by month 4, and kill the ones that don't.
