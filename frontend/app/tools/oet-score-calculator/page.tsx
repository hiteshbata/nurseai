import type { Metadata } from 'next'
import { Suspense } from 'react'
import Link from 'next/link'
import { ScoreCalculator } from './ScoreCalculator'
import { REGULATORS, US_STATES_NOT_LISTED, scoreToGrade, gradeToFloorScore } from '@/lib/oetScoring'
import { SITE_URL, SITE_NAME } from '@/lib/site'

const countryNames = Array.from(new Set(REGULATORS.map((r) => r.country)))
const countryCount = countryNames.length
const usStateCount = REGULATORS.filter((r) => r.id.startsWith('us-') && r.id !== 'us-trumerit').length

const gradeBFloor = gradeToFloorScore('B')
const gradeBCeiling = gradeToFloorScore('A') - 10
const gradeCPlusFloor = gradeToFloorScore('C+')
const regulatorsClearedAt300 = REGULATORS.filter((r) =>
  Object.values(r.requirements).every((req) => req <= 300)
).length

const SCORE_MEANING_FAQS = [
  {
    q: 'What does a score of 350 mean?',
    a: `350 is Grade ${scoreToGrade(350)} on OET's 0-500 scale — the minimum most nursing regulators worldwide (NMC, Ahpra, NMBI, and others) ask for on each individual sub-test. It's a per-sub-test bar, not an average: you need 350 (or your regulator's minimum) on every one of Listening, Reading, Writing, and Speaking, not just overall.`,
  },
  {
    q: 'What is Grade B?',
    a: `Grade B covers numeric scores from ${gradeBFloor} to ${gradeBCeiling} out of 500 — one band below the top grade, Grade A (${gradeToFloorScore('A')}+). It's the level most regulators on this page ask for in Listening, Reading, and Speaking; Writing is often set one band lower, at Grade C+ (${gradeCPlusFloor}+).`,
  },
  {
    q: 'Is 300 enough?',
    a: `Depends entirely on your target. A flat 300 across all four sub-tests — Grade ${scoreToGrade(300)} — clears ${regulatorsClearedAt300} of the ${REGULATORS.length} regulators checked by this calculator (mostly individual U.S. state boards), but falls short of NMC, Ahpra, NMBI, and most others, which ask for 350. Enter your scores above against your specific target for a definite answer.`,
  },
  {
    q: 'Which countries accept my score?',
    a: `This calculator checks nursing regulators across ${countryCount} countries: ${countryNames.join(', ')}. OET is recognised more broadly than that — other countries, and 11 other healthcare professions beyond nursing — but we only publish a pass/fail number here where we could confirm the exact figure from a primary source. See OET's own "who recognises OET" directory for the full list.`,
  },
  {
    q: 'Which professions require which scores?',
    a: "This tool is built specifically for nurses, so every requirement above is a nursing regulator's. OET also serves 11 other healthcare professions (medicine, dentistry, physiotherapy, pharmacy, and more) — their regulators often ask for a similar grade (commonly Grade B) but set their own number independently, so check your profession's own regulator rather than assuming these nursing figures apply.",
  },
  {
    q: 'How can I increase my Speaking score from 330 to 350?',
    a: 'Enter 330 for Speaking above against your target regulator and the calculator will generate a free 4-week Speaking study plan automatically. In general, a 20-point Speaking gap closes with repeated recorded role-plays scored against the real criteria — empathy, structure, information-gathering — not more reading about the exam. It\'s a performance skill.',
  },
  {
    q: 'How long is an OET score valid?',
    a: "OET itself doesn't expire, but each regulator sets its own acceptance window for how old a result can be when you submit your application — commonly around two years for most nursing regulators, though this varies and changes without notice. Confirm the current validity period on your target regulator's own site (linked in the results table above) before relying on an older result.",
  },
]

export const metadata: Metadata = {
  title: 'OET Score Calculator — Check Your Band & Regulator Pass/Fail',
  description: `Enter your OET Listening, Reading, Writing, and Speaking grades or numeric scores and instantly check pass/fail against NMC, Ahpra, NMBI, ${usStateCount} US state nursing boards, and more. Free, no signup.`,
  alternates: { canonical: '/tools/oet-score-calculator' },
}

