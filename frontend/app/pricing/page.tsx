import type { Metadata } from 'next'
import Link from 'next/link'
import { Check, Minus, Mic, Sparkles, TrendingUp, LifeBuoy } from 'lucide-react'
import { FALLBACK_PLANS } from '@/lib/plans'
import { SITE_URL, SITE_NAME } from '@/lib/site'

export const metadata: Metadata = {
  title: 'Pricing — How Much Does OET Practice Cost?',
  description:
    'SpeakOET pricing: a free plan with 3 speaking sessions a month, then Basic, Pro, and Elite from ₹299/month. Compare Speaking, Writing, Reading, Listening and Mock Test access across every plan.',
  alternates: { canonical: '/pricing' },
}

// Flat approximate rate for the USD hint next to INR prices -- matches the
// rate already used in FAQSection.tsx and page.tsx so numbers agree site-wide.
const INR_TO_USD = 83

// Mirrors backend/app/services/plan_gating.py (PREMIUM_PLANS, WRITING_PLANS,
// READING_PLANS, LISTENING_PLANS, MOCK_TEST_PLANS, PRONUNCIATION_PLANS,
// STUDY_PLAN_PLANS, get_history_limit) -- the actual gating source of truth.
// Update this table if that file changes.
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
      { label: 'Speaking sessions per month', free: '3', basic: '20', pro: '40', elite: '80' },
      { label: 'Reading practice', free: false, basic: true, pro: true, elite: true },
      { label: 'Listening practice', free: false, basic: true, pro: true, elite: true },
      { label: 'Writing practice', free: false, basic: false, pro: true, elite: true },
      { label: 'Full Mock Test (all 4 parts)', free: false, basic: false, pro: false, elite: true },
    ],
  },
  {
    title: 'AI Feedback',
    icon: Sparkles,
    rows: [
      { label: 'Full 9-criteria OET score', free: true, basic: true, pro: true, elite: true },
      { label: 'Advanced AI feedback', free: false, basic: false, pro: true, elite: true },
      { label: 'Premium AI conversation partner', free: false, basic: false, pro: true, elite: true },
      { label: 'Patient voice', free: 'Standard', basic: 'Standard', pro: 'Natural British', elite: 'Natural British' },
      { label: 'Handwriting OCR for Writing', free: false, basic: false, pro: true, elite: true },
      { label: 'Pronunciation analysis', free: false, basic: false, pro: false, elite: true },
      { label: 'AI-generated study plan', free: false, basic: false, pro: false, elite: true },
    ],
  },
  {
    title: 'Progress',
    icon: TrendingUp,
    rows: [
      { label: 'Progress tracking dashboard', free: true, basic: true, pro: true, elite: true },
      { label: 'Attempt history', free: 'Last 3', basic: 'Last 10', pro: 'Unlimited', elite: 'Unlimited' },
    ],
  },
  {
    title: 'Support',
    icon: LifeBuoy,
    rows: [
      { label: 'Support channel', free: 'Community', basic: 'Email', pro: 'Priority email', elite: 'WhatsApp priority' },
    ],
  },
]

const PRICING_FAQS = [
  {
    q: 'How much does SpeakOET cost?',
    a: `SpeakOET has a free plan with ${FALLBACK_PLANS.find((p) => p.id === 'free')!.sessions_limit} speaking sessions a month. Paid plans start at ₹${FALLBACK_PLANS.find((p) => p.id === 'basic')!.price} (about $${Math.round(FALLBACK_PLANS.find((p) => p.id === 'basic')!.price / INR_TO_USD)}) per month, up to Elite at ₹${FALLBACK_PLANS.find((p) => p.id === 'elite')!.price} (about $${Math.round(FALLBACK_PLANS.find((p) => p.id === 'elite')!.price / INR_TO_USD)}) per month. All prices are billed monthly with no lock-in contract.`,
  },
  {
    q: 'Is there a free trial?',
    a: 'Yes. The free plan gives you 3 speaking sessions a month with the full 9-criteria examiner report. No credit card is required to start.',
  },
  {
    q: 'What is the difference between Basic, Pro, and Elite?',
    a: 'Basic adds Reading and Listening practice on top of Speaking. Pro adds Writing practice and scoring, a premium scoring model, and the premium British patient voice. Elite adds the full 4-part Mock Test, phoneme-level pronunciation scoring, and an AI-generated study plan.',
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
  {
    q: 'Is pricing different for nurses outside India?',
    a: "Prices are billed in Indian Rupees (INR) regardless of where you're practicing from. The USD amounts shown are an approximate conversion so international users can compare cost at a glance.",
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
      <td className="px-4 py-3 text-center">
        <Check className="w-4 h-4 text-emerald-600 mx-auto" strokeWidth={3} aria-hidden="true" />
        <span className="sr-only">Included</span>
      </td>
    )
  }
  if (value === false) {
    return (
      <td className="px-4 py-3 text-center">
        <Minus className="w-4 h-4 text-gray-300 mx-auto" aria-hidden="true" />
        <span className="sr-only">Not included</span>
      </td>
    )
  }
  return <td className="px-4 py-3 text-center text-gray-600">{value}</td>
}

