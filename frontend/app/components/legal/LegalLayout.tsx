import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { RevealOnScroll } from '@/components/RevealOnScroll'

export interface LegalSection {
  heading: string
  body: string
  // Optional interactive element rendered after the section's text -- e.g.
  // the "Manage cookie preferences" button on the Privacy Policy's Cookies
  // section. Keeps LegalLayout's sections plain data for every other page.
  action?: ReactNode
}

export function LegalLayout({
  icon: Icon,
  title,
  effectiveDate,
  sections,
}: {
  icon: LucideIcon
  title: string
  effectiveDate: string
  sections: LegalSection[]
}) {
  return (
    <main className="min-h-screen bg-white">
      {/* Hero */}
      <div className="max-w-3xl mx-auto px-4 pt-20 pb-12 text-center motion-safe:animate-[fade-up-in_0.6s_ease-out_both]">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-[#0F2356]/[0.06] mb-5">
          <Icon className="w-5 h-5 text-[#047857]" strokeWidth={1.75} aria-hidden="true" />
        </div>
        <h1 className="font-display text-4xl md:text-5xl font-semibold text-[#0F2356] text-balance leading-[1.1]">
          {title}
        </h1>
        <p className="text-gray-500 text-sm mt-4">Effective Date: {effectiveDate}</p>
      </div>

      <div className="max-w-3xl mx-auto px-4 pb-24">
        {/* On this page */}
        <nav
          aria-label="On this page"
          className="mb-12 rounded-2xl border border-gray-200 p-6 motion-safe:animate-[fade-up-in_0.6s_ease-out_0.05s_both]"
        >
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
            On this page
          </p>
          <ul className="grid sm:grid-cols-2 gap-x-6">
            {sections.map(({ heading }) => (
              <li key={heading}>
                <a
                  href={`#${slugify(heading)}`}
                  className="block py-3 text-sm text-[#0F2356]/80 hover:text-[#047857] transition-colors rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
                >
                  {heading}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex flex-col gap-6">
          {sections.map(({ heading, body, action }) => (
            <RevealOnScroll key={heading}>
              <section
                id={slugify(heading)}
                className="scroll-mt-24 rounded-2xl border border-gray-200 p-7 shadow-premium"
              >
                <h2 className="font-display text-xl font-semibold text-[#0F2356] mb-3">{heading}</h2>
                {body.split('\n\n').map((paragraph, p) => (
                  <p
                    key={p}
                    className="text-gray-600 leading-relaxed mb-3 last:mb-0 whitespace-pre-line"
                  >
                    {paragraph}
                  </p>
                ))}
                {action && <div className="mt-4">{action}</div>}
              </section>
            </RevealOnScroll>
          ))}
        </div>
      </div>
    </main>
  )
}

function slugify(heading: string) {
  return heading
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}
