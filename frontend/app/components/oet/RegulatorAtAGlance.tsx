import { MODULE_LABELS, REGULATORS, scoreToGrade, type OetModule } from '@/lib/oetScoring'
import { RevealOnScroll } from '@/components/RevealOnScroll'

const MODULES: OetModule[] = ['listening', 'reading', 'writing', 'speaking']

export function RegulatorAtAGlance({ regulatorId }: { regulatorId: string }) {
  const regulator = REGULATORS.find((r) => r.id === regulatorId)
  if (!regulator) return null

  return (
    <RevealOnScroll className="block mb-8 rounded-2xl border border-[#0F2356]/10 bg-[#F8FAFC] p-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-[#0F2356]/60 mb-3">At a glance</p>
      <dl className="grid grid-cols-2 gap-y-2 text-sm text-gray-700 sm:grid-cols-4">
        {MODULES.map((module) => (
          <div key={module}>
            <dt className="text-gray-500">{MODULE_LABELS[module]}</dt>
            <dd className="font-semibold text-[#0F2356]">
              {scoreToGrade(regulator.requirements[module])} ({regulator.requirements[module]})
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-xs text-gray-500">
        Combining two sittings: allowed by some regulators — verify {regulator.name}&apos;s current
        policy. Score validity: commonly around two years, but confirm the current window directly.
      </p>
    </RevealOnScroll>
  )
}