const FAQS = [
  {
    q: 'Is this an official OET score calculator?',
    a: 'No. This is an independent study tool built by SpeakOET. OET is a registered trademark of Cambridge Boxhill Language Assessment. We are not affiliated with or endorsed by OET or by any of the regulators listed here.',
  },
  {
    q: 'How accurate is the pass/fail check?',
    a: "It compares your score against each regulator's publicly published minimum, using OET's own published A-E grade scale (450/350/300/200/100). Regulators change their requirements over time, so always confirm the current pass mark on the regulator's own site before you rely on it.",
  },
  {
    q: 'What if I only know my grade, not my exact score?',
    a: 'A grade covers a range of scores (e.g. Grade B is 350-440). If a regulator\'s requirement doesn\'t line up exactly with a grade boundary, a grade alone can\'t prove a pass or fail — that result is marked borderline, so switch to "I have numbers" and enter your exact score for a precise check. None of the regulators currently listed require more precision than a grade, but the check is there in case one does.',
  },
  {
    q: 'Which regulators are covered?',
    a: `${countryCount} countries: NMC (UK), Ahpra/NMBA (Australia), NMBI (Ireland), Nursing Council (New Zealand), Canada's 13 provincial/territorial nursing regulators (identical across every one), plus TruMerit/CGFNS and ${usStateCount} individual U.S. state nursing boards. ${US_STATES_NOT_LISTED} We deliberately left out UAE licensing bodies (DHA/DOH/MOH) — public sources conflicted and requirements aren't uniform across emirates. Singapore (SNB) and Malta (CNM) are left out for the same reason: no primary-source data pulled for them yet.`,
  },
  {
    q: 'Can I combine scores from two OET sittings?',
    a: "Several regulators allow combining results from two sittings within a set window (commonly 6-12 months) if you meet the minimum in every sub-test across the two attempts. This calculator only checks a single sitting's scores — check your target regulator's own combining rules for the exact conditions.",
  },
  {
    q: 'Is my data saved or shared anywhere?',
    a: 'No. The calculation runs entirely in your browser. Nothing is sent to a server or stored — the "copy link" option just puts your scores in the URL so you can reopen or share that specific result.',
  },
]

const faqJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: [...SCORE_MEANING_FAQS, ...FAQS].map(({ q, a }) => ({
    '@type': 'Question',
    name: q,
    acceptedAnswer: { '@type': 'Answer', text: a },
  })),
}

const softwareApplicationJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: `OET Score Calculator by ${SITE_NAME}`,
  applicationCategory: 'EducationalApplication',
  operatingSystem: 'Web',
  url: `${SITE_URL}/tools/oet-score-calculator`,
  description: 'Free OET band score and regulator pass/fail calculator for nurses.',
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'INR' },
}

export default function OetScoreCalculatorPage() {
  return (
    <main className="min-h-screen bg-gray-50">
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
      />
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareApplicationJsonLd) }}
      />

      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="text-center mb-10">
          <h1 className="text-4xl md:text-5xl font-bold text-[#0F2356] text-balance">
            OET Score Calculator
          </h1>
          <p className="text-gray-500 mt-4 text-lg max-w-2xl mx-auto">
            Enter your grades or numeric scores and check pass/fail against {countryCount} countries —
            NMC, Ahpra, NMBI, all 13 Canadian nursing regulators, and {usStateCount} individual U.S.
            state boards. Free, no signup, nothing saved.
          </p>
        </div>

        <Suspense fallback={<div className="text-center text-muted-foreground">Loading calculator…</div>}>
          <ScoreCalculator />
        </Suspense>

        <div className="max-w-3xl mx-auto mt-16">
          <h2 className="text-2xl md:text-3xl font-bold text-[#0F2356] text-center mb-8">
            Understanding Your Score
          </h2>
          <div className="rounded-2xl overflow-hidden border border-gray-100 shadow-sm bg-white">
            {SCORE_MEANING_FAQS.map((faq, i) => (
              <div key={faq.q} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                <div className="px-6 py-5">
                  <h3 className="text-[#0F2356] font-semibold text-sm md:text-base leading-snug mb-2">
                    {faq.q}
                  </h3>
                  <p className="text-gray-600 text-sm leading-relaxed">{faq.a}</p>
                </div>
                {i < SCORE_MEANING_FAQS.length - 1 && <div className="border-b border-gray-100" />}
              </div>
            ))}
          </div>
          <p className="text-center text-sm text-gray-500 mt-6">
            Want the full picture? Read{' '}
            <Link href="/learn/oet-band-scores" className="text-[#0F2356] font-semibold underline">
              OET Band Scores Explained
            </Link>{' '}
            or start{' '}
            <Link href="/practice/speaking" className="text-[#0F2356] font-semibold underline">
              Speaking practice
            </Link>
            .
          </p>
        </div>

        <div className="max-w-3xl mx-auto mt-16">
          <h2 className="text-2xl md:text-3xl font-bold text-[#0F2356] text-center mb-8">
            Calculator Questions
          </h2>
          <div className="rounded-2xl overflow-hidden border border-gray-100 shadow-sm bg-white">
            {FAQS.map((faq, i) => (
              <div key={faq.q} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                <div className="px-6 py-5">
                  <h3 className="text-[#0F2356] font-semibold text-sm md:text-base leading-snug mb-2">
                    {faq.q}
                  </h3>
                  <p className="text-gray-600 text-sm leading-relaxed">{faq.a}</p>
                </div>
                {i < FAQS.length - 1 && <div className="border-b border-gray-100" />}
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  )
}
