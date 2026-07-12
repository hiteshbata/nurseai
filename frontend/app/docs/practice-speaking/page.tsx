import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { TableOfContents } from '@/components/learn/TableOfContents'

export const metadata: Metadata = {
  title: 'Practice Speaking - SpeakOET Docs',
  description: 'How the AI patient roleplay works, what the 9-criteria feedback means, and tips for getting the most out of a session.',
}

const toc = [
  { id: 'how-it-works', label: 'How a session works' },
  { id: 'feedback-criteria', label: 'What the 9 criteria measure' },
  { id: 'mic-issues', label: 'Microphone not working' },
]

export default function PracticeSpeakingDocsPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <Link href="/docs" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All docs
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">Practice Speaking</h1>
      <p className="text-gray-500 text-lg mb-10">
        Roleplay realistic OET patient scenarios out loud with an AI patient, and get instant,
        criteria-based feedback.
      </p>
      <TableOfContents items={toc} />

      <h2 id="how-it-works" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">How a session works</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Open{' '}
        <Link href="/practice/speaking" className="text-[#0F2356] font-semibold underline">
          Practice Speaking
        </Link>
        , pick a role-play scenario, and take your 2 minutes of prep time to read the card. When
        you start, the AI patient responds to you in real time by voice — you talk, it talks back,
        just like the real exam. Sessions count against your plan&apos;s monthly session limit.
      </p>

      <h2 id="feedback-criteria" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">What the 9 criteria measure</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        After each session, SpeakOET grades you against the same linguistic and clinical
        communication criteria OET examiners use — things like relationship building, structuring
        the conversation, understanding and incorporating the patient&apos;s perspective, providing
        the right information at the right time, and appropriate use of language. Your feedback
        names the specific criteria you did well on and the ones to focus on next.
      </p>

      <h2 id="mic-issues" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Microphone not working</h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Check your browser has microphone permission for SpeakOET — usually a padlock icon in the
        address bar — close any other app using the mic, and refresh the page. Still stuck?{' '}
        <Link href="/support" className="text-[#0F2356] font-semibold underline">
          Contact support
        </Link>{' '}
        with your browser and device.
      </p>

      <LearnCTA />
    </main>
  )
}
