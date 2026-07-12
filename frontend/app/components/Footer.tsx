'use client'

import Link from 'next/link'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'
import { useSupabaseSession } from '@/lib/supabase'

export function Footer() {
  const currentYear = new Date().getFullYear()
  const { status } = useSupabaseSession()
  const pricingHref = status === 'authenticated' ? '/upgrade' : '/#pricing'

  return (
    <footer style={{ backgroundColor: '#0F2356' }} className="text-white py-12">
      <div className="max-w-6xl mx-auto px-4">
        <div className="grid md:grid-cols-6 gap-8 mb-8">
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
                href="https://instagram.com/speakoet"
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
                href="https://linkedin.com/company/speakoet"
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
            <h3 className="text-white font-semibold mb-4">Product</h3>
            <ul className="text-sm">
              <li>
                <Link href="/practice/speaking" className="inline-flex items-center min-h-11 text-white/70 hover:text-white transition">
                  Speaking Practice
                </Link>
              </li>
              <li>
                <Link href="/#how-it-works" className="inline-flex items-center min-h-11 text-white/70 hover:text-white transition">
                  How It Works
                </Link>
              </li>
              <li>
                <Link href={pricingHref} className="inline-flex items-center min-h-11 text-white/70 hover:text-white transition">
                  Pricing
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 3 — Learn */}
          <div>
            <h3 className="text-white font-semibold mb-4">Learn</h3>
            <ul className="text-sm">
              {[
                { href: "/learn/what-is-oet-speaking", label: "What is OET Speaking" },
                { href: "/learn/oet-band-scores", label: "OET Band Scores" },
                { href: "/learn/oet-vs-ielts", label: "OET vs IELTS" },
                { href: "/learn/oet-speaking-tips", label: "OET Speaking Tips" },
                { href: "/learn/oet-for-indian-nurses", label: "OET for Indian Nurses" },
              ].map(({ href, label }) => (
                <li key={href}>
                  <Link href={href} className="inline-flex items-center min-h-11 text-white/70 hover:text-white transition">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Column 4 — Company */}
          <div>
            <h3 className="text-white font-semibold mb-4">Company</h3>
            <ul className="text-sm">
              {[
                { href: "/about", label: "About" },
                { href: "/support", label: "Support" },
                { href: "/blog", label: "Blog" },
                { href: "/privacy", label: "Privacy" },
                { href: "/terms", label: "Terms of Service" },
              ].map(({ href, label }) => (
                <li key={href}>
                  <Link href={href} className="inline-flex items-center min-h-11 text-white/70 hover:text-white transition">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="border-t border-white/10 pt-6 flex flex-col md:flex-row items-center justify-between text-sm text-white/50">
          <p>&copy; {currentYear} SpeakOET. All rights reserved.</p>
          <p className="mt-2 md:mt-0">Made for nurses worldwide 🌏</p>
        </div>
        <p className="mt-4 text-xs text-white/40 text-center md:text-left">
          SpeakOET is an independent preparation platform. OET is a registered trademark of Cambridge Boxhill Language Assessment Pty Ltd. SpeakOET is not affiliated with or endorsed by the official exam board.
        </p>
      </div>
    </footer>
  )
}
