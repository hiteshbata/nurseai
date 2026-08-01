import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { TableOfContents } from '@/components/learn/TableOfContents'

export const metadata: Metadata = {
  title: 'Getting Started - Docs',
  description: 'Create your account, run your first AI patient roleplay, and understand your dashboard.',
  alternates: { canonical: '/docs/getting-started' },
}

const toc = [
  { id: 'create-account', label: '1. Create your account' },
  { id: 'first-session', label: '2. Run your first speaking session' },
  { id: 'read-feedback', label: '3. Read your feedback' },
  { id: 'dashboard', label: '4. Understand your dashboard' },
]

export default function GettingStartedPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <Link
        href="/docs"
        className="text-sm text-gray-500 hover:text-[#0F2356] rounded motion-safe:transition-colors motion-safe:duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
      >
        ← All docs
      </Link>
      <div className="motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mt-4 mb-4">Getting Started</h1>
        <p className="text-gray-500 text-lg mb-10">
          Everything you need to run your first practice session in a few minutes.
        </p>
      </div>
      <TableOfContents items={toc} />

      <h2 id="create-account" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">1. Create your account</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Sign up with your email from the{' '}
        <Link
          href="/auth/register"
          className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
        >
          registration page
        </Link>
        . Every new account starts on the Free plan with a limited number of speaking sessions, so
        you can try SpeakOET before choosing a paid plan.
      </p>

      <h2 id="first-session" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">2. Run your first speaking session</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        From your dashboard, open{' '}
        <Link
          href="/practice/speaking"
          className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
        >
          Practice Speaking
        </Link>
        . Allow microphone access when your browser asks, read the role-play card, and start
        talking to the AI patient as if it were a real OET Speaking sub-test.
      </p>

      <h2 id="read-feedback" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">3. Read your feedback</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        After a session ends, SpeakOET scores your performance against the same 9 criteria an OET
        examiner uses, and highlights specific things to fix before your next attempt. See{' '}
        <Link
          href="/docs/practice-speaking"
          className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
        >
          Practice Speaking
        </Link>{' '}
        for what each criterion means.
      </p>

      <h2 id="dashboard" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">4. Understand your dashboard</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Your dashboard shows your plan, how many sessions you have left this period, and your
        score history over time. Sessions remaining resets each billing period — see{' '}
        <Link
          href="/docs/account-and-billing"
          className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
        >
          Account &amp; Billing
        </Link>{' '}
        for details on plans and limits.
      </p>

      <LearnCTA />
    </main>
  )
}
