import Link from 'next/link'
import { MODULE_LABELS, REGULATORS, scoreToGrade, type OetModule } from '@/lib/oetScoring'

const MODULES: OetModule[] = ['listening', 'reading', 'writing', 'speaking']

const COMPARISON_ROWS = [
  { regulatorId: 'nmc', slug: 'uk', label: 'NMC (UK)' },
  { regulatorId: 'ahpra', slug: 'australia', label: 'Ahpra (Australia)' },
  { regulatorId: 'nmbi', slug: 'ireland', label: 'NMBI (Ireland)' },
  { regulatorId: 'nz', slug: 'new-zealand', label: 'Nursing Council (NZ)' },
  { regulatorId: 'canada', slug: 'canada', label: 'Canada (all provinces)' },
]

export function RegulatorComparisonTable({ currentSlug }: { currentSlug?: string }) {
  return (
    <div className="my-8 overflow-x-auto rounded-2xl border border-gray-100 shadow-sm">
      <table className="w-full text-left">
        <thead className="bg-[#0F2356] text-white">
          <tr>
            <th className="px-4 py-3 text-sm font-semibold">Regulator</th>
            {MODULES.map((module) => (
              <th key={module} className="px-4 py-3 text-sm font-semibold">
                {MODULE_LABELS[module]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {COMPARISON_ROWS.map((row, i) => {
            const regulator = REGULATORS.find((r) => r.id === row.regulatorId)
            if (!regulator) return null
            const isCurrent = row.slug === currentSlug
            return (
              <tr
                key={row.slug}
                className={isCurrent ? 'bg-[#F8FAFC] font-semibold' : i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}
              >
                <td className="px-4 py-3 text-gray-700">
                  {isCurrent ? (
                    row.label
                  ) : (
                    <Link href={`/oet/${row.slug}`} className="text-[#0F2356] underline">
                      {row.label}
                    </Link>
                  )}
                </td>
                {MODULES.map((module) => (
                  <td key={module} className="px-4 py-3 text-gray-700">
                    {scoreToGrade(regulator.requirements[module])}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="border-t border-gray-100 bg-gray-50 px-4 py-3 text-xs text-gray-500">
        UAE is intentionally left out — DHA, DOH, and MOHAP each set their own requirement and public
        sources conflict, so see the{' '}
        <Link href="/oet/uae" className="underline">
          UAE page
        </Link>{' '}
        for why we don&apos;t publish a number there. Grades shown are minimums; confirm the current
        figure on each regulator&apos;s own site before you rely on it.
      </div>
    </div>
  )
}
