import type { Metadata } from 'next'
import Link from 'next/link'
import { StartFreeMock } from './StartFreeMock'
import { SITE_URL, SITE_NAME } from '@/lib/site'
import { RevealOnScroll } from '@/components/RevealOnScroll'

const SECTIONS = [
  { label: 'Listening', time: '~40 min', blurb: 'Three parts. Each recording plays once, just like the real exam.' },
  { label: 'Reading', time: '60 min', blurb: 'Part A (15 min) then Parts B & C (45 min).' },
  { label: 'Writing', time: '40 min', blurb: 'A referral or discharge letter, scored against the real 6-criteria rubric.' },
  { label: 'Speaking', time: '~20 min', blurb: 'Two role plays with an AI patient, scored live.' },
]

const FAQS = [
  {
    q: 'Is this really free? Do I need to sign up?',
    a: 'Yes — the full mock test is free and you can start it with no account. You\'ll see your raw score for each of the four sub-tests (Listening, Reading, Writing, Speaking) as soon as you finish. Creating a free account only unlocks the fuller band report afterwards.',
  },
  {
    q: 'What do I get without signing up?',
    a: 'Your raw score for every sub-test — e.g. your Listening band and how many questions you got right, your Writing grade and numeric score, your Speaking band. That\'s the same score data the real test reports, just without the extra breakdown.',
  },
  {
    q: 'What does creating a free account unlock?',
    a: 'A fuller report: which of your four sub-tests is comparatively weakest, a free 4-week study plan targeted at it, and a link to check your scores against your specific nursing regulator\'s requirements.',
  },
  {
    q: 'How is Writing and Speaking scored?',
    a: 'By the same AI scoring engine used across SpeakOET — Writing against the official 6-criteria rubric, Speaking against the 9 OET Speaking criteria — the identical scoring your letter or role play would get in paid practice.',
  },
  {
    q: 'Can I take it more than once?',
    a: 'The free, no-signup version is one attempt. Create a free account (or subscribe) for unlimited mock tests.',
  },
  {
    q: 'Is this an official OET mock test?',
    a: 'No. This is an independent practice tool built by SpeakOET, scored by AI against OET\'s published rubrics. OET is a registered trademark of Cambridge Boxhill Language Assessment; we are not affiliated with or endorsed by OET.',
  },
]

export const metadata: Metadata = {
  title: 'Free OET Mock Test Online — Full Scored Practice, No Signup',
  description:
    'Take a complete, timed OET mock test — Listening, Reading, Writing, and Speaking — free, with no signup. See your raw score for every sub-test as soon as you finish.',
  alternates: { canonical: '/tools/oet-mock-test-free' },
}

const faqJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: FAQS.map(({ q, a }) => ({
    '@type': 'Question',
    name: q,
    acceptedAnswer: { '@type': 'Answer', text: a },
  })),
}

const softwareApplicationJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: `Free OET Mock Test by ${SITE_NAME}`,
  applicationCategory: 'EducationalApplication',
  operatingSystem: 'Web',
  url: `${SITE_URL}/tools/oet-mock-test-free`,
  description: 'Free, no-signup, full four-skill OET mock test scored by AI.',
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'INR' },
}

export default function OetMockTestFreePage() {
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
        <div className="text-center mb-10 motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-600">
            Free · No signup to start
          </p>
          <h1 className="mt-2 font-display text-4xl md:text-5xl font-semibold text-[#0F2356] text-balance">
            Free OET Mock Test
          </h1>
          <p className="text-gray-500 mt-4 text-lg max-w-2xl mx-auto">
            One complete, timed OET sitting — Listening, Reading, Writing, and Speaking — scored by
            the same AI engine as our paid practice. See your raw score for every sub-test the
            moment you finish, no account needed.
          </p>
        </div>

        <div className="max-w-2xl mx-auto">
          <StartFreeMock />
        </div>

        <div className="max-w-2xl mx-auto mt-10">
          <div className="rounded-2xl overflow-hidden border border-gray-100 shadow-premium bg-white">
            {SECTIONS.map((s, i) => (
              <RevealOnScroll key={s.label} delayMs={Math.min(i, 4) * 40} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                <div className="px-6 py-4 flex items-center justify-between gap-4">
                  <div>
                    <p className="font-semibold text-gray-900">{s.label}</p>
                    <p className="text-[13px] text-gray-500 mt-0.5">{s.blurb}</p>
                  </div>
                  <span className="shrink-0 tabular-nums text-sm font-semibold text-gray-700">{s.time}</span>
                </div>
              </RevealOnScroll>
            ))}
          </div>
        </div>

        <div className="max-w-3xl mx-auto mt-16">
          <h2 className="font-display text-2xl md:text-3xl font-semibold text-[#0F2356] text-center mb-8">
            Free Mock Test Questions
          </h2>
          <div className="rounded-2xl overflow-hidden border border-gray-100 shadow-premium bg-white">
            {FAQS.map((faq, i) => (
              <RevealOnScroll key={faq.q} delayMs={Math.min(i, 4) * 40} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                <div className="px-6 py-5">
                  <h3 className="text-[#0F2356] font-semibold text-sm md:text-base leading-snug mb-2">
                    {faq.q}
                  </h3>
                  <p className="text-gray-600 text-sm leading-relaxed">{faq.a}</p>
                </div>
                {i < FAQS.length - 1 && <div className="border-b border-gray-100" />}
              </RevealOnScroll>
            ))}
          </div>
          <p className="text-center text-sm text-gray-500 mt-6">
            Want to check a score against your regulator first? Try the{' '}
            <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
              OET Score Calculator
            </Link>
            .
          </p>
        </div>
      </div>
    </main>
  )
}
