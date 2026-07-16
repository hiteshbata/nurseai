import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'

export const metadata: Metadata = {
  title: 'OET for Indian Nurses',
  description:
    'What Indian nurses need to know about OET: why it’s often preferred over IELTS, common challenges, and how to prepare.',
  alternates: { canonical: '/learn/oet-for-indian-nurses' },
}

const toc = [
  { id: 'why-oet', label: 'Why OET, and not just IELTS?' },
  { id: 'common-challenges', label: 'Common challenges' },
  { id: 'how-to-prepare', label: 'How to prepare' },
]

export default function OetForIndianNursesPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <Link href="/blog" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All articles
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">OET for Indian Nurses</h1>
      <p className="text-gray-500 text-lg mb-2">
        What Indian nurses need to know about OET before registering in Australia, the UK, or New
        Zealand.
      </p>
      <ArticleMeta date="2026-07-04" />
      <TableOfContents items={toc} />

      <h2 id="why-oet" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Why OET, and not just IELTS?</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Most major nursing regulators — the UK&apos;s NMC, Australia&apos;s Ahpra/NMBA, and New
        Zealand&apos;s Nursing Council — accept both OET and IELTS. Many Indian nurses choose OET
        because the content is built around real clinical scenarios rather than general English
        topics, so preparation feels more directly useful. See our full{' '}
        <Link href="/learn/oet-vs-ielts" className="text-[#0F2356] font-semibold underline">
          OET vs IELTS comparison
        </Link>{' '}
        for the details.
      </p>

      <h2 id="common-challenges" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Common challenges</h2>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        <li>
          <span className="font-semibold text-[#0F2356]">Register and directness.</span> Clinical
          communication styles taught and practised in India can be more formal or direct than
          what OET&apos;s patient-centred criteria reward — examiners specifically look for
          warmth, checking-in, and involving the patient in the conversation.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Unscripted improvisation.</span> The
          interlocutor reacts in real time, so a memorised script falls apart the moment they say
          something unexpected. This is usually the single biggest score-killer.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Exam-day nerves.</span> Many strong
          English speakers underperform simply because they haven&apos;t roleplayed the format
          enough times to feel comfortable with it.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Limited speaking practice partners.</span>{' '}
          Reading and Writing can be self-studied from books; Speaking needs another person (or an
          AI patient) to practise against, which is harder to arrange consistently.
        </li>
      </ul>

      <LearnCTA />

      <h2 id="how-to-prepare" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">How to prepare</h2>
      <ol className="list-decimal pl-5 space-y-2 text-gray-600 mb-4">
        <li>Confirm the exact score your target regulator requires before you book the test.</li>
        <li>
          Learn the format cold — see our{' '}
          <Link href="/learn/what-is-oet-speaking" className="text-[#0F2356] font-semibold underline">
            OET Speaking guide
          </Link>
          .
        </li>
        <li>Practise full roleplays regularly, not just vocabulary lists.</li>
        <li>Record yourself, or get scored feedback, so you know what to fix — not just &quot;how it felt.&quot;</li>
        <li>Repeat scenarios you found hard until the structure becomes automatic.</li>
      </ol>
      <p className="text-gray-600 leading-relaxed mb-4">
        SpeakOET is built for exactly this: unlimited AI patient roleplay, available whenever
        you have time to practise, with the same structured feedback an examiner would give.
      </p>

      <LearnCTA />
    </main>
  )
}
