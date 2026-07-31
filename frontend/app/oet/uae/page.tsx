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

const TITLE = 'OET Requirements for the UAE (DHA, DOH, MOHAP) — Nurses Guide'
const DESCRIPTION =
  'Which UAE health authority licenses nurses depending on emirate, whether OET is accepted, and where to check the current pass mark directly — DHA, DOH, and MOHAP each set their own.'

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/oet/uae' },
}

const toc = [
  { id: 'authorities', label: 'Which authority licenses you' },
  { id: 'score', label: 'Minimum OET score' },
  { id: 'validity', label: 'How long is my score valid?' },
  { id: 'registration', label: 'Registration process overview' },
  { id: 'prepare', label: 'How to prepare' },
  { id: 'mistakes', label: 'Common mistakes' },
  { id: 'compare', label: 'UAE vs other regulators' },
  { id: 'faq', label: 'FAQ' },
  { id: 'related', label: 'Related guides' },
]

const faqs = [
  {
    q: 'Does the UAE accept OET for nurse licensing?',
    a: 'Yes. All three UAE health regulators — the Dubai Health Authority (DHA), the Department of Health Abu Dhabi (DOH), and the Ministry of Health and Prevention (MOHAP) for the other emirates — recognise OET as an English-proficiency option for internationally-trained nurses.',
  },
  {
    q: "What's the minimum OET score for a UAE nursing license?",
    a: "It depends which authority licenses you — DHA, DOH, and MOHAP each set their own requirement, and these have changed in recent years. We're deliberately not publishing a specific number here because public sources conflict and requirements aren't uniform across emirates. Check the current pass mark directly on the authority's own site linked above before you rely on it.",
  },
  {
    q: 'Which UAE authority do I apply to?',
    a: "Generally DHA if you'll work in Dubai, DOH if you'll work in Abu Dhabi, and MOHAP for the other emirates (Sharjah, Ajman, and the rest). This is based on where the employing facility is licensed, not where you live — confirm with your recruiter or employer.",
  },
  {
    q: 'Does DHA/DOH/MOHAP accept IELTS instead of OET, or exempt some nurses entirely?',
    a: 'Generally yes to IELTS Academic alongside OET. Some nurses whose degree was taught entirely in English are also exempt from an English test altogether — eligibility rules differ by authority, so check yours directly on the relevant site above.',
  },
]

export default function OetUaePage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <OetPageJsonLd path="/oet/uae" title={TITLE} description={DESCRIPTION} datePublished="2026-07-27" />

      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">OET Requirements for the UAE</h1>
      <p className="text-gray-500 text-lg mb-2">
        The UAE has three separate health regulators, each setting its own English-language requirement —
        here's who to check with, and why we're not publishing a single score for all three.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        Yes — OET is accepted for nurse licensing in the UAE, but by three separate authorities
        depending on which emirate you'll work in.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        Before checking who licenses you, you can estimate your current level using our{' '}
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

      <h2 id="authorities" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        Which authority licenses you
      </h2>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        <li>
          <span className="font-semibold text-[#0F2356]">Dubai Health Authority (DHA)</span> — for nurses
          working in Dubai. Official site:{' '}
          <a href="https://www.dha.gov.ae" target="_blank" rel="noopener noreferrer" className="text-[#0F2356] font-semibold underline">
            dha.gov.ae
          </a>
          , including a self-assessment tool for professional qualification requirements.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Department of Health Abu Dhabi (DOH)</span> — for
          nurses working in Abu Dhabi. Official Professional Qualification Requirements for nurses:{' '}
          <a href="https://www.doh.gov.ae/en/pqr/Nurses" target="_blank" rel="noopener noreferrer" className="text-[#0F2356] font-semibold underline">
            doh.gov.ae/en/pqr/Nurses
          </a>
          .
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Ministry of Health and Prevention (MOHAP)</span> —
          for the other emirates (Sharjah, Ajman, and the rest). Official licensing page:{' '}
          <a href="https://mohap.gov.ae/en/w/licensing-or-re-licensing-of-health-professional" target="_blank" rel="noopener noreferrer" className="text-[#0F2356] font-semibold underline">
            mohap.gov.ae
          </a>
          .
        </li>
      </ul>

      <h2 id="score" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        Minimum OET score
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        We show a verified score table for the UK, Australia, Ireland, New Zealand, and Canada on their own
        pages. We're not doing that here: DHA, DOH, and MOHAP publish different requirements from each
        other, sources conflict on the exact current figures, and getting this wrong on a nursing site is a
        permanent trust loss — not just an SEO problem. Use the official links above to confirm the current
        pass mark for your specific authority before you book your test.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        Our{' '}
        <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline">
          free OET Score Calculator
        </Link>{' '}
        deliberately leaves UAE out for the same reason — we'll add it the moment we can verify one
        reliable number per authority.
      </p>

      <h2 id="validity" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        How long is my OET score valid?
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET itself doesn't expire, but each UAE authority sets its own acceptance window for how old a
        result can be at the time you apply — commonly around two years for most nursing regulators,
        though this changes without notice and can differ between DHA, DOH, and MOHAP. Confirm the
        current validity period directly on your target authority's site linked above before you rely
        on an older result.
      </p>

      <h2 id="registration" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        Registration process overview
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Meeting the English-language requirement is one part of licensing with DHA, DOH, or MOHAP — not
        the whole process. The typical path: confirm you meet the qualification and experience criteria
        your target authority publishes, submit your application and supporting documents (including a
        Good Standing Certificate) through their official portal, complete any additional exam or
        assessment they require, then receive your license once everything clears. Steps differ between
        the three authorities and change over time — start from the official site linked above rather
        than a third-party guide.
      </p>

      <RegulatorCTA regulatorName="UAE nursing license" />

      <h2 id="prepare" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        How to prepare for the UAE OET requirement
      </h2>
      <p className="text-gray-600 leading-relaxed mb-3">
        Whichever authority licenses you, focus on the areas that commonly prevent candidates from
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
        UAE compared with other regulators
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        We can't put the UAE in this table for the reason explained above, but here's what the
        regulators we can verify require, for comparison while you decide where to register:
      </p>
      <RegulatorComparisonTable currentSlug="uae" />

      <FaqSection faqs={faqs} />

      <div id="related">
        <RelatedOetPages currentSlug="uae" />
      </div>

      <RegulatorCTA regulatorName="UAE nursing license" />
    </main>
  )
}
