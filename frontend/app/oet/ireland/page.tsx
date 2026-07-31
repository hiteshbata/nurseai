import Link from 'next/link'
import type { Metadata } from 'next'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'
import { RegulatorScoreTable } from '@/components/oet/RegulatorScoreTable'
import { RegulatorProcessInfo } from '@/components/oet/RegulatorProcessInfo'
import { RegulatorAtAGlance } from '@/components/oet/RegulatorAtAGlance'
import { CommonMistakes } from '@/components/oet/CommonMistakes'
import { RelatedOetPages } from '@/components/oet/RelatedOetPages'
import { RegulatorCTA } from '@/components/oet/RegulatorCTA'
import { RegulatorComparisonTable } from '@/components/oet/RegulatorComparisonTable'
import { FaqSection } from '@/components/seo/FaqSection'
import { OetPageJsonLd } from '@/components/seo/OetPageJsonLd'

const TITLE = 'OET Requirements for NMBI (Ireland) — Score Guide for Nurses'
const DESCRIPTION =
  "The exact OET score the NMBI requires for Irish nurse registration, sourced from OET's own regulator directory, plus how to prepare."

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/oet/ireland' },
}

const toc = [
  { id: 'requirement', label: 'Minimum OET score for the NMBI' },
  { id: 'combining', label: 'Combining two sittings' },
  { id: 'validity', label: 'How long is my score valid?' },
  { id: 'registration', label: 'Registration process overview' },
  { id: 'prepare', label: 'How to prepare' },
  { id: 'mistakes', label: 'Common mistakes' },
  { id: 'compare', label: 'NMBI vs other regulators' },
  { id: 'faq', label: 'FAQ' },
  { id: 'related', label: 'Related guides' },
]

const faqs = [
  {
    q: 'Does the NMBI accept OET for Irish nurse registration?',
    a: 'Yes. The Nursing and Midwifery Board of Ireland (NMBI) accepts OET as an approved English language test for internationally-trained nurses.',
  },
  {
    q: "What's the minimum OET score the NMBI requires?",
    a: "Grade B (350/500) in all four sub-tests — Listening, Reading, Writing, and Speaking. Confirm the current figure directly on the NMBI's own page before you book, since requirements can change.",
  },
  {
    q: 'Can I combine scores from two OET sittings for NMBI registration?',
    a: "Some regulators allow combining results from two sittings within a set window if you meet the minimum in every sub-test across the two attempts. Check the NMBI's current combining policy directly rather than assuming.",
  },
  {
    q: 'Does the NMBI accept IELTS instead of OET?',
    a: "Yes — the NMBI also accepts IELTS Academic alongside OET. OET tends to suit nurses better because its content mirrors real clinical scenarios rather than general topics — see our full OET vs IELTS comparison.",
  },
]

export default function OetIrelandPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <OetPageJsonLd path="/oet/ireland" title={TITLE} description={DESCRIPTION} datePublished="2026-07-27" />

      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">OET Requirements for the NMBI (Ireland)</h1>
      <p className="text-gray-500 text-lg mb-2">
        What score the Nursing and Midwifery Board of Ireland requires from OET, and how to prepare for it.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        Yes — the NMBI accepts OET as an approved English-language test for internationally-trained
        nurses registering to work in Ireland.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        Before checking the requirements, you can estimate your current level using our{' '}
        <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline">
          OET Score Calculator
        </Link>{' '}
        and practise with{' '}
        <Link href="/auth/register" className="text-[#0F2356] font-semibold underline">
          free OET Speaking roleplays
        </Link>
        .
      </p>
      <ArticleMeta date="2026-07-27" />
      <TableOfContents items={toc} />
      <RegulatorAtAGlance regulatorId="nmbi" />

      <h2 id="requirement" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        Minimum OET score for the NMBI
      </h2>
      <RegulatorScoreTable regulatorId="nmbi" />
      <p className="text-gray-600 leading-relaxed mb-4">
        You need to meet Grade B in every sub-test in one sitting, or combine two sittings if the NMBI's
        current policy allows it for your case. Not sure where your scores stand? Use our free{' '}
        <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline">
          OET Score Calculator
        </Link>{' '}
        to check instantly against the NMBI and other regulators.
      </p>

      <h2 id="combining" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        Combining two sittings
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        If you fall short in one sub-test, some regulators let you combine results from two sittings taken
        within a set window instead of retaking everything. Combining rules change, so verify the NMBI's
        current policy on their own site rather than relying on a forum post or an old blog.
      </p>

      <RegulatorProcessInfo
        regulatorName="the NMBI"
        sourceUrl="https://oet.com/test/who-recognises-oet/recognising-organisations/ireland"
      />

      <RegulatorCTA regulatorName="NMBI requirement" />

      <h2 id="prepare" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        How to prepare for the NMBI OET requirement
      </h2>
      <p className="text-gray-600 leading-relaxed mb-3">
        If you're aiming for Irish registration, focus on the areas that commonly prevent candidates from
        achieving the required scores.
      </p>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        <li>Practise realistic OET Speaking roleplays.</li>
        <li>Learn how OET grades convert into scores.</li>
        <li>Avoid common Speaking mistakes that reduce your mark.</li>
      </ul>
      <p className="text-gray-600 font-semibold mb-2">Helpful guides:</p>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        <li>
          <Link href="/learn/what-is-oet-speaking" className="text-[#0F2356] font-semibold underline">
            What is OET Speaking?
          </Link>
        </li>
        <li>
          <Link href="/learn/oet-band-scores" className="text-[#0F2356] font-semibold underline">
            OET Band Scores Explained
          </Link>
        </li>
        <li>
          <Link href="/learn/oet-speaking-tips" className="text-[#0F2356] font-semibold underline">
            OET Speaking Tips
          </Link>
        </li>
      </ul>

      <div id="mistakes">
        <CommonMistakes />
      </div>

      <h2 id="compare" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        NMBI OET requirement compared with other regulators
      </h2>
      <RegulatorComparisonTable currentSlug="ireland" />

      <FaqSection faqs={faqs} />

      <div id="related">
        <RelatedOetPages currentSlug="ireland" />
      </div>

      <RegulatorCTA regulatorName="NMBI requirement" />
    </main>
  )
}
