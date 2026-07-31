import { FaqJsonLd } from './FaqJsonLd'

export function FaqSection({
  faqs,
  heading = 'Frequently Asked Questions',
}: {
  faqs: { q: string; a: string }[]
  heading?: string
}) {
  return (
    <div className="mt-12">
      <FaqJsonLd faqs={faqs} />
      <h2 className="text-2xl font-bold text-[#0F2356] mb-6">{heading}</h2>
      <div className="rounded-2xl overflow-hidden border border-gray-100 shadow-sm bg-white">
        {faqs.map((faq, i) => (
          <div key={faq.q} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
            <div className="px-6 py-5">
              <h3 className="text-[#0F2356] font-semibold text-sm md:text-base leading-snug mb-2">
                {faq.q}
              </h3>
              <p className="text-gray-600 text-sm leading-relaxed">{faq.a}</p>
            </div>
            {i < faqs.length - 1 && <div className="border-b border-gray-100" />}
          </div>
        ))}
      </div>
    </div>
  )
}
