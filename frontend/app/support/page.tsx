import Link from 'next/link'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'

export const metadata: Metadata = {
  title: 'Support - SpeakOET',
  description:
    'Get help with SpeakOET — contact us by email or WhatsApp, or check our FAQ on plans, sessions, and OET scoring.',
}

// TODO: replace with your real WhatsApp Business number (digits only, country
// code first, no + or spaces) — e.g. 919812345678 for a +91 98123 45678 number.
const WHATSAPP_NUMBER = '910000000000'

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
      'Speaking. SpeakOET focuses specifically on the OET Speaking sub-test — the roleplay between you and a patient or relative.',
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
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold text-[#0F2356] mb-4">Support</h1>
      <p className="text-gray-500 text-lg mb-10">
        We&apos;re here to help — before, during, and after your OET prep.
      </p>

      <section className="grid sm:grid-cols-2 gap-4 mb-12">
        <a
          href="mailto:support@speakoet.com"
          className="rounded-2xl border border-gray-100 bg-white shadow-sm p-6 hover:shadow-md transition"
        >
          <p className="font-semibold text-[#0F2356] mb-1">📧 Email</p>
          <p className="text-gray-500 text-sm mb-2">Best for detailed questions or account issues.</p>
          <p className="text-[#0F2356] font-semibold text-sm">support@speakoet.com</p>
        </a>
        <a
          href={`https://wa.me/${WHATSAPP_NUMBER}`}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-2xl border border-gray-100 bg-white shadow-sm p-6 hover:shadow-md transition"
        >
          <p className="font-semibold text-[#0F2356] mb-1">💬 WhatsApp</p>
          <p className="text-gray-500 text-sm mb-2">Best for quick questions during your prep.</p>
          <p className="text-[#0F2356] font-semibold text-sm">Chat with us</p>
        </a>
      </section>

      <section>
        <h2 className="text-xl font-bold text-[#0F2356] mb-4">Frequently asked questions</h2>
        <div className="divide-y divide-gray-100 border-y border-gray-100">
          {FAQS.map(({ question, answer }) => (
            <details key={question} className="group py-4">
              <summary className="cursor-pointer list-none flex items-center justify-between font-semibold text-[#0F2356]">
                {question}
                <span className="text-gray-400 transition-transform group-open:rotate-45 text-xl leading-none">
                  +
                </span>
              </summary>
              <div className="text-gray-600 mt-2 leading-relaxed">{answer}</div>
            </details>
          ))}
        </div>
      </section>
    </main>
  )
}
