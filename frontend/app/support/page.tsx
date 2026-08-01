import Link from 'next/link'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import { Mail, MessageCircle } from 'lucide-react'
import { RevealOnScroll } from '@/components/RevealOnScroll'

export const metadata: Metadata = {
  title: 'Support',
  description:
    'Get help with SpeakOET — contact us by email or WhatsApp, or check our FAQ on plans, sessions, and OET scoring.',
  alternates: { canonical: '/support' },
}

// WhatsApp Business number, wa.me format: country code first, digits only, no
// + or spaces. This is public and gets scraped, so it must stay a Business
// number rather than a personal one.
const WHATSAPP_NUMBER = '919512499593'

const FAQS: { question: string; answer: ReactNode }[] = [
  {
    question: 'What is SpeakOET?',
    answer:
      'SpeakOET is an AI-powered speaking partner for OET preparation. You roleplay realistic patient scenarios out loud with an AI patient, and get instant, criteria-based feedback — the same kind an OET examiner would give.',
  },
  {
    question: 'Do I need to install anything?',
    answer:
      'No. SpeakOET runs in your browser. You just need a working microphone and a stable internet connection.',
  },
  {
    question: 'Which part of OET does SpeakOET cover?',
    answer:
      'All four: Speaking, Reading, Writing and Listening, plus full Mock Tests. Speaking is our signature feature, an AI patient roleplay scored on all 9 OET criteria, alongside dedicated practice for the other three sub-tests.',
  },
  {
    question: 'How many free sessions do I get?',
    answer: (
      <>
        New accounts start with a limited number of free speaking sessions. You can see the
        current number and all paid plans on the{' '}
        <Link href="/upgrade" className="text-[#0F2356] font-semibold underline">
          pricing page
        </Link>
        .
      </>
    ),
  },
  {
    question: 'Can I cancel my subscription?',
    answer:
      'Yes, anytime, from your account settings. Your access continues until the end of the billing period you already paid for — there are no lock-in contracts.',
  },
  {
    question: 'Do you offer refunds?',
    answer: (
      <>
        Reach out to{' '}
        <a href="mailto:support@speakoet.com" className="text-[#0F2356] font-semibold underline">
          support@speakoet.com
        </a>{' '}
        with your issue and we&apos;ll sort it out on a case-by-case basis.
      </>
    ),
  },
  {
    question: 'Is my speaking data private?',
    answer: (
      <>
        We only use your practice sessions to generate your feedback and score history — see our{' '}
        <Link href="/privacy" className="text-[#0F2356] font-semibold underline">
          Privacy Policy
        </Link>{' '}
        for full details.
      </>
    ),
  },
  {
    question: 'Which countries does this help with?',
    answer:
      'SpeakOET is built around the OET Speaking format used by regulators in Australia, the UK, and New Zealand, with a particular focus on Indian nurses preparing for the first time.',
  },
  {
    question: 'My microphone isn’t working — what do I do?',
    answer:
      'Check that your browser has microphone permission for this site (usually a padlock icon in the address bar), close other apps that might be using the mic, and try refreshing the page. If it still doesn’t work, email us with your browser and device and we’ll help you debug it.',
  },
]

export default function SupportPage() {
  // AppShell already renders <main id="main-content"> and pads/centers the
  // page -- a second <main> here duplicated that landmark and its id.
  return (
    <div className="max-w-3xl mx-auto py-8 lg:py-12">
      <div className="motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mb-4">Support</h1>
        <p className="text-gray-500 text-lg mb-10">
          We&apos;re here to help — before, during, and after your OET prep.
        </p>
      </div>

      <section className="grid sm:grid-cols-2 gap-4 mb-12">
        <RevealOnScroll>
          <a
            href="mailto:support@speakoet.com"
            className="block h-full rounded-2xl border border-gray-100 bg-white shadow-premium p-6 motion-safe:transition-shadow motion-safe:duration-200 hover:shadow-premium-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
          >
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-[#0F2356]/[0.06] mb-3">
              <Mail className="w-5 h-5 text-[#047857]" strokeWidth={1.75} aria-hidden="true" />
            </div>
            <p className="font-semibold text-[#0F2356] mb-1">Email</p>
            <p className="text-gray-500 text-sm mb-2">Best for detailed questions or account issues.</p>
            <p className="text-[#0F2356] font-semibold text-sm">support@speakoet.com</p>
          </a>
        </RevealOnScroll>
        {/* Elite lists "WhatsApp priority support" as a paid feature, so this
            link has to resolve to a real, WhatsApp-active number — an invalid
            one shows "phone number shared via url is invalid" to a paying
            member. Format: country code first, digits only, no + or spaces. */}
        <RevealOnScroll delayMs={80}>
          <a
            href={`https://wa.me/${WHATSAPP_NUMBER}`}
            target="_blank"
            rel="noopener noreferrer"
            className="block h-full rounded-2xl border border-gray-100 bg-white shadow-premium p-6 motion-safe:transition-shadow motion-safe:duration-200 hover:shadow-premium-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
          >
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-[#0F2356]/[0.06] mb-3">
              <MessageCircle className="w-5 h-5 text-[#047857]" strokeWidth={1.75} aria-hidden="true" />
            </div>
            <p className="font-semibold text-[#0F2356] mb-1">WhatsApp</p>
            <p className="text-gray-500 text-sm mb-2">Best for quick questions during your prep.</p>
            <p className="text-[#0F2356] font-semibold text-sm">Chat with us</p>
          </a>
        </RevealOnScroll>
      </section>

      <section>
        <h2 className="font-display text-xl font-semibold text-[#0F2356] mb-4">
          Frequently asked questions
        </h2>
        <div className="divide-y divide-gray-100 border-y border-gray-100">
          {FAQS.map(({ question, answer }, i) => (
            <RevealOnScroll key={question} delayMs={Math.min(i, 4) * 40}>
              <details className="group py-4">
                <summary className="cursor-pointer list-none flex items-center justify-between gap-4 font-semibold text-[#0F2356] rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
                  {question}
                  <span className="shrink-0 text-gray-400 motion-safe:transition-transform motion-safe:duration-200 group-open:rotate-45 text-xl leading-none">
                    +
                  </span>
                </summary>
                <div className="text-gray-600 mt-2 leading-relaxed">{answer}</div>
              </details>
            </RevealOnScroll>
          ))}
        </div>
      </section>
    </div>
  )
}
