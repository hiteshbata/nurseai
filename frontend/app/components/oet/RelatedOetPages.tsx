import Link from 'next/link'
import { OET_COUNTRY_PAGES } from '@/app/oet/countries'

export function RelatedOetPages({ currentSlug }: { currentSlug: string }) {
  const others = OET_COUNTRY_PAGES.filter((p) => p.slug !== currentSlug)

  return (
    <>
      <h2 className="text-xl font-bold text-[#0F2356] mt-8 mb-3">Related guides</h2>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        {others.map((page) => (
          <li key={page.slug}>
            <Link href={`/oet/${page.slug}`} className="text-[#0F2356] font-semibold underline">
              OET {page.label}
            </Link>
          </li>
        ))}
        <li>
          <Link href="/learn/oet-vs-ielts" className="text-[#0F2356] font-semibold underline">
            OET vs IELTS
          </Link>
        </li>
      </ul>
    </>
  )
}
