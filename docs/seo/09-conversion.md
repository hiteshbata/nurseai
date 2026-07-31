# 09 — Conversion-Focused SEO

## The premise

Traffic that does not convert is a cost, not an asset — you pay for it in content hours and it
returns nothing. Every page in [02](02-topical-map.md) must have a defined job in the funnel before
it is written.

**Your buyer's state of mind, which dictates every CTA below:** a nurse with a booked test date, a
visa timeline, family expectations, and a real fear of failing an exam that stands between them and
a career abroad. They are anxious, time-poor, on a phone, and price-sensitive but not cheap — they
will pay for confidence. **Sell diagnosis and reassurance, not features.**

The single most effective CTA pattern in this market is therefore not "Start free trial" but
**"Find out if you're ready"** — because that is the question keeping them awake.

---

## The funnel

```
Informational (grammar, vocab, careers)     → email capture, no sale attempt
Comparative  (vs IELTS, alternatives)       → free tool, then trial
Diagnostic   (scores, requirements, retake) → free mock/checker → account
Commercial   (pricing, landings, coaching)  → paid conversion
```

Do not put a hard sale on an informational page — it converts nothing and damages the page's
engagement metrics. Do not put a soft email capture on a pricing page — you have the buyer, ask
for the sale.

---

## Page-type conversion specs

### 1. Pillar pages (`/oet/speaking/`, `/oet/writing/`, …)

| | |
|---|---|
| **Primary CTA** | "Practise this free — no card needed" → embedded live product widget on the page itself |
| **Secondary CTA** | "Get the free 30-day study plan" → email capture |
| **Internal links** | All cluster children; the matching product landing; `/pricing` |
| **Lead magnet** | Sub-test-specific checklist PDF ("12-point OET Writing checklist") |
| **Conversion notes** | The pillar must *contain* the product, not link to it. A nurse who completes one AI role-play on the page converts at multiples of one who reads about it. Put the widget above the fold, after the 50-word answer paragraph. |

### 2. Supporting articles (`/learn/*`)

| | |
|---|---|
| **Primary CTA** | Contextual, mid-article, matched to the exact topic: on `/learn/oet-writing-criteria` → "Get your own letter scored against these 6 criteria — free" |
| **Secondary CTA** | Related-article links (keeps the session alive; session depth correlates with signup) |
| **Internal links** | 1 pillar (up), 3 siblings (sideways), 1 conversion page |
| **Lead magnet** | Topic-matched download, gated by email only |
| **Conversion notes** | One inline CTA after the first substantive section, one at the end. Never a popup on the first 15 seconds — bounce cost exceeds capture gain on mobile 4G. Trigger exit-intent or 60%-scroll instead. |

### 3. Country / regulator pages (`/oet/uk`, `/oet/india`)

Highest-intent pages you own. Treat them as landing pages that happen to be informative.

| | |
|---|---|
| **Primary CTA** | "Check if you're ready for the NMC's B grade — free 10-minute assessment" → `/tools/oet-readiness-quiz` |
| **Secondary CTA** | "See plans" → `/pricing` (with local currency pre-selected by country) |
| **Internal links** | 3 sibling countries; the relevant registration guide; all 4 sub-test landings |
| **Lead magnet** | Country-specific PDF: "The complete UK NMC pathway for Indian nurses — every step, fee and timeline" |
| **Conversion notes** | Show price in local currency on these pages. A ₹ price on `/oet/india` converts materially better than a $ price. Add a country-matched testimonial ("Anitha, Kochi — 350 → 400 in Writing"). Social proof from the reader's own country outperforms generic proof by a wide margin. |

### 4. Score / requirement pages (`/oet/scores/*`)

| | |
|---|---|
| **Primary CTA** | "Calculate your band" → `/tools/oet-score-calculator` |
| **Secondary CTA** | "Take a free scored mock test" |
| **Internal links** | Score calculator; the sub-test the reader is weakest in; `/pricing` |
| **Lead magnet** | Score-conversion chart PDF |
| **Conversion notes** | These readers are diagnosing a problem. The calculator result is the conversion moment: **"Your Writing is 30 points below the NMC requirement. Here's the 4-week plan to close it."** That sentence, generated from their own numbers, is the highest-converting string on the site. Build the tool to produce it. |

