import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'

export const metadata: Metadata = {
  title: 'What is OET Speaking?',
  description:
    'A complete guide to the OET Speaking sub-test: the role-play format, timing, and exactly how examiners assess you.',
  alternates: { canonical: '/learn/what-is-oet-speaking' },
}

const toc = [
  { id: 'the-format', label: 'The format' },
  { id: 'whats-being-assessed', label: "What's being assessed" },
  { id: 'why-it-feels-different', label: 'Why it feels different from other exams' },
]

export default function WhatIsOetSpeakingPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <Link href="/blog" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All articles
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">What is OET Speaking?</h1>
      <p className="text-gray-500 text-lg mb-2">
        A complete guide to the OET Speaking sub-test — format, timing, and how it&apos;s scored.
      </p>
      <ArticleMeta date="2026-07-04" />
      <TableOfContents items={toc} />

      <h2 id="the-format" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">The format</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET Speaking is a face-to-face (or video-call) test with a trained interlocutor, taken
        separately from Listening, Reading, and Writing. It&apos;s built around your profession —
        nurses get nursing scenarios, doctors get medical scenarios — and it&apos;s recorded for
        assessment.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        You complete two roleplays, each about 5 minutes long. Before each one, you get roughly 2
        minutes to read a card describing the scenario: who you are, who the patient is, and what
        you need to cover. The interlocutor plays the patient or a relative and improvises around
        the scenario — it isn&apos;t scripted, so you have to actually listen and respond.
      </p>

      <h2 id="whats-being-assessed" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">What&apos;s being assessed</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Two examiners score your recording against two groups of criteria:
      </p>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        <li>
          <span className="font-semibold text-[#0F2356]">Linguistic criteria</span> —
          intelligibility, fluency, appropriateness of language, and resources of grammar and
          expression. This is the &quot;is your English clear and natural&quot; half.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Clinical communication criteria</span> —
          relationship building, understanding and incorporating the patient&apos;s perspective,
          providing structure, information gathering, and information giving. This is the
          &quot;are you communicating like a safe, patient-centred clinician&quot; half.
        </li>
      </ul>
      <p className="text-gray-600 leading-relaxed mb-4">
        That second group is what trips up a lot of strong English speakers — it&apos;s not enough
        to speak fluently, you also need to structure the conversation, check the patient
        understands, and respond to what they actually say rather than delivering a memorised
        script.
      </p>

      <LearnCTA />

      <h2 id="why-it-feels-different" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Why it feels different from other exams</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Most English tests ask you to describe a photo or give an opinion on a general topic. OET
        Speaking asks you to actually do your job in English — explain a procedure, handle an
        anxious relative, break bad news calmly. That&apos;s why generic speaking practice (or a
        friend reading questions off a list) only gets you so far: the skill you&apos;re being
        tested on is reacting in character, in real time.
      </p>

      <p className="text-gray-600 leading-relaxed mb-4">
        Always check the exact current format and marking guide on the official OET website —
        details like timing and criteria weighting are set by OET, not by us.
      </p>

      <p className="text-gray-600 leading-relaxed mb-4">
        For the full breakdown of all 9 assessment criteria and how a roleplay actually plays
        out, see our{' '}
        <Link href="/oet/speaking" className="text-[#0F2356] font-semibold underline">
          complete OET Speaking guide
        </Link>
        . If you&apos;re preparing for the other three sub-tests too, see our guides to{' '}
        <Link href="/learn/oet-writing" className="text-[#0F2356] font-semibold underline">
          OET Writing
        </Link>
        ,{' '}
        <Link href="/learn/oet-reading" className="text-[#0F2356] font-semibold underline">
          OET Reading
        </Link>
        , and{' '}
        <Link href="/learn/oet-listening" className="text-[#0F2356] font-semibold underline">
          OET Listening
        </Link>
        .
      </p>

      <LearnCTA />
    </main>
  )
}
