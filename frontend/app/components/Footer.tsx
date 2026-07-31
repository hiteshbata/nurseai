'use client'

import Link from 'next/link'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'
import { useSupabaseSession } from '@/lib/supabase'

export function Footer() {
  const currentYear = new Date().getFullYear()
  const { status } = useSupabaseSession()
  const pricingHref = status === 'authenticated' ? '/upgrade' : '/pricing'

  return (
    <footer style={{ backgroundColor: '#0F2356' }} className="text-white pt-16 pb-8">
      <div className="max-w-6xl mx-auto px-4">
        {/* 5 columns, brand spans 2 -- grid-cols-6 left one column empty, so
            the links stopped two-thirds across and the footer read lopsided. */}
        <div className="grid md:grid-cols-5 gap-8 mb-10">
          {/* Column 1 — Brand */}
          <div className="md:col-span-2">
            <SpeakOETLogo height={28} variant="full" theme="light" />
            <p className="text-white/70 text-sm mt-4">
              AI-powered OET preparation for nurses
            </p>
            <a
              href="mailto:support@speakoet.com"
              className="text-white/70 hover:text-white transition text-sm block mt-2"
            >
              support@speakoet.com
            </a>
            {/* Social icons */}
            <div className="flex items-center gap-4 mt-4">
              <a
                href="https://www.instagram.com/speakoet"
                target="_blank"
                rel="noopener noreferrer"
                className="text-white/60 hover:text-[#10B981] transition-colors duration-200"
                aria-label="Instagram"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="2" width="20" height="20" rx="5" ry="5"/>
                  <circle cx="12" cy="12" r="4"/>
                  <circle cx="17.5" cy="6.5" r="0.5" fill="currentColor"/>
                </svg>
              </a>
              <a
                href="https://youtube.com/@speakoet"
                target="_blank"
                rel="noopener noreferrer"
                className="text-white/60 hover:text-[#10B981] transition-colors duration-200"
                aria-label="YouTube"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22.54 6.42a2.78 2.78 0 0 0-1.95-1.96C18.88 4 12 4 12 4s-6.88 0-8.59.46a2.78 2.78 0 0 0-1.95 1.96A29 29 0 0 0 1 12a29 29 0 0 0 .46 5.58A2.78 2.78 0 0 0 3.41 19.54C5.12 20 12 20 12 20s6.88 0 8.59-.46a2.78 2.78 0 0 0 1.95-1.96A29 29 0 0 0 23 12a29 29 0 0 0-.46-5.58z"/>
                  <polygon points="9.75 15.02 15.5 12 9.75 8.98 9.75 15.02"/>
                </svg>
              </a>
              <a
                href="https://www.linkedin.com/company/speak-oet/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-white/60 hover:text-[#10B981] transition-colors duration-200"
                aria-label="LinkedIn"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"/>
                  <rect x="2" y="9" width="4" height="12"/>
                  <circle cx="4" cy="4" r="2"/>
                </svg>
              </a>
            </div>
          </div>

          {/* Column 2 — Product */}
          <div>
            <h3 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-white/50">Product</h3>
            <ul className="text-sm">
              <li>
                <Link href="/practice/speaking" className="inline-flex items-center min-h-11 md:min-h-0 md:py-1.5 text-white/70 hover:text-white transition">
                  Speaking Practice
                </Link>
              </li>
              <li>
                <Link href="/#how-it-works" className="inline-flex items-center min-h-11 md:min-h-0 md:py-1.5 text-white/70 hover:text-white transition">
                  How It Works
                </Link>
              </li>
              <li>
                <Link href={pricingHref} className="inline-flex items-center min-h-11 md:min-h-0 md:py-1.5 text-white/70 hover:text-white transition">
                  Pricing
                </Link>
              </li>
              <li>
                <Link href="/tools/oet-score-calculator" className="inline-flex items-center min-h-11 md:min-h-0 md:py-1.5 text-white/70 hover:text-white transition">
                  Score Calculator
                </Link>
              </li>
              <li>
                <Link href="/tools/ai-study-plan-generator" className="inline-flex items-center min-h-11 md:min-h-0 md:py-1.5 text-white/70 hover:text-white transition">
                  AI Study Plan Generator
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 3 — Learn */}
          <div>
            <h3 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-white/50">Learn</h3>
            <ul className="text-sm">
              {[
                { href: "/learn/what-is-oet-speaking", label: "What is OET Speaking" },
                { href: "/learn/oet-band-scores", label: "OET Band Scores" },
                { href: "/learn/oet-vs-ielts", label: "OET vs IELTS" },
                { href: "/learn/oet-speaking-tips", label: "OET Speaking Tips" },
                { href: "/oet/india", label: "OET for Indian Nurses" },
              ].map(({ href, label }) => (
                <li key={href}>
                  <Link href={href} className="inline-flex items-center min-h-11 md:min-h-0 md:py-1.5 text-white/70 hover:text-white transition">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Column 4 — Company */}
          <div>
            <h3 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-white/50">Company</h3>
            <ul className="text-sm">
              {/* Privacy and Terms moved to the bottom bar -- legal links are
                  utility, not a marketing column. Leaves 3/5/3 columns. */}
              {[
                { href: "/about", label: "About" },
                { href: "/support", label: "Support" },
                { href: "/blog", label: "Blog" },
              ].map(({ href, label }) => (
                <li key={href}>
                  <Link href={href} className="inline-flex items-center min-h-11 md:min-h-0 md:py-1.5 text-white/70 hover:text-white transition">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Above the divider, not buried under the copyright -- it is the one
            legally required line in here. */}
        <p className="mb-6 max-w-3xl text-xs leading-relaxed text-white/60">
          SpeakOET is an independent preparation platform. OET is a registered trademark of Cambridge Boxhill Language Assessment Pty Ltd. SpeakOET is not affiliated with or endorsed by the official exam board.
        </p>

        <div className="flex flex-col gap-3 border-t border-white/10 pt-6 text-sm text-white/50 md:flex-row md:items-center md:justify-between">
          <p>&copy; {currentYear} SpeakOET. All rights reserved.</p>
          <div className="flex items-center gap-3">
            <Link href="/privacy" className="hover:text-white transition">
              Privacy
            </Link>
            <span aria-hidden="true">&middot;</span>
            <Link href="/terms" className="hover:text-white transition">
              Terms
            </Link>
          </div>
        </div>
      </div>
    </footer>
  )
}
