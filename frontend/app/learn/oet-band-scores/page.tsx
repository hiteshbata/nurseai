import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'

export const metadata: Metadata = {
  title: 'OET Band Scores Explained',
  description:
    'How OET grading works from A to E, what the numeric score means, and the score most regulators ask for.',
  alternates: { canonical: '/learn/oet-band-scores' },
}

const toc = [
  { id: 'grades-and-numeric-scores', label: 'Grades and numeric scores' },
  { id: 'what-score-do-you-need', label: 'What score do you actually need?' },
  { id: 'why-speaking-is-hardest', label: 'Why Speaking is often the hardest sub-test' },
]

export default function OetBandScoresPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <Link href="/blog" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All articles
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">OET Band Scores Explained</h1>
      <p className="text-gray-500 text-lg mb-2">
        How OET grading works, and the score most nursing regulators ask for.
      </p>
      <ArticleMeta date="2026-07-04" />
      <TableOfContents items={toc} />

      <h2 id="grades-and-numeric-scores" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Grades and numeric scores</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Each of the four OET sub-tests — Listening, Reading, Writing, Speaking — is graded
        separately, both as a letter grade (A being the highest, E the lowest) and as a numeric
        score out of 500, in steps of 10. There is no single &quot;overall&quot; score that
        averages the four together — regulators look at your result on each sub-test
        individually.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        As a rough guide, an OET Grade B roughly corresponds to the middle-to-upper band of the
        500-point scale, and is the level most healthcare regulators ask for. Exact grade
        boundaries are set and occasionally adjusted by OET, so treat any specific numbers you
        see (including here) as a general guide rather than the final word.
      </p>

      <LearnCTA />

      <h2 id="what-score-do-you-need" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">What score do you actually need?</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Requirements are set by the regulator you&apos;re registering with — not by OET itself —
        and they do change over time. As a starting point:
      </p>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        <li>
          <span className="font-semibold text-[#0F2356]">UK (NMC)</span> — typically Grade B or
          higher in each sub-test.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Australia (Ahpra / NMBA)</span> —
          typically Grade B or higher in each sub-test.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">New Zealand (Nursing Council)</span> —
          typically Grade B or higher in each sub-test.
        </li>
      </ul>
      <p className="text-gray-600 leading-relaxed mb-4">
        Because these requirements are set by each regulator and can change, always confirm the
        current pass mark on your target regulator&apos;s official website before you sit the
        test — don&apos;t rely solely on this page or on forum posts.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        Already have a result? Use the free{' '}
        <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline">
          OET score calculator
        </Link>{' '}
        to check your grades or numeric scores against NMC, Ahpra, and 5 other regulators at once.
      </p>

      <h2 id="why-speaking-is-hardest" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Why Speaking is often the hardest sub-test</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Many candidates comfortably clear Grade B on Reading and Listening but stall on Speaking,
        because it&apos;s scored on live, unscripted performance rather than a written answer you
        can prepare in advance. The fix is the same as for any performance skill: repeated,
        realistic practice with feedback — not just reading about the exam.
      </p>

      <LearnCTA />
    </main>
  )
}
