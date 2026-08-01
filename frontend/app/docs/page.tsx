import Link from 'next/link'
import type { Metadata } from 'next'
import { docsGuides } from './guides'
import { RevealOnScroll } from '@/components/RevealOnScroll'

export const metadata: Metadata = {
  title: 'Docs',
  description: 'Guides for using SpeakOET — practice speaking, practice writing, mock tests, and account settings.',
  alternates: { canonical: '/docs' },
}

export default function DocsPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <div className="motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mb-4">Docs</h1>
        <p className="text-gray-500 text-lg mb-10">
          Guides for getting the most out of SpeakOET. Looking for something else?{' '}
          <Link
            href="/support"
            className="text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
          >
            Visit Support
          </Link>
          .
        </p>
      </div>

      <div className="grid gap-4">
        {docsGuides.map((guide, i) => (
          <RevealOnScroll key={guide.href} delayMs={Math.min(i, 4) * 40}>
            <Link
              href={guide.href}
              className="block rounded-2xl border border-gray-100 bg-white shadow-premium p-6 motion-safe:transition-shadow motion-safe:duration-200 hover:shadow-premium-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
            >
              <p className="font-semibold text-[#0F2356] mb-1">{guide.title}</p>
              <p className="text-gray-500 text-sm">{guide.description}</p>
            </Link>
          </RevealOnScroll>
        ))}
      </div>
    </main>
  )
}
