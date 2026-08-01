// THESIS: a pricing page for a clinical exam product reads like a lab report,
// not a checkout page — restrained navy/ink, generous white space, Fraunces
// display serif carrying every number and headline, no gamified badges.
// OWN-WORLD: inherits the site's established system — navy #0F2356 + emerald
// #047857 accent, Fraunces display / Inter body, tinted "premium" shadows
// already defined in tailwind.config.ts. Nothing new invented here.
// STORY: a nurse compares four tiers, understands the outcome each buys
// (not a session count), and trusts the claims because none are invented.
// FIRST VIEWPORT: headline + one-line honest subhead, four cards below with
// Pro raised and softly lit — no hero metric, no fake stat band.
// FORM: extend of the existing pricing page; established world, not a new one.
import type { Metadata } from 'next'
import Link from 'next/link'
import {
  Check,
  Minus,
  Mic,
  Sparkles,
  Wand2,
  TrendingUp,
  Trophy,
  LifeBuoy,
  Stethoscope,
  ClipboardCheck,
  GraduationCap,
} from 'lucide-react'
import { FALLBACK_PLANS, type Plan } from '@/lib/plans'
import { SITE_URL, SITE_NAME } from '@/lib/site'
import { RevealOnScroll } from '@/components/RevealOnScroll'

export const metadata: Metadata = {
  title: 'Pricing — How Much Does OET Practice Cost?',
  description:
    'SpeakOET pricing: a free plan with 3 speaking sessions a month, then Basic, Pro, and Elite from ₹299/month. Compare Speaking, Writing, Reading, Listening and Mock Test access across every plan.',
  alternates: { canonical: '/pricing' },
}

// Flat approximate rate for the USD hint next to INR prices -- matches the
// rate already used in FAQSection.tsx and page.tsx so numbers agree site-wide.
const INR_TO_USD = 83

// Marketing framing for this page only -- outcome-led headline/subtitle and a
// short, curated feature list. Deliberately NOT stored on the shared Plan
// record in lib/plans.ts, because that record is also read by /upgrade (an
// in-app, already-a-user screen where "Explore SpeakOET" would read oddly)
// and by the homepage teaser. Facts (price, session count, gating) still
// come from FALLBACK_PLANS -- this only adds the sales voice on top.
interface PlanMarketing {
  headline: string
  subtitle: string
  includesNote?: string
  highlights: string[]
}

const PLAN_MARKETING: Record<string, PlanMarketing> = {
  free: {
    headline: 'Explore SpeakOET',
    subtitle: 'Experience AI-powered OET preparation before you upgrade.',
    highlights: [
      '3 AI speaking sessions / month',
      'Full 9-criteria AI scoring',
      'Realistic patient simulation',
      'Standard British voice',
    ],
  },
  basic: {
    headline: 'Build Strong Foundations',
    subtitle: 'Master Speaking, Reading and Listening with AI guidance.',
    includesNote: 'Everything in Free, plus:',
    highlights: [
      '20 Premium AI speaking sessions',
      'Reading & Listening practice',
      'Full 9-criteria AI scoring',
      'Track your progress — last 10 attempts',
    ],
  },
  pro: {
    headline: 'Complete OET Preparation',
    subtitle: 'Everything you need to prepare confidently for your exam.',
    includesNote: 'Everything in Basic, plus:',
    highlights: [
      '40 Premium AI speaking sessions',
      'AI Writing Evaluation',
      'Advanced AI Feedback',
      'Natural British Voice',
      'Unlimited progress history',
    ],
  },
  elite: {
    headline: 'Exam-Day Mastery',
    subtitle: 'The complete OET experience, with mock exams and pronunciation coaching.',
    highlights: [
      '80 Premium AI speaking sessions',
      'Full OET Exam Simulation',
      'Pronunciation Analysis',
      'AI Study Plan',
      'Everything in Pro',
    ],
  },
}

const PLAN_CTA: Record<string, string> = {
  free: 'Start Free',
  basic: 'Start Practicing',
  pro: 'Start Preparing',
  elite: 'Become Exam Ready',
}

