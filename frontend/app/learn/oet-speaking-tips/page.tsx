import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'

export const metadata: Metadata = {
  title: 'OET Speaking Tips for Nurses',
  description:
    'Practical, criteria-based tips to raise your OET Speaking score — from structuring the consultation to managing nerves.',
}

const toc = [
  { id: 'tip-1-use-prep-well', label: '1. Use your 2 minutes of prep well' },
  { id: 'tip-2-open-the-conversation', label: "2. Open the conversation, don't launch into facts" },
  { id: 'tip-3-give-structure', label: '3. Give the conversation structure' },
  { id: 'tip-4-check-understanding', label: '4. Check understanding before moving on' },
  { id: 'tip-5-react-to-patient', label: '5. React to what the patient actually says' },
  { id: 'tip-6-record-yourself', label: '6. Record yourself and listen back' },
  { id: 'tip-7-practise-roleplay', label: '7. Practise the roleplay itself, not just vocabulary' },
]

export default function OetSpeakingTipsPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <Link href="/blog" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All articles
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">OET Speaking Tips for Nurses</h1>
      <p className="text-gray-500 text-lg mb-2">
        Practical, criteria-based tips to raise your score — not generic English advice.
      </p>
      <ArticleMeta date="2026-07-04" />
      <TableOfContents items={toc} />

      <h2 id="tip-1-use-prep-well" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">1. Use your 2 minutes of prep well</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Don&apos;t just read the card once. Identify: who you are, who the patient is, what
        they&apos;re worried about, and the 2–3 things you must cover. Jot down key words, not
        full sentences — you&apos;ll be marked down for sounding rehearsed.
      </p>

      <h2 id="tip-2-open-the-conversation" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">2. Open the conversation, don&apos;t launch into facts</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Examiners score &quot;relationship building&quot; separately from the information itself.
        Greet the patient, use their name, and acknowledge how they might be feeling before you
        start explaining or asking questions.
      </p>

      <h2 id="tip-3-give-structure" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">3. Give the conversation structure</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Signal what&apos;s coming next: &quot;I&apos;d like to ask a few questions first, then
        explain what happens next.&quot; This is literally one of the scored criteria (providing
        structure) — it also makes you sound calmer and more in control.
      </p>

      <h2 id="tip-4-check-understanding" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">4. Check understanding before moving on</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Avoid jargon, and pause to confirm the patient has understood — &quot;does that make
        sense?&quot; or &quot;would you like me to go over that again?&quot; This maps directly to
        the &quot;incorporating the patient&apos;s perspective&quot; criterion.
      </p>

      <LearnCTA />

      <h2 id="tip-5-react-to-patient" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">5. React to what the patient actually says</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        The interlocutor improvises — if they mention a fear or a detail you didn&apos;t expect,
        respond to it before moving to your next point. Ignoring what the patient says to get
        through a memorised script is one of the most common ways candidates lose marks.
      </p>

      <h2 id="tip-6-record-yourself" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">6. Record yourself and listen back</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        It&apos;s uncomfortable, but it&apos;s the fastest way to catch filler words, rushed
        pacing, and places where you dropped structure. Score yourself against the criteria
        instead of just asking &quot;did that sound okay?&quot;
      </p>

      <h2 id="tip-7-practise-roleplay" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">7. Practise the roleplay itself, not just vocabulary</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Flashcards and vocabulary lists help with Reading and Writing, but Speaking is a
        performance skill — the only way to get comfortable with it is repeated, realistic
        practice under similar conditions to the real test.{' '}
        <Link href="/practice/speaking" className="text-[#0F2356] font-semibold underline">
          SpeakOET&apos;s AI patient
        </Link>{' '}
        exists specifically to give you that repetition on demand.
      </p>

      <LearnCTA />
    </main>
  )
}