export default function PricingPage() {
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

      <div className="max-w-6xl mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h1 className="text-4xl md:text-5xl font-bold text-[#0F2356] text-balance">
            Pricing that grows with your OET prep
          </h1>
          <p className="text-gray-500 mt-4 text-lg max-w-2xl mx-auto">
            Start free with 3 speaking sessions a month. Paid plans from ₹
            {FALLBACK_PLANS.find((p) => p.id === 'basic')!.price} (~$
            {Math.round(FALLBACK_PLANS.find((p) => p.id === 'basic')!.price / INR_TO_USD)}) a
            month unlock Reading, Listening, Writing, and the full Mock Test — no lock-in
            contract, cancel anytime.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-16 items-start">
          {FALLBACK_PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`rounded-2xl bg-white flex flex-col ${
                plan.highlight
                  ? 'border-2 border-[#0F2356] shadow-xl md:-translate-y-2'
                  : 'border border-gray-200 shadow-sm'
              }`}
            >
              {plan.highlight && (
                <div className="bg-[#0F2356] text-white text-center text-xs font-semibold uppercase tracking-wider py-2 rounded-t-2xl">
                  Most Popular
                </div>
              )}
              <div className="p-6 flex flex-col flex-1">
                <h2 className="text-xl font-bold text-[#0F2356] mb-1">{plan.name}</h2>
                <p className="text-sm text-gray-500 mb-4 min-h-[2.5rem]">{plan.description}</p>
                <div className="mb-1">
                  <span className="text-3xl font-black text-[#0F2356]">
                    {plan.price === 0 ? 'Free' : `₹${plan.price}`}
                  </span>
                  {plan.price > 0 && <span className="text-gray-400 text-sm ml-1">/{plan.period}</span>}
                </div>
                {plan.price > 0 && (
                  <p className="text-xs text-gray-400 mb-4">
                    ≈ ${Math.round(plan.price / INR_TO_USD)} USD/{plan.period}
                  </p>
                )}
                {plan.price === 0 && <p className="text-xs text-gray-400 mb-4">No credit card required</p>}

                <ul className="flex flex-col gap-2.5 mb-6 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-sm text-gray-600">
                      <Check className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" strokeWidth={3} aria-hidden="true" />
                      {f}
                    </li>
                  ))}
                </ul>

                <Link
                  href="/auth/register"
                  className={`mt-auto block w-full text-center font-semibold px-6 py-3 rounded-xl transition-colors ${
                    plan.highlight
                      ? 'bg-[#0F2356] text-white hover:bg-[#0F2356]/90'
                      : 'bg-gray-50 text-[#0F2356] border border-gray-200 hover:bg-gray-100'
                  }`}
                >
                  {plan.cta}
                </Link>
              </div>
            </div>
          ))}
        </div>

        <div className="mb-16">
          <h2 className="text-2xl md:text-3xl font-bold text-[#0F2356] text-center mb-8">
            Compare Every Feature
          </h2>
          <div className="overflow-x-auto rounded-2xl border border-gray-200 shadow-sm bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th scope="col" className="px-4 py-3 text-left font-bold text-[#0F2356]">
                    Feature
                  </th>
                  {FALLBACK_PLANS.map((plan) => (
                    <th key={plan.id} scope="col" className="px-4 py-3 text-center font-bold text-[#0F2356]">
                      {plan.name}
                    </th>
                  ))}
                </tr>
              </thead>
              {FEATURE_SECTIONS.map((section) => (
                <tbody key={section.title}>
                  <tr className="bg-[#0F2356]/5">
                    <th
                      colSpan={5}
                      scope="colgroup"
                      className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-[#0F2356]"
                    >
                      <span className="inline-flex items-center gap-2">
                        <section.icon className="w-3.5 h-3.5" aria-hidden="true" />
                        {section.title}
                      </span>
                    </th>
                  </tr>
                  {section.rows.map((row, i) => (
                    <tr key={row.label} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50/60'}>
                      <th scope="row" className="px-4 py-3 text-left font-medium text-gray-700">
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
        </div>

        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold text-[#0F2356] text-center mb-8">
            Pricing Questions
          </h2>
          <div className="rounded-2xl overflow-hidden border border-gray-100 shadow-sm bg-white">
            {PRICING_FAQS.map((faq, i) => (
              <div key={faq.q} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                <div className="px-6 py-5">
                  <h3 className="text-[#0F2356] font-semibold text-sm md:text-base leading-snug mb-2">
                    {faq.q}
                  </h3>
                  <p className="text-gray-600 text-sm leading-relaxed">{faq.a}</p>
                </div>
                {i < PRICING_FAQS.length - 1 && <div className="border-b border-gray-100" />}
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  )
}