### 5. Free tools (`/tools/*`)

| | |
|---|---|
| **Primary CTA** | Show the result **first**, then: "Save your result and get a personalised plan" → account creation |
| **Secondary CTA** | "Practise your weakest area now" → product |
| **Internal links** | Related tools; the pillar for the weakest area identified |
| **Lead magnet** | The tool *is* the lead magnet |
| **Conversion notes** | **Never gate before value.** Gating the result kills 70%+ of completions and the links you wanted. Gate the *extras*: the emailed PDF, saving history, the detailed breakdown. Add an embeddable widget with attribution for links ([07](07-digital-pr.md)). |

### 6. Free mock test (`/tools/oet-mock-test-free`)

Your single strongest conversion asset. Spec it deliberately.

| | |
|---|---|
| **Primary CTA** | After completion: "Get your full band report + per-criterion feedback" → free account |
| **Secondary CTA** | "Practise your weakest sub-test" → targeted product page |
| **Lead magnet** | The band report itself |
| **Conversion notes** | Show *raw* sub-test scores free — enough that the result feels real and the value is proven. Gate the band conversion, the per-criterion breakdown, and the improvement plan. The gap between "I scored 28/42 in Listening" and "what does that mean for my NMC application" is the exact moment they create an account. Then: immediate, contextual upgrade prompt while the anxiety is fresh — not a drip email three days later. Rate-limit and cost-cap the AI calls (reuse existing rate-limit middleware) or this becomes an unmetered expense. |

### 7. Product landing pages (`/oet-speaking-practice`, …)

| | |
|---|---|
| **Primary CTA** | "Start practising free" → signup, repeated 3× down the page |
| **Secondary CTA** | "Watch a 60-second demo" |
| **Internal links** | Pillar; 3 supporting articles; `/pricing`; `/success-stories` |
| **Lead magnet** | None — do not divert a commercial-intent visitor into an email sequence. Ask for the account. |
| **Conversion notes** | Above the fold: what it does, who it's for, a real product screenshot or embedded demo, and the price. Do not hide pricing — price-hiding on a $15–30/mo product just adds friction. Include 3 named testimonials with before/after band scores and country. Address the objection explicitly: "Can AI really score OET Writing?" → show the criteria mapping and a scored sample. |

### 8. Comparison pages (`/compare/*`)

| | |
|---|---|
| **Primary CTA** | "Try SpeakOET free" |
| **Secondary CTA** | Feature-comparison table anchor link |
| **Internal links** | `/pricing`; the sub-test landings; `/success-stories` |
| **Lead magnet** | None — closest-to-purchase traffic on the site |
| **Conversion notes** | **Be scrupulously fair.** State what the competitor does better (E2 has live human teachers; Swoosh has a stronger community). Fairness converts better than advocacy because the reader is already sceptical, and it protects you legally and reputationally. Win on the axes you actually win: instant feedback, price, nurse-specific specialty depth, 24/7 availability. |

### 9. Pricing page (`/pricing`)

| | |
|---|---|
| **Primary CTA** | "Start free" on every tier |
| **Secondary CTA** | "Try a free mock test first" — catches the not-ready-yet visitor instead of losing them |
| **Internal links** | `/success-stories`; `/how-it-works`; FAQ |
| **Conversion notes** | Local currency by region with a manual switch. Annual plan positioned against the OET exam fee itself — "less than one OET retake" is the most persuasive frame available, because a retake costs roughly what an annual subscription does and they know it. Money-back guarantee if you can support it: a "pass or refund" style guarantee is extremely powerful in exam prep and reduces the perceived risk that blocks most purchases. 10 FAQs with schema, covering refunds, plan switching, free-tier limits, and payment methods (UPI matters enormously in India — say so explicitly). |

### 10. Programmatic role-play pages (`/oet/speaking/role-play/*`)

| | |
|---|---|
| **Primary CTA** | "Start this role-play free" — the widget on the page |
| **Secondary CTA** | "See all cardiology role-plays" → specialty hub |
| **Internal links** | Specialty hub; 4 sibling scenarios; speaking pillar; `/pricing` |
| **Conversion notes** | Allow 1–2 free role-plays per visitor, then gate. The searcher arrived wanting to *do* this exact thing — the friction budget is near zero. Do not ask for an email before they experience it. |

