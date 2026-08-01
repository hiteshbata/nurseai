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

const TITLE = 'OET Requirements for Canada — Score Guide for Nurses (All 13 Provinces)'
const DESCRIPTION =
  "The OET score Canada's provincial and territorial nursing regulators require, sourced from OET's own regulator directory — identical across every province and territory."

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/oet/canada' },
}

const toc = [
  { id: 'requirement', label: 'Minimum OET score for Canada' },
  { id: 'combining', label: 'Combining two sittings' },
  { id: 'validity', label: 'How long is my score valid?' },
  { id: 'registration', label: 'Registration process overview' },
  { id: 'prepare', label: 'How to prepare' },
  { id: 'mistakes', label: 'Common mistakes' },
  { id: 'compare', label: 'Canada vs other regulators' },
  { id: 'faq', label: 'FAQ' },
  { id: 'related', label: 'Related guides' },
]

const faqs = [
  {
    q: 'Does Canada accept OET for nurse registration?',
    a: "Yes. Every one of Canada's 13 provincial and territorial nursing regulators (Ontario, BC, Alberta, and the rest) accepts OET as an approved English language test for internationally-trained nurses.",
  },
  {
    q: "What's the minimum OET score Canada requires?",
    a: 'Grade B (350/500) in Listening and Speaking, and Grade C+ (300/500) in Reading and Writing — identical across every province and territory OET lists. Confirm the current figure directly on your target regulator\'s own page before you book, since requirements can change.',
  },
  {
    q: 'Is the OET requirement really the same in every province?',
    a: "Based on OET's own directory, yes — every provincial/territorial regulator listed (Ontario, BC, Alberta, Manitoba, Saskatchewan, Nova Scotia, New Brunswick, PEI, Newfoundland & Labrador, NWT/Nunavut, Yukon) shows the identical figure. Still confirm on your specific province's regulator site, since healthcare licensing is provincially governed and policy can diverge without notice.",
  },
  {
    q: 'Can I combine scores from two OET sittings for Canadian registration?',
    a: 'Some regulators allow combining results from two sittings within a set window if you meet the minimum in every sub-test across the two attempts. Check your target province\'s current combining policy directly rather than assuming.',
  },
]

export default function OetCanadaPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <OetPageJsonLd path="/oet/canada" title={TITLE} description={DESCRIPTION} datePublished="2026-07-27" />

      <div className="motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mt-4 mb-4">OET Requirements for Canada</h1>
        <p className="text-gray-500 text-lg mb-2">
          What score Canada's provincial and territorial nursing regulators require from OET — the same
          figure across all 13 — and how to prepare for it.
        </p>
        <p className="text-gray-600 leading-relaxed mb-4">
          Yes — every provincial and territorial nursing regulator in Canada accepts OET as an approved
          English-language test for internationally-trained nurses.
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
      <RegulatorAtAGlance regulatorId="canada" />

      <h2 id="requirement" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        Minimum OET score for Canada
      </h2>
      <RegulatorScoreTable regulatorId="canada" />
      <p className="text-gray-600 leading-relaxed mb-4">
        Unlike most countries, nursing licensure in Canada is governed province by province — yet every
        regulator OET lists shows the same requirement. Not sure where your scores stand? Use our free{' '}
        <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2">
          OET Score Calculator
        </Link>{' '}
        to check instantly against Canada and other regulators.
      </p>

      <h2 id="combining" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        Combining two sittings
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        If you fall short in one sub-test, some regulators let you combine results from two sittings taken
        within a set window instead of retaking everything. Combining rules change and can differ by
        province, so verify your target regulator's current policy on their own site rather than relying on
        a forum post or an old blog.
      </p>

      <RegulatorProcessInfo
        regulatorName="your target provincial regulator"
        sourceUrl="https://oet.com/test/who-recognises-oet/recognising-organisations/canada"
      />

      <RegulatorCTA regulatorName="Canadian nursing requirement" />

      <h2 id="prepare" className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">
        How to prepare for the Canadian OET requirement
      </h2>
      <p className="text-gray-600 leading-relaxed mb-3">
        If you're aiming for Canadian registration, focus on the areas that commonly prevent candidates
        from achieving the required scores.
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
        Canada OET requirement compared with other regulators
      </h2>
      <RegulatorComparisonTable currentSlug="canada" />

      <FaqSection faqs={faqs} />

      <div id="related">
        <RelatedOetPages currentSlug="canada" />
      </div>

      <RegulatorCTA regulatorName="Canadian nursing requirement" />
    </main>
  )
}
