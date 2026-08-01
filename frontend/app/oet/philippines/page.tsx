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

const TITLE = 'OET for Filipino Nurses — Requirements, Challenges, How to Prepare'
const DESCRIPTION =
  'What Filipino nurses need to know about OET: how it fits alongside PRC licensure, which destinations (UK, Australia, Canada, UAE and more) accept it, common challenges, and how to prepare.'

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/oet/philippines' },
}

const toc = [
  { id: 'prc', label: 'OET vs your PRC license' },
  { id: 'where', label: 'Where Filipino nurses use OET' },
  { id: 'test-centres', label: 'OET test centres in the Philippines' },
  { id: 'common-challenges', label: 'Common challenges' },
  { id: 'how-to-prepare', label: 'How to prepare' },
  { id: 'mistakes', label: 'Common mistakes' },
  { id: 'faq', label: 'FAQ' },
  { id: 'related', label: 'Related guides' },
]

const faqs = [
  {
    q: 'Does OET replace my PRC nursing license?',
    a: "No. OET only satisfies the English-language requirement that most destination regulators ask for. You still need your PRC license recognised or converted through the destination country's own credentialing process — OET is one piece of that pathway, not a substitute for it.",
  },
  {
    q: 'Which OET score do I need as a Filipino nurse?',
    a: "It depends entirely on your destination regulator — the UK's NMC, Australia's Ahpra, Canada's provincial boards, and the Gulf authorities (DHA, DOH, MOHAP) each set their own minimum. Check your specific target in the comparison table below, or run your scores through our free OET Score Calculator.",
  },
  {
    q: 'Is OET or IELTS more common among Filipino nurses?',
    a: "Both are widely accepted. Many Filipino nurses choose OET because the content is built around real clinical scenarios rather than general English topics, so preparation feels more directly useful for the job you're going to. See our full OET vs IELTS comparison.",
  },
  {
    q: 'Where can Filipino-trained nurses use an OET result?',
    a: 'The UK, Australia, Ireland, New Zealand, and Canada all accept OET for nurse registration, as do the UAE\'s three health authorities (DHA, DOH, MOHAP) and the US via the TruMerit/CGFNS pathway or individual state boards. See the comparison table below for each one\'s requirement.',
  },
]

export default function OetPhilippinesPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <OetPageJsonLd path="/oet/philippines" title={TITLE} description={DESCRIPTION} datePublished="2026-07-27" />

      <div className="motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mt-4 mb-4">OET for Filipino Nurses</h1>
        <p className="text-gray-500 text-lg mb-2">
          What Filipino nurses need to know about OET before registering abroad — in the UK, Australia,
          Canada, the Gulf, and beyond.
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

      <h2 id="prc" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        OET vs your PRC license
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Your Professional Regulation Commission (PRC) license proves you're a qualified nurse in the
        Philippines. It doesn't automatically transfer abroad — each destination regulator runs its own
        credential recognition process, separate from English-language testing. OET (or IELTS) satisfies
        only the English requirement inside that larger process. Confirm the full credentialing pathway
        with your destination regulator, not just the language-test piece covered here.
      </p>

      <h2 id="where" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        Where Filipino nurses use OET
      </h2>
      <RegulatorComparisonTable />
      <p className="text-gray-600 leading-relaxed mb-4">
        The Gulf authorities (DHA, DOH, MOHAP) also accept OET — see the{' '}
        <Link href="/oet/uae" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
          UAE page
        </Link>{' '}
        for why we don't publish a score for them here. The US doesn't have one national board either —
        check the TruMerit/CGFNS national pathway or your target state directly in our{' '}
        <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
          free OET Score Calculator
        </Link>
        .
      </p>

      <h2 id="test-centres" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        OET test centres in the Philippines
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET is available at test centres in Manila and other major Philippine cities, and the network
        changes over time. Find your nearest current centre and book directly through{' '}
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
          <span className="font-semibold text-[#0F2356]">Unscripted improvisation.</span> The interlocutor
          reacts in real time, so a memorised script falls apart the moment they say something unexpected.
          This is usually the single biggest score-killer, regardless of how strong your everyday English is.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Patient-centred phrasing.</span> OET's Speaking
          criteria specifically reward warmth, checking-in, and involving the patient — habits worth
          practising deliberately rather than assuming they'll show up under exam pressure.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Limited speaking practice partners.</span> Reading
          and Writing can be self-studied from books; Speaking needs another person (or an AI patient) to
          practise against, which is harder to arrange consistently, especially while still working shifts.
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
        <RelatedOetPages currentSlug="philippines" />
      </div>

      <RegulatorCTA regulatorName="OET score you need" />
    </main>
  )
}