// Mirrors backend/app/services/plan_gating.py (PREMIUM_PLANS, WRITING_PLANS,
// READING_PLANS, LISTENING_PLANS, MOCK_TEST_PLANS, PRONUNCIATION_PLANS,
// STUDY_PLAN_PLANS, get_history_limit) -- the actual gating source of truth.
// Update this table if that file changes. Grouped Practice / AI Feedback /
// Learning / Exam Readiness / Support, not one flat checklist.
type Cell = string | boolean
interface FeatureRow {
  label: string
  free: Cell
  basic: Cell
  pro: Cell
  elite: Cell
}
interface FeatureSection {
  title: string
  icon: typeof Mic
  rows: FeatureRow[]
}

const FEATURE_SECTIONS: FeatureSection[] = [
  {
    title: 'Practice',
    icon: Mic,
    rows: [
      { label: 'Premium AI speaking sessions / month', free: '3', basic: '20', pro: '40', elite: '80' },
      { label: 'Reading practice', free: false, basic: true, pro: true, elite: true },
      { label: 'Listening practice', free: false, basic: true, pro: true, elite: true },
      { label: 'AI Writing Evaluation (typed or handwritten)', free: false, basic: false, pro: true, elite: true },
    ],
  },
  {
    title: 'AI Feedback',
    icon: Wand2,
    rows: [
      { label: 'Full 9-criteria OET score', free: true, basic: true, pro: true, elite: true },
      { label: 'Advanced AI Feedback', free: false, basic: false, pro: true, elite: true },
      { label: 'Premium AI Conversation partner', free: false, basic: false, pro: true, elite: true },
      { label: 'Patient voice', free: 'Standard', basic: 'Standard', pro: 'Natural British', elite: 'Natural British' },
    ],
  },
  {
    title: 'Exam Readiness',
    icon: Trophy,
    rows: [
      { label: 'Full OET Exam Simulation (all 4 parts)', free: false, basic: false, pro: false, elite: true },
      { label: 'Pronunciation Analysis', free: false, basic: false, pro: false, elite: true },
      { label: 'AI Study Plan', free: false, basic: false, pro: false, elite: true },
    ],
  },
  {
    title: 'Learning',
    icon: TrendingUp,
    rows: [
      { label: 'Progress tracking dashboard', free: true, basic: true, pro: true, elite: true },
      { label: 'Track your progress (attempt history)', free: 'Last 3', basic: 'Last 10', pro: 'Unlimited', elite: 'Unlimited' },
    ],
  },
  {
    title: 'Support',
    icon: LifeBuoy,
    rows: [{ label: 'Support channel', free: 'Community', basic: 'Email', pro: 'Priority email', elite: 'WhatsApp priority' }],
  },
]

const TRUST_POINTS = [
  {
    icon: Stethoscope,
    title: 'Built specifically for OET',
    body: 'Not a general English app — every scenario, rubric, and voice is built around the OET Speaking, Writing, Reading and Listening sub-tests nurses actually sit.',
  },
  {
    icon: ClipboardCheck,
    title: 'Scored against the real rubric',
    body: "Speaking is scored on the same 9 criteria OET examiners use — Empathy, Fluency, Grammar & Expression, and the rest — not an app-invented scale.",
  },
  {
    icon: GraduationCap,
    title: 'No classroom required',
    body: 'A self-serve alternative to human tutors and coaching classes — practice on your own schedule, around shift work, from your phone or laptop.',
  },
]

