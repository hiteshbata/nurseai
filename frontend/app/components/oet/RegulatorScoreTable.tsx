import { MODULE_LABELS, REGULATORS, scoreToGrade, type OetModule } from '@/lib/oetScoring'
import { RevealOnScroll } from '@/components/RevealOnScroll'

const MODULES: OetModule[] = ['listening', 'reading', 'writing', 'speaking']

export function RegulatorScoreTable({ regulatorId }: { regulatorId: string }) {
  const regulator = REGULATORS.find((r) => r.id === regulatorId)
  if (!regulator) return null

  return (
    <RevealOnScroll className="my-8 block overflow-hidden rounded-2xl border border-gray-100 shadow-premium">
      <table className="w-full text-left">
        <thead className="bg-[#0F2356] text-white">
          <tr>
            <th className="px-4 py-3 text-sm font-semibold">Sub-test</th>
            <th className="px-4 py-3 text-sm font-semibold">Minimum score</th>
            <th className="px-4 py-3 text-sm font-semibold">Minimum grade</th>
          </tr>
        </thead>
        <tbody>
          {MODULES.map((module, i) => (
            <tr
              key={module}
              className={`motion-safe:transition-colors motion-safe:duration-200 hover:bg-[#F8FAFC] ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}
            >
              <td className="px-4 py-3 text-gray-700">{MODULE_LABELS[module]}</td>
              <td className="px-4 py-3 text-gray-700">{regulator.requirements[module]}</td>
              <td className="px-4 py-3 text-gray-700">{scoreToGrade(regulator.requirements[module])}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="border-t border-gray-100 bg-gray-50 px-4 py-3 text-xs text-gray-500">
        Source:{' '}
        <a
          href={regulator.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
        >
          {regulator.sourceLabel}
        </a>
        . {regulator.note ? `${regulator.note} ` : ''}
        Regulators change requirements over time — confirm the current pass mark on {regulator.name}&apos;s
        own site before you book your test.
      </div>
    </RevealOnScroll>
  )
}
