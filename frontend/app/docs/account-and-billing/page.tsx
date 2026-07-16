import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { TableOfContents } from '@/components/learn/TableOfContents'

export const metadata: Metadata = {
  title: 'Account & Billing - Docs',
  description: 'Manage your plan, sessions, subscription, and account settings.',
  alternates: { canonical: '/docs/account-and-billing' },
}

const toc = [
  { id: 'plans-and-sessions', label: 'Plans and session limits' },
  { id: 'upgrade-downgrade', label: 'Upgrading or downgrading' },
  { id: 'cancel', label: 'Cancelling your subscription' },
  { id: 'profile', label: 'Updating your profile' },
]

export default function AccountBillingDocsPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <Link href="/docs" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All docs
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">Account &amp; Billing</h1>
      <p className="text-gray-500 text-lg mb-10">
        How plans, sessions, and your account settings work.
      </p>
      <TableOfContents items={toc} />

      <h2 id="plans-and-sessions" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Plans and session limits</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Every plan includes a fixed number of speaking sessions per billing period. You can see
        your current usage — sessions used and remaining — on your dashboard and in the account
        menu. Session counts reset at the start of each new billing period, they don&apos;t carry
        over.
      </p>

      <h2 id="upgrade-downgrade" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Upgrading or downgrading</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Compare plans and change yours anytime from the{' '}
        <Link href="/upgrade" className="text-[#0F2356] font-semibold underline">
          Upgrade page
        </Link>
        . Higher plans unlock more sessions and features like Practice Writing.
      </p>

      <h2 id="cancel" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Cancelling your subscription</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        You can cancel anytime from your account settings — there&apos;s no lock-in contract.
        You&apos;ll keep access until the end of the billing period you&apos;ve already paid for.
      </p>

      <h2 id="profile" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Updating your profile</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Update your name and other account details from{' '}
        <Link href="/profile" className="text-[#0F2356] font-semibold underline">
          Profile Settings
        </Link>
        . For anything else — refunds, billing questions, account issues — reach out via{' '}
        <Link href="/support" className="text-[#0F2356] font-semibold underline">
          Support
        </Link>
        .
      </p>

      <LearnCTA />
    </main>
  )
}
