import Link from 'next/link'
import { OET_COUNTRY_PAGES } from '@/app/oet/countries'
import { RevealOnScroll } from '@/components/RevealOnScroll'

const linkClass =
  'text-[#0F2356] font-semibold underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2'

export function RelatedOetPages({ currentSlug }: { currentSlug: string }) {
  const others = OET_COUNTRY_PAGES.filter((p) => p.slug !== currentSlug)

  return (
    <RevealOnScroll>
      <h2 className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">Related guides</h2>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        {others.map((page) => (
          <li key={page.slug}>
            <Link href={`/oet/${page.slug}`} className={linkClass}>
              OET {page.label}
            </Link>
          </li>
        ))}
        <li>
          <Link href="/learn/oet-vs-ielts" className={linkClass}>
            OET vs IELTS
          </Link>
        </li>
      </ul>
    </RevealOnScroll>
  )
}
