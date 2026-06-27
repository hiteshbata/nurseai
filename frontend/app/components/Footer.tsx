'use client'

import Link from 'next/link'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'

export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer style={{ backgroundColor: '#0F2356' }} className="text-white py-12">
      <div className="max-w-6xl mx-auto px-4">
        <div className="grid md:grid-cols-3 gap-8 mb-8">
          {/* Column 1 — Brand */}
          <div>
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
          </div>

          {/* Column 2 — Practice */}
          <div>
            <h4 className="text-white font-semibold mb-4">Practice</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/practice/speaking" className="text-white/70 hover:text-white transition">
                  Speaking Practice
                </Link>
              </li>
              <li>
                <Link href="/practice/writing" className="text-white/70 hover:text-white transition">
                  Writing Practice
                </Link>
              </li>
              <li>
                <span className="text-white/50">
                  Mock Test <span className="text-amber-400 text-xs ml-1">Coming Soon</span>
                </span>
              </li>
              <li>
                <Link href="/dashboard" className="text-white/70 hover:text-white transition">
                  Progress
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 3 — Support */}
          <div>
            <h4 className="text-white font-semibold mb-4">Support</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a href="mailto:support@speakoet.com" className="text-white/70 hover:text-white transition">
                  Contact
                </a>
              </li>
              <li>
                <span className="text-white/50 cursor-default">Privacy Policy</span>
              </li>
              <li>
                <span className="text-white/50 cursor-default">Terms of Service</span>
              </li>
            </ul>
          </div>
        </div>

        <div className="border-t border-white/10 pt-6 flex flex-col md:flex-row items-center justify-between text-sm text-white/50">
          <p>&copy; {currentYear} SpeakOET. All rights reserved.</p>
          <p className="mt-2 md:mt-0">Made for nurses worldwide 🌏</p>
        </div>
      </div>
    </footer>
  )
}
