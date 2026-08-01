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

const TITLE = 'OET Requirements for the NMC (UK) — Score Guide for Nurses'
const DESCRIPTION =
  "The exact OET score the NMC requires for UK nurse registration, sourced from OET's own regulator directory, plus how to prepare and where to verify current combining rules."

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/oet/uk' },
}

const toc = [
  { id: 'requirement', label: 'Minimum OET score for the NMC' },
  { id: 'combining', label: 'Combining two sittings' },
  { id: 'validity', label: 'How long is my score valid?' },
  { id: 'registration', label: 'Registration process overview' },
  { id: 'prepare', label: 'How to prepare' },
  { id: 'mistakes', label: 'Common mistakes' },
  { id: 'compare', label: 'NMC vs other regulators' },
  { id: 'faq', label: 'FAQ' },
  { id: 'related', label: 'Related guides' },
]

const faqs = [
  {
    q: 'Does the NMC accept OET for UK nurse registration?',
    a: 'Yes. The Nursing and Midwifery Council (NMC) accepts OET as one of its approved English language tests for internationally-trained nurses and midwives joining the UK register.',
  },
  {
    q: "What's the minimum OET score the NMC requires?",
    a: "At least Grade B (350/500) in Listening, Reading, and Speaking, and Grade C+ (300/500) in Writing — see the table above. Confirm the current figure on the NMC's own page before you book, since requirements can change.",
  },
  {
    q: 'Can I combine scores from two OET sittings for NMC registration?',
    a: "Many regulators allow combining results from two sittings taken within a set window if you meet the minimum in every sub-test across the two attempts. Combining rules vary and change — check the NMC's current policy directly rather than assuming yours qualifies.",
  },
  {
    q: 'Does the NMC accept IELTS instead of OET?',
    a: 'Yes, the NMC accepts both OET and IELTS Academic. Many nurses prefer OET because its content is built around real clinical scenarios rather than general topics — see our full OET vs IELTS comparison.',
  },
]

export default function OetUkPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <OetPageJsonLd path="/oet/uk" title={TITLE} description={DESCRIPTION} datePublished="2026-07-27" />

      <div className="motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mt-4 mb-4">OET Requirements for the NMC (UK)</h1>
        <p className="text-gray-500 text-lg mb-2">
          What score the Nursing and Midwifery Council (NMC) requires from OET, and how to prepare for it.
        </p>
        <p className="text-gray-600 leading-relaxed mb-4">
          Yes — the NMC accepts OET as an approved English-language test for nurses and midwives
          registering to work in the UK.
        </p>
        <p className="text-gray-600 leading-relaxed mb-4">
          Before checking the requirements, you can estimate your current level using our{' '}
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
      <RegulatorAtAGlance regulatorId="nmc" />

      <h2 id="requirement" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        Minimum OET score for the NMC
      </h2>
      <RegulatorScoreTable regulatorId="nmc" />
      <p className="text-gray-600 leading-relaxed mb-4">
        You need to meet the minimum in every sub-test in one sitting, or combine two sittings if the NMC's
        current policy allows it for your case. Not sure where your scores stand? Use our free{' '}
        <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
          OET Score Calculator
        </Link>{' '}
        to check instantly against the NMC and other regulators.
      </p>

      <h2 id="combining" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        Combining two sittings
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        If you fall short in one sub-test, some regulators let you combine results from two sittings taken
        within a set window instead of retaking everything. Combining rules change, so verify the NMC's
        current policy on their own site rather than relying on a forum post or an old blog.
      </p>

      <RegulatorProcessInfo
        regulatorName="the NMC"
        sourceUrl="https://www.nmc.org.uk/registration/joining-the-register/english-language-requirements/accepted-english-language-tests/"
      />

      <RegulatorCTA regulatorName="NMC requirement" />

      <h2 id="prepare" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        How to prepare for the NMC OET requirement
      </h2>
      <p className="text-gray-600 leading-relaxed mb-3">
        If you're aiming for UK registration, focus on the areas that commonly prevent candidates from
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
          <Link href="/learn/what-is-oet-speaking" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
            What is OET Speaking?
          </Link>
        </li>
        <li>
          <Link href="/learn/oet-band-scores" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
            OET Band Scores Explained
          </Link>
        </li>
        <li>
          <Link href="/learn/oet-speaking-tips" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
            OET Speaking Tips
          </Link>
        </li>
      </ul>

      <div id="mistakes">
        <CommonMistakes />
      </div>

      <h2 id="compare" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        NMC OET requirement compared with other regulators
      </h2>
      <RegulatorComparisonTable currentSlug="uk" />

      <FaqSection faqs={faqs} />

      <div id="related">
        <RelatedOetPages currentSlug="uk" />
      </div>

      <RegulatorCTA regulatorName="NMC requirement" />
    </main>
  )
}