const PRICING_FAQS = [
  {
    q: 'Which plan should I choose?',
    a: 'If you only need Speaking practice, start Free. If OET requires all four sub-tests for you, Basic covers Speaking, Reading and Listening. Pro adds Writing — the plan most candidates sitting the full exam choose. Elite adds the full Mock Test, Pronunciation Analysis and an AI Study Plan for the final weeks before your test date.',
  },
  {
    q: 'How does AI scoring work?',
    a: 'Speaking responses are scored against the same 9-criteria OET Speaking rubric examiners use (Empathy, Patient’s Perspective, Providing Structure, Information Gathering, Information Giving, Intelligibility, Fluency, Appropriateness of Language, and Grammar & Expression). Pro and Elite use a stronger AI model for richer, more detailed feedback on top of the same rubric.',
  },
  {
    q: 'How accurate is the scoring?',
    a: "SpeakOET is a preparation tool, not the official exam — your real OET result is always set by a human examiner. Our scoring is built to closely track the published rubric so the feedback is genuinely useful practice, but treat your band score here as strong guidance, not a guaranteed outcome.",
  },
  {
    q: 'Is my progress saved?',
    a: 'Yes. Every attempt, score, and piece of feedback is saved to your account and shown on your progress dashboard, up to your plan’s history limit — Last 3 on Free, Last 10 on Basic, and unlimited on Pro and Elite.',
  },
  {
    q: 'Can I cancel anytime?',
    a: "Yes, cancel anytime from your account settings — there's no lock-in contract. You keep access until the end of the billing period you've already paid for.",
  },
  {
    q: 'What payment methods do you accept?',
    a: 'Payments are handled securely by Razorpay. We accept UPI, credit and debit cards, and netbanking.',
  },
  {
    q: 'Do you offer refunds?',
    a: 'Refunds are handled case by case — email support@speakoet.com with your account details and we will take a look.',
  },
  {
    q: 'Do you offer discounts for coaching institutes or academies?',
    a: 'Yes. Contact support@speakoet.com for academy and bulk pricing — each student gets the full Elite plan.',
  },
]

const faqJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: PRICING_FAQS.map(({ q, a }) => ({
    '@type': 'Question',
    name: q,
    acceptedAnswer: { '@type': 'Answer', text: a },
  })),
}

const softwareApplicationJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: SITE_NAME,
  applicationCategory: 'EducationalApplication',
  operatingSystem: 'Web',
  url: `${SITE_URL}/pricing`,
  description: 'AI-powered OET exam preparation covering Speaking, Writing, Reading, and Listening for nurses.',
  offers: FALLBACK_PLANS.map((plan) => ({
    '@type': 'Offer',
    name: `${plan.name} Plan`,
    price: String(plan.price),
    priceCurrency: 'INR',
    url: `${SITE_URL}/pricing`,
    availability: 'https://schema.org/InStock',
  })),
}

function FeatureCell({ value }: { value: Cell }) {
  if (value === true) {
    return (
      <td className="px-5 py-3.5 text-center">
        <Check className="w-4 h-4 text-emerald-600 mx-auto" strokeWidth={3} aria-hidden="true" />
        <span className="sr-only">Included</span>
      </td>
    )
  }
  if (value === false) {
    return (
      <td className="px-5 py-3.5 text-center">
        <Minus className="w-4 h-4 text-gray-300 mx-auto" strokeWidth={3} aria-hidden="true" />
        <span className="sr-only">Not included</span>
      </td>
    )
  }
  return <td className="px-5 py-3.5 text-center text-gray-600">{value}</td>
}

function PriceTag({ plan }: { plan: Plan }) {
  return (
    <div className="mb-1 flex items-baseline gap-1.5">
      <span className="font-display text-4xl font-semibold text-[#0F2356] tracking-tight">
        {plan.price === 0 ? 'Free' : `₹${plan.price}`}
      </span>
      {plan.price > 0 && <span className="text-gray-600 text-sm">/{plan.period}</span>}
    </div>
  )
}

