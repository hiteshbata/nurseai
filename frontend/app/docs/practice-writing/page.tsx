import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'

export const metadata: Metadata = {
  title: 'Practice Writing - Docs',
  description: 'How OET Writing practice works and which plans include it.',
}

export default function PracticeWritingDocsPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <Link href="/docs" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All docs
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">Practice Writing</h1>
      <p className="text-gray-500 text-lg mb-10">
        Practice OET-style referral letters and get AI feedback on structure, tone, and clinical
        accuracy.
      </p>

      <p className="text-gray-600 leading-relaxed mb-4">
        Open{' '}
        <Link href="/practice/writing" className="text-[#0F2356] font-semibold underline">
          Practice Writing
        </Link>{' '}
        to write against a case note prompt, styled on the OET Writing sub-test. You&apos;ll get
        feedback on how well your letter is structured, whether you&apos;ve included the right
        clinical information, and how appropriate your tone and language are for the reader.
      </p>

      <p className="text-gray-600 leading-relaxed mb-4">
        Practice Writing is included on{' '}
        <Link href="/upgrade" className="text-[#0F2356] font-semibold underline">
          Pro and Elite plans
        </Link>
        . If you&apos;re on Free or Basic, you&apos;ll see an upgrade prompt when you try to open
        it.
      </p>

      <LearnCTA />
    </main>
  )
}
