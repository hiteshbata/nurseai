import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'

export const metadata: Metadata = {
  title: 'OET vs IELTS — Which Should Nurses Choose?',
  description:
    'How the two tests differ in format and content, and why most nurses find one more relevant to their job.',
}

const toc = [
  { id: 'the-core-difference', label: 'The core difference' },
  { id: 'format-side-by-side', label: 'Format, side by side' },
  { id: 'why-nurses-prefer-oet', label: 'Why many nurses prefer OET' },
  { id: 'how-to-decide', label: 'How to decide' },
]

export default function OetVsIeltsPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <Link href="/blog" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All articles
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">
        OET vs IELTS — Which Should Nurses Choose?
      </h1>
      <p className="text-gray-500 text-lg mb-2">
        Both are accepted by most major nursing regulators. Here&apos;s how they actually differ.
      </p>
      <ArticleMeta date="2026-07-04" />
      <TableOfContents items={toc} />

      <h2 id="the-core-difference" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">The core difference</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        IELTS Academic tests general English — everyday topics, academic-style essays, an
        interview about your life and opinions. OET tests healthcare English specifically — every
        task, in every sub-test, is built around real clinical situations a nurse or doctor would
        face on the job.
      </p>

      <h2 id="format-side-by-side" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Format, side by side</h2>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        <li>
          <span className="font-semibold text-[#0F2356]">Speaking</span> — IELTS is a general
          interview with an examiner. OET is a profession-specific roleplay with a patient or
          relative.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Writing</span> — IELTS asks for a
          general essay and a data/letter task. OET asks nurses to write a referral, discharge,
          or transfer letter based on case notes.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Reading &amp; Listening</span> — IELTS
          uses general-interest passages and recordings. OET uses healthcare texts, patient
          consultations, and clinical presentations.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Scoring</span> — IELTS reports a band
          from 0–9. OET reports a letter grade (A–E) and a numeric score per sub-test — see our{' '}
          <Link href="/learn/oet-band-scores" className="text-[#0F2356] font-semibold underline">
            OET band scores guide
          </Link>
          .
        </li>
      </ul>

      <LearnCTA />

      <h2 id="why-nurses-prefer-oet" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Why many nurses prefer OET</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Because the content matches your actual job, preparation does double duty — the
        vocabulary, scenarios, and communication habits you practise for the exam are the same
        ones you&apos;ll use on the ward. Nurses who find general-topic IELTS questions (&quot;describe
        a memorable trip&quot;) hard to relate to often find OET&apos;s clinical scenarios more
        natural to prepare for, since they&apos;re already familiar with the subject matter.
      </p>

      <h2 id="how-to-decide" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">How to decide</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Start with your target regulator — check which test(s) they accept and any minimum score
        before you commit to one. If both are accepted, the deciding factor is usually which
        format you&apos;ll prepare for more effectively: general English topics, or real clinical
        roleplay.
      </p>

      <LearnCTA />
    </main>
  )
}
