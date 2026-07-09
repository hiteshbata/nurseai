import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'

export const metadata: Metadata = {
  title: 'About Us - SpeakOET',
  description:
    'Why we built SpeakOET: realistic AI patient roleplay so nurses can practice OET Speaking, not just study theory.',
}

export default function AboutPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold text-[#0F2356] mb-4">About SpeakOET</h1>
      <p className="text-gray-500 text-lg mb-10">
        We help nurses pass OET Speaking with realistic AI patient roleplay — not just theory.
      </p>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-[#0F2356] mb-3">Why we built this</h2>
        <p className="text-gray-600 leading-relaxed mb-4">
          Every year, thousands of qualified, experienced nurses are held back from working in
          Australia, the UK, and New Zealand — not by their clinical skills, but by one speaking
          exam. Most OET preparation is built for reading and writing. Speaking practice usually
          means a WhatsApp group, a friend pretending to be a patient, or nothing at all.
        </p>
        <p className="text-gray-600 leading-relaxed">
          SpeakOET exists to fix that. We built an AI patient that roleplays real OET-style
          scenarios with you, any time of day, and gives you the same structured, criteria-based
          feedback an examiner would use — so you walk into the real test having already done the
          reps.
        </p>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-[#0F2356] mb-3">What we do</h2>
        <ul className="space-y-4">
          <li>
            <p className="font-semibold text-[#0F2356]">AI Patient Roleplay</p>
            <p className="text-gray-600">
              Real-time voice conversations styled on official OET role-play cards — not
              multiple-choice quizzes.
            </p>
          </li>
          <li>
            <p className="font-semibold text-[#0F2356]">Instant 9-Criteria Feedback</p>
            <p className="text-gray-600">
              Every session is scored against the same linguistic and clinical communication
              criteria OET examiners use.
            </p>
          </li>
          <li>
            <p className="font-semibold text-[#0F2356]">AI Coaching</p>
            <p className="text-gray-600">
              Personalized guidance on exactly what to fix before your next attempt.
            </p>
          </li>
        </ul>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-[#0F2356] mb-3">Who it&apos;s for</h2>
        <p className="text-gray-600 leading-relaxed">
          SpeakOET is built for nurses preparing to register in Australia, the UK, and New
          Zealand — with a particular focus on Indian nurses navigating OET for the first time.
        </p>
      </section>

      <p className="text-gray-500 mb-10">
        Questions or feedback? We&apos;d love to hear from you at{' '}
        <a href="mailto:support@speakoet.com" className="text-[#0F2356] font-semibold underline">
          support@speakoet.com
        </a>{' '}
        or via our{' '}
        <Link href="/support" className="text-[#0F2356] font-semibold underline">
          support page
        </Link>
        .
      </p>

      <LearnCTA />
    </main>
  )
}
