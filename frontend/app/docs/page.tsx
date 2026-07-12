import Link from 'next/link'
import type { Metadata } from 'next'
import { docsGuides } from './guides'

export const metadata: Metadata = {
  title: 'Docs',
  description: 'Guides for using SpeakOET — practice speaking, practice writing, mock tests, and account settings.',
}

export default function DocsPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold text-[#0F2356] mb-4">Docs</h1>
      <p className="text-gray-500 text-lg mb-10">
        Guides for getting the most out of SpeakOET. Looking for something else?{' '}
        <Link href="/support" className="text-[#0F2356] font-semibold underline">
          Visit Support
        </Link>
        .
      </p>

      <div className="grid gap-4">
        {docsGuides.map((guide) => (
          <Link
            key={guide.href}
            href={guide.href}
            className="rounded-2xl border border-gray-100 bg-white shadow-sm p-6 hover:shadow-md transition"
          >
            <p className="font-semibold text-[#0F2356] mb-1">{guide.title}</p>
            <p className="text-gray-500 text-sm">{guide.description}</p>
          </Link>
        ))}
      </div>
    </main>
  )
}
