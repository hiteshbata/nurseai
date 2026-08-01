import Link from 'next/link'
import { Check } from 'lucide-react'
import { RevealOnScroll } from '@/components/RevealOnScroll'

const CHECKLIST = ['Free AI Speaking Practice', 'Instant score estimates', 'Real OET roleplays']

export function RegulatorCTA({ regulatorName }: { regulatorName: string }) {
  return (
    <RevealOnScroll>
      <div className="mt-12 rounded-2xl border border-gray-100 bg-[#F8FAFC] p-8 text-center">
        <h3 className="font-display text-xl font-semibold text-[#0F2356] mb-4">
          Ready to achieve the {regulatorName}?
        </h3>
        <ul className="mb-5 inline-flex flex-col items-start gap-1.5 text-left text-gray-600">
          {CHECKLIST.map((item) => (
            <li key={item} className="flex items-center gap-2">
              <Check className="w-4 h-4 text-[#10B981] shrink-0" strokeWidth={3} aria-hidden="true" />
              {item}
            </li>
          ))}
        </ul>
        <div>
          <Link
            href="/auth/register"
            className="inline-flex items-center justify-center bg-[#10B981] text-white font-semibold px-6 py-3 rounded-lg motion-safe:transition-colors motion-safe:duration-200 hover:bg-[#0ea472] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0F2356] focus-visible:ring-offset-2"
          >
            Start Free Practice
          </Link>
        </div>
      </div>
    </RevealOnScroll>
  )
}