### 11. Programmatic writing-sample pages (`/oet/writing/sample/*`)

| | |
|---|---|
| **Primary CTA** | "Get your version of this letter scored free" |
| **Secondary CTA** | "See the band-C version and what went wrong" |
| **Internal links** | Letter-type hub; 4 sibling specialties; writing pillar |
| **Lead magnet** | Downloadable case-note pack |
| **Conversion notes** | Highest commercial intent of any programmatic page. The reader is comparing their own letter to yours right now. One free scored submission converts hard. |

### 12. Careers / post-OET pages (`/careers/*`)

| | |
|---|---|
| **Primary CTA** | "Not passed OET yet? Start free" |
| **Secondary CTA** | Email list for the registration-guide series |
| **Internal links** | OET pillars; country pages |
| **Conversion notes** | Mixed audience — some have passed, some haven't. Segment with a single question early on the page ("Have you taken OET yet?") and route accordingly. Those who passed still matter: they are your referral engine and your testimonial source. Ask them for a review, not a sale. |

### 13. Grammar / vocabulary / nursing-English pages

| | |
|---|---|
| **Primary CTA** | Email capture only: "Get 500 OET vocabulary words as flashcards" |
| **Secondary CTA** | Link to the relevant sub-test pillar |
| **Conversion notes** | Lowest intent on the site. Do not waste a hard sale here. Job: topical authority, AI citations, and email addresses to nurture. Accept a 0.5% direct conversion rate and measure these pages on *assisted* conversions instead. |

---

## Cross-site conversion infrastructure

**1. Exit-intent / 60%-scroll offer, topic-matched.** One offer per cluster, not a site-wide
generic popup. Writing cluster → writing checklist. Never fires in the first 20 seconds or on
mobile scroll-up.

**2. Sticky mobile CTA bar.** Your traffic is overwhelmingly mobile. One persistent bottom bar,
text matched to the page cluster, dismissible. This alone typically lifts mobile conversion
30–50%.

**3. Email nurture, 7 emails over 14 days.** Sequenced by the cluster they entered from. Day 1
deliver the magnet, day 2 the single most useful tip, day 4 a mistake-focused email, day 6 a
testimonial, day 8 a free-mock invitation, day 11 an objection-handler, day 14 a limited discount.
Exam prep has a hard deadline — urgency is real here, not manufactured.

**4. Exam-date capture.** Ask for the test date at signup. It is the single most valuable field you
can collect: it determines urgency, the study plan, and the entire email cadence. A nurse 3 weeks
out gets a different sequence — and a different offer — than one 6 months out.

**5. Currency and country detection.** Show ₹ to Indian visitors, ₱ to Filipino, £ to UK. Trivial
to implement, material conversion impact.

**6. Referral prompt at the win moment.** You already have `/refer`. Trigger the prompt when a user
sees a score *improvement*, not at signup. Nurses prepare in cohorts and WhatsApp groups — this is
the highest-leverage loop you own.

**7. Attribution.** PostHog: first-touch landing page → signup → paid, per page. By month 4 you
must be able to name the 10 pages producing paying subscribers, and stop writing the kind that
don't.

---

## Realistic conversion benchmarks

| Page type | Visitor → signup | Signup → paid |
|---|---|---|
| Free mock test | 25–40% | 10–15% |
| Free tools | 12–20% | 8–12% |
| Country/regulator pages | 8–12% | 8–12% |
| Score/requirement pages | 6–10% | 8–10% |
| Product landings | 10–15% | 12–18% |
| Comparison pages | 8–12% | 15–20% |
| Programmatic writing samples | 6–10% | 8–12% |
| Programmatic role-plays | 5–8% | 6–10% |
| Supporting articles | 3–6% | 5–8% |
| Grammar/vocabulary | 1–2% | 3–5% |

**Blended site target: ~5% visitor→signup, ~8% signup→paid = 0.4% visitor→paid.** Every 0.1%
improvement on the blended rate is worth roughly 25% more subscribers at constant traffic — which
is why the Q4 conversion-optimisation work in [06](06-content-calendar.md) matters as much as
another 300 pages.