export default function PricingPage() {
  return (
    <main className="min-h-screen bg-white">
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

      {/* Hero */}
      <div className="max-w-3xl mx-auto px-4 pt-20 pb-14 text-center motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-4xl md:text-6xl font-semibold text-[#0F2356] text-balance leading-[1.05]">
          Pricing built for how you actually prepare
        </h1>
        <p className="text-gray-500 mt-5 text-lg leading-relaxed text-balance">
          Start free with 3 speaking sessions a month. Paid plans from ₹
          {FALLBACK_PLANS.find((p) => p.id === 'basic')!.price} (~$
          {Math.round(FALLBACK_PLANS.find((p) => p.id === 'basic')!.price / INR_TO_USD)}) a month unlock Reading,
          Listening, Writing, and the full OET Exam Simulation — no lock-in contract, cancel anytime.
        </p>
      </div>

      {/* Plan cards */}
      <div className="max-w-6xl mx-auto px-4 pb-24">
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {FALLBACK_PLANS.map((plan, i) => {
            const marketing = PLAN_MARKETING[plan.id]
            return (
              <RevealOnScroll key={plan.id} delayMs={Math.min(i, 4) * 40} className="block h-full">
              <div
                className={`relative rounded-3xl bg-white flex flex-col h-full motion-safe:transition-transform motion-safe:duration-300 ${
                  plan.highlight
                    ? 'border border-emerald-200 md:-translate-y-3'
                    : 'border border-gray-200 shadow-premium hover:-translate-y-1 hover:shadow-premium-lg'
                }`}
                style={
                  plan.highlight
                    ? {
                        boxShadow:
                          '0 2px 8px rgba(15,35,86,0.06), 0 32px 56px -16px rgba(4,120,87,0.28), 0 0 0 1px rgba(4,120,87,0.08)',
                      }
                    : undefined
                }
              >
                {plan.highlight && (
                  <span className="absolute -top-3.5 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 bg-[#0F2356] text-white text-xs font-semibold px-4 py-1.5 rounded-full shadow-premium">
                    <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
                    Most Popular
                  </span>
                )}
                <div className="p-8 flex flex-col flex-1">
                  <p className="text-sm font-semibold text-gray-500 mb-2">{plan.name}</p>
                  <h2 className="font-display text-xl font-semibold text-[#0F2356] mb-2 text-balance leading-snug min-h-[3.5rem]">
                    {marketing.headline}
                  </h2>
                  <p className="text-sm text-gray-500 mb-6 leading-relaxed min-h-[2.75rem]">{marketing.subtitle}</p>

                  <PriceTag plan={plan} />
                  {plan.price > 0 ? (
                    <p className="text-xs text-gray-600 mb-7">
                      ≈ ${Math.round(plan.price / INR_TO_USD)} USD/{plan.period}
                    </p>
                  ) : (
                    <p className="text-xs text-gray-600 mb-7">No credit card required</p>
                  )}

                  {marketing.includesNote && (
                    <p className="text-xs font-semibold text-gray-600 mb-3 uppercase tracking-wide">
                      {marketing.includesNote}
                    </p>
                  )}
                  <ul className="flex flex-col gap-3 mb-8 flex-1">
                    {marketing.highlights.map((f) => (
                      <li key={f} className="flex items-start gap-2.5 text-sm text-gray-600 leading-snug">
                        <Check className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" strokeWidth={3} aria-hidden="true" />
                        {f}
                      </li>
                    ))}
                  </ul>

                  <Link
                    href="/auth/register"
                    className={`block w-full text-center text-sm font-semibold px-6 py-3.5 rounded-xl motion-safe:transition-all motion-safe:duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2 ${
                      plan.highlight
                        ? 'bg-[#047857] text-white hover:bg-[#036546] hover:shadow-premium-lg'
                        : 'bg-transparent text-[#0F2356] border border-gray-200 hover:border-[#0F2356]/30 hover:bg-[#0F2356]/[0.03]'
                    }`}
                  >
                    {PLAN_CTA[plan.id]}
                  </Link>
                </div>
              </div>
              </RevealOnScroll>
            )
          })}
        </div>
      </div>

      {/* Trust */}
      <div className="border-y border-gray-100 bg-[#F8FAFC]">
        <div className="max-w-5xl mx-auto px-4 py-16">
          <div className="grid sm:grid-cols-3 gap-10">
            {TRUST_POINTS.map(({ icon: Icon, title, body }, i) => (
              <RevealOnScroll key={title} delayMs={Math.min(i, 4) * 40}>
                <Icon className="w-6 h-6 text-[#047857] mb-4" strokeWidth={1.75} aria-hidden="true" />
                <h3 className="font-display text-base font-semibold text-[#0F2356] mb-2">{title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{body}</p>
              </RevealOnScroll>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 py-24">
        {/* Comparison table */}
        <div className="mb-24">
          <h2 className="font-display text-2xl md:text-3xl font-semibold text-[#0F2356] text-center mb-3">
            Compare every plan
          </h2>
          <p className="text-gray-500 text-center mb-10 max-w-xl mx-auto">
            Every plan scores against the same real OET rubric — higher tiers unlock more sub-tests, deeper
            feedback, and exam-day simulation.
          </p>
          <RevealOnScroll className="block relative rounded-3xl border border-gray-200 shadow-premium bg-white">
            <div className="overflow-x-auto rounded-3xl">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="border-b border-gray-200">
                  <th scope="col" className="px-5 py-4 text-left font-semibold text-[#0F2356] w-[38%]">
                    Feature
                  </th>
                  {FALLBACK_PLANS.map((plan) => (
                    <th
                      key={plan.id}
                      scope="col"
                      className={`px-5 py-4 text-center font-semibold ${
                        plan.highlight ? 'text-[#047857]' : 'text-[#0F2356]'
                      }`}
                    >
                      {plan.name}
                    </th>
                  ))}
                </tr>
              </thead>
              {FEATURE_SECTIONS.map((section) => (
                <tbody key={section.title}>
                  <tr className="bg-[#0F2356]/[0.04]">
                    <th
                      colSpan={5}
                      scope="colgroup"
                      className="px-5 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-[#0F2356]"
                    >
                      <span className="inline-flex items-center gap-2">
                        <section.icon className="w-3.5 h-3.5" aria-hidden="true" />
                        {section.title}
                      </span>
                    </th>
                  </tr>
                  {section.rows.map((row) => (
                    <tr key={row.label} className="border-b border-gray-100 last:border-0 hover:bg-gray-50/60 motion-safe:transition-colors">
                      <th scope="row" className="px-5 py-3.5 text-left font-medium text-gray-700">
                        {row.label}
                      </th>
                      <FeatureCell value={row.free} />
                      <FeatureCell value={row.basic} />
                      <FeatureCell value={row.pro} />
                      <FeatureCell value={row.elite} />
                    </tr>
                  ))}
                </tbody>
              ))}
            </table>
            </div>
            <div
              aria-hidden="true"
              className="absolute top-0 right-0 bottom-0 w-10 bg-gradient-to-l from-white to-transparent pointer-events-none rounded-r-3xl sm:hidden"
            />
          </RevealOnScroll>
        </div>

        {/* FAQ */}
        <div className="max-w-3xl mx-auto">
          <h2 className="font-display text-2xl md:text-3xl font-semibold text-[#0F2356] text-center mb-10">
            Pricing questions
          </h2>
          <div className="flex flex-col gap-3">
            {PRICING_FAQS.map((faq, i) => (
              <RevealOnScroll key={faq.q} delayMs={Math.min(i, 4) * 40}>
                <details className="group rounded-2xl border border-gray-200 bg-white open:shadow-premium open:border-[#0F2356]/15 motion-safe:transition-shadow">
                  <summary className="cursor-pointer list-none flex items-center justify-between gap-4 px-6 py-5 font-semibold text-[#0F2356] rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
                    {faq.q}
                    <span className="shrink-0 text-gray-400 motion-safe:transition-transform motion-safe:duration-200 group-open:rotate-45 text-xl leading-none">
                      +
                    </span>
                  </summary>
                  <p className="px-6 pb-5 text-gray-600 text-sm leading-relaxed">{faq.a}</p>
                </details>
              </RevealOnScroll>
            ))}
          </div>
        </div>

        {/* Closing CTA */}
        <RevealOnScroll className="block max-w-3xl mx-auto mt-24 text-center rounded-3xl bg-[#0F2356] px-8 py-14">
          <h2 className="font-display text-2xl md:text-3xl font-semibold text-white mb-3 text-balance">
            Start preparing with confidence
          </h2>
          <p className="text-white/70 mb-8 max-w-md mx-auto">
            Free to start, no credit card required. Upgrade whenever you're ready for the full syllabus.
          </p>
          <Link
            href="/auth/register"
            className="inline-block bg-[#047857] text-white font-semibold px-8 py-3.5 rounded-xl hover:bg-[#036546] motion-safe:transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-[#0F2356]"
          >
            Start Free
          </Link>
        </RevealOnScroll>
      </div>
    </main>
  )
}
