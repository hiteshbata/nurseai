import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'

export const metadata: Metadata = {
  title: 'Mock Test - Docs',
  description: 'Simulate the full OET Speaking sub-test under timed, exam-style conditions.',
}

export default function MockTestDocsPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <Link href="/docs" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All docs
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">Mock Test</h1>
      <p className="text-gray-500 text-lg mb-10">
        Run a full, timed OET Speaking simulation before your real exam.
      </p>

      <p className="text-gray-600 leading-relaxed mb-4">
        Open{' '}
        <Link href="/mock-test" className="text-[#0F2356] font-semibold underline">
          Mock Test
        </Link>{' '}
        to attempt both role-plays back to back under the same timing as the real OET Speaking
        sub-test — 2 minutes prep, then the roleplay itself. Unlike a single practice session, a
        mock test gives you one combined score across both role-plays, closer to what you&apos;ll
        experience on exam day.
      </p>

      <p className="text-gray-600 leading-relaxed mb-4">
        Use Mock Test in the final week or two before your booked OET date, once you&apos;ve
        already built confidence with regular{' '}
        <Link href="/docs/practice-speaking" className="text-[#0F2356] font-semibold underline">
          Practice Speaking
        </Link>{' '}
        sessions.
      </p>

      <LearnCTA />
    </main>
  )
}
