import Link from 'next/link'
import type { Metadata } from 'next'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'
import { CommonMistakes } from '@/components/oet/CommonMistakes'
import { RelatedOetPages } from '@/components/oet/RelatedOetPages'
import { RegulatorCTA } from '@/components/oet/RegulatorCTA'
import { RegulatorComparisonTable } from '@/components/oet/RegulatorComparisonTable'
import { FaqSection } from '@/components/seo/FaqSection'
import { OetPageJsonLd } from '@/components/seo/OetPageJsonLd'

const TITLE = 'OET for Indian Nurses — Requirements, Challenges, How to Prepare'
const DESCRIPTION =
  "What Indian nurses need to know about OET: why it's often preferred over IELTS, which regulators (UK, Australia, Ireland, New Zealand, Canada) accept it, common challenges, and how to prepare."

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/oet/india' },
}

const toc = [
  { id: 'why-oet', label: 'Why OET, and not just IELTS?' },
  { id: 'where', label: 'Where Indian nurses use OET' },
  { id: 'test-centres', label: 'OET test centres in India' },
  { id: 'common-challenges', label: 'Common challenges' },
  { id: 'how-to-prepare', label: 'How to prepare' },
  { id: 'mistakes', label: 'Common mistakes' },
  { id: 'faq', label: 'FAQ' },
  { id: 'related', label: 'Related guides' },
]

const faqs = [
  {
    q: 'Why do Indian nurses often choose OET over IELTS?',
    a: "Most major nursing regulators accept both, but OET's content is built around real clinical scenarios rather than general English topics, so preparation feels more directly useful for the job you're going to. See our full OET vs IELTS comparison for the details.",
  },
  {
    q: 'Which OET score do I need as an Indian nurse?',
    a: "It depends entirely on your destination regulator — the UK's NMC, Australia's Ahpra, Ireland's NMBI, New Zealand's Nursing Council, and Canada's provincial boards each set their own minimum. Check your specific target in the comparison table below, or run your scores through our free OET Score Calculator.",
  },
  {
    q: 'Is OET harder for Indian nurses than for other nationalities?',
    a: "No — the test itself doesn't vary by nationality. What trips up many Indian-trained nurses specifically is the patient-centred communication style OET rewards (warmth, checking in, involving the patient), which can differ from more formal or direct styles taught locally — see the challenges below.",
  },
  {
    q: 'Where can Indian-trained nurses use an OET result?',
    a: 'The UK, Australia, Ireland, New Zealand, and Canada all accept OET for nurse registration, alongside the US via the TruMerit/CGFNS pathway or individual state boards. See the comparison table below for each one\'s exact requirement.',
  },
]

export default function OetIndiaPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <OetPageJsonLd path="/oet/india" title={TITLE} description={DESCRIPTION} datePublished="2026-07-27" />

      <div className="motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mt-4 mb-4">OET for Indian Nurses</h1>
        <p className="text-gray-500 text-lg mb-2">
          What Indian nurses need to know about OET before registering in the UK, Australia, Ireland, New
          Zealand, or Canada.
        </p>
        <p className="text-gray-600 leading-relaxed mb-4">
          Before checking which regulator applies to you, you can estimate your current level using our{' '}
          <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
            OET Score Calculator
          </Link>{' '}
          and practise with{' '}
          <Link href="/auth/register" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
            free OET Speaking roleplays
          </Link>
          .
        </p>
      </div>
      <ArticleMeta date="2026-07-27" />
      <TableOfContents items={toc} />

      <h2 id="why-oet" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        Why OET, and not just IELTS?
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Most major nursing regulators — the UK's NMC, Australia's Ahpra/NMBA, Ireland's NMBI, and New
        Zealand's Nursing Council — accept both OET and IELTS. Many Indian nurses choose OET because the
        content is built around real clinical scenarios rather than general English topics, so preparation
        feels more directly useful. See our full{' '}
        <Link href="/learn/oet-vs-ielts" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
          OET vs IELTS comparison
        </Link>{' '}
        for the details.
      </p>

      <h2 id="where" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        Where Indian nurses use OET
      </h2>
      <RegulatorComparisonTable />
      <p className="text-gray-600 leading-relaxed mb-4">
        The US doesn't have one national board — check the TruMerit/CGFNS national pathway or your target
        state directly in our{' '}
        <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
          free OET Score Calculator
        </Link>
        .
      </p>

      <h2 id="test-centres" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        OET test centres in India
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET is available at test centres in most major Indian cities, and the network changes over
        time. Find your nearest current centre and book directly through{' '}
        <a href="https://oet.com" target="_blank" rel="noopener noreferrer" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
          oet.com
        </a>{' '}
        rather than a third-party listing, so you're seeing the actual current locations and dates.
      </p>

      <h2 id="common-challenges" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        Common challenges
      </h2>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        <li>
          <span className="font-semibold text-[#0F2356]">Register and directness.</span> Clinical
          communication styles taught and practised in India can be more formal or direct than what OET's
          patient-centred criteria reward — examiners specifically look for warmth, checking-in, and
          involving the patient in the conversation.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Unscripted improvisation.</span> The interlocutor
          reacts in real time, so a memorised script falls apart the moment they say something unexpected.
          This is usually the single biggest score-killer.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Exam-day nerves.</span> Many strong English
          speakers underperform simply because they haven't roleplayed the format enough times to feel
          comfortable with it.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Limited speaking practice partners.</span> Reading
          and Writing can be self-studied from books; Speaking needs another person (or an AI patient) to
          practise against, which is harder to arrange consistently.
        </li>
      </ul>

      <RegulatorCTA regulatorName="OET score you need" />

      <h2 id="how-to-prepare" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        How to prepare
      </h2>
      <ol className="list-decimal pl-5 space-y-2 text-gray-600 mb-4">
        <li>Confirm the exact score your target regulator requires before you book the test.</li>
        <li>
          Learn the format cold — see our{' '}
          <Link href="/learn/what-is-oet-speaking" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
            OET Speaking guide
          </Link>
          .
        </li>
        <li>Practise full roleplays regularly, not just vocabulary lists.</li>
        <li>Record yourself, or get scored feedback, so you know what to fix — not just how it felt.</li>
        <li>Repeat scenarios you found hard until the structure becomes automatic.</li>
      </ol>
      <p className="text-gray-600 leading-relaxed mb-4">
        SpeakOET is built for exactly this: unlimited AI patient roleplay, available whenever you have time
        to practise, with the same structured feedback an examiner would give.
      </p>

      <div id="mistakes">
        <CommonMistakes />
      </div>

      <FaqSection faqs={faqs} />

      <div id="related">
        <RelatedOetPages currentSlug="india" />
      </div>

      <RegulatorCTA regulatorName="OET score you need" />
    </main>
  )
}
