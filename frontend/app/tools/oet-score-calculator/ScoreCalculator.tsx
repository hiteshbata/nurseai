'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams, useRouter, usePathname } from 'next/navigation'
import {
  REGULATORS,
  MODULE_LABELS,
  FOUR_WEEK_PLANS,
  compareToRequirement,
  scoreToGrade,
  GRADE_ORDER,
  type OetGrade,
  type OetModule,
  type PassStatus,
} from '@/lib/oetScoring'

const MODULES: OetModule[] = ['listening', 'reading', 'writing', 'speaking']
const GRADES: OetGrade[] = ['A', 'B', 'C+', 'C', 'D', 'E']

// Grouped by country for the <optgroup>-based picker -- a flat 40+ option
// list (mostly individual US state boards) is unusable without this.
const REGULATORS_BY_COUNTRY = REGULATORS.reduce<Record<string, typeof REGULATORS>>((acc, r) => {
  ;(acc[r.country] ??= []).push(r)
  return acc
}, {})

type Mode = 'grade' | 'number'
type Inputs = Record<OetModule, string>

const EMPTY_INPUTS: Inputs = { listening: '', reading: '', writing: '', speaking: '' }

function StatusBadge({ status }: { status: PassStatus }) {
  if (status === 'pass') {
    return <span className="text-emerald-600 font-bold" aria-label="Meets requirement">✓</span>
  }
  if (status === 'fail') {
    return <span className="text-red-500 font-bold" aria-label="Below requirement">✕</span>
  }
  return <span className="text-amber-500 font-bold" aria-label="Borderline, enter exact score">?</span>
}

export function ScoreCalculator() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()

  const [mode, setMode] = useState<Mode>((searchParams.get('mode') as Mode) || 'grade')
  const [inputs, setInputs] = useState<Inputs>(() => ({
    listening: searchParams.get('l') || '',
    reading: searchParams.get('r') || '',
    writing: searchParams.get('w') || '',
    speaking: searchParams.get('s') || '',
  }))
  const [targetId, setTargetId] = useState(searchParams.get('reg') || 'nmc')
  const [copied, setCopied] = useState(false)

  const allFilled = MODULES.every((m) => inputs[m] !== '')

  // Shareable URL: reflect current inputs in the query string so the result
  // can be copied and reopened without any account or backend storage.
  useEffect(() => {
    if (!allFilled) return
    const params = new URLSearchParams({
      mode,
      l: inputs.listening,
      r: inputs.reading,
      w: inputs.writing,
      s: inputs.speaking,
      reg: targetId,
    })
    router.replace(`${pathname}?${params.toString()}`, { scroll: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, inputs, targetId, allFilled])

  const userValues = useMemo(() => {
    if (!allFilled) return null
    const entries = MODULES.map((m) => {
      if (mode === 'number') {
        const score = Number(inputs[m])
        return [m, { mode: 'number' as const, score }] as const
      }
      return [m, { mode: 'grade' as const, grade: inputs[m] as OetGrade }] as const
    })
    return Object.fromEntries(entries) as Record<OetModule, { mode: 'number'; score: number } | { mode: 'grade'; grade: OetGrade }>
  }, [inputs, mode, allFilled])

  const target = REGULATORS.find((r) => r.id === targetId) ?? REGULATORS[0]

  const targetResults = useMemo(() => {
    if (!userValues) return null
    return MODULES.map((m) => ({
      module: m,
      status: compareToRequirement(userValues[m], target.requirements[m]),
    }))
  }, [userValues, target])

  // The CTA sentence: the weakest module against the selected regulator.
  // Number mode ranks by exact point gap. Grade mode ranks by how many grade
  // bands short the user is (a grade is a band, so a precise point gap would
  // be a guess -- see oetScoring.ts); borderline results rank below a
  // confirmed fail of any size but above a pass.
  const weakest = useMemo(() => {
    if (!userValues || !targetResults) return null
    let worst: { module: OetModule; status: PassStatus; gap: number } | null = null
    for (const { module, status } of targetResults) {
      if (status === 'pass') continue
      const required = target.requirements[module]
      const value = userValues[module]
      const gap =
        value.mode === 'number'
          ? required - value.score
          : status === 'borderline'
          ? 0.5
          : GRADE_ORDER.indexOf(scoreToGrade(required)) - GRADE_ORDER.indexOf(value.grade)
      if (!worst || gap > worst.gap) worst = { module, status, gap }
    }
    return worst
  }, [userValues, targetResults, target])

  function handleCopyLink() {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div>
      <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
          <div className="inline-flex rounded-lg border border-gray-200 p-1 text-sm">
            <button
              type="button"
              onClick={() => setMode('grade')}
              className={`px-3 py-1.5 rounded-md font-medium transition ${mode === 'grade' ? 'bg-[#0F2356] text-white' : 'text-gray-500'}`}
            >
              I have grades
            </button>
            <button
              type="button"
              onClick={() => setMode('number')}
              className={`px-3 py-1.5 rounded-md font-medium transition ${mode === 'number' ? 'bg-[#0F2356] text-white' : 'text-gray-500'}`}
            >
              I have numbers (0-500)
            </button>
          </div>

          <label className="text-sm text-gray-500 flex items-center gap-2">
            Check against
            <select
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm font-medium text-[#0F2356]"
            >
              {Object.entries(REGULATORS_BY_COUNTRY).map(([country, regs]) => (
                <optgroup key={country} label={country}>
                  {regs.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {MODULES.map((m) => (
            <div key={m}>
              <label className="block text-sm font-semibold text-[#0F2356] mb-1.5" htmlFor={`input-${m}`}>
                {MODULE_LABELS[m]}
              </label>
              {mode === 'grade' ? (
                <select
                  id={`input-${m}`}
                  value={inputs[m]}
                  onChange={(e) => setInputs((prev) => ({ ...prev, [m]: e.target.value }))}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">Select grade</option>
                  {GRADES.map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id={`input-${m}`}
                  type="number"
                  min={0}
                  max={500}
                  step={10}
                  value={inputs[m]}
                  onChange={(e) => setInputs((prev) => ({ ...prev, [m]: e.target.value }))}
                  placeholder="0-500"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {allFilled && userValues && targetResults && (
        <div className="mt-8">
          <div
            className={`rounded-2xl p-6 mb-8 text-center ${
              weakest ? 'bg-amber-50 border border-amber-200' : 'bg-emerald-50 border border-emerald-200'
            }`}
          >
            {weakest ? (
              <>
                <p className="text-lg font-bold text-[#0F2356]">
                  {weakest.status === 'borderline'
                    ? `Your ${MODULE_LABELS[weakest.module]} is borderline against the ${target.name} requirement — enter your exact score above for certainty.`
                    : mode === 'number'
                    ? `Your ${MODULE_LABELS[weakest.module]} is ${weakest.gap} points below the ${target.name} requirement.`
                    : `Your ${MODULE_LABELS[weakest.module]} doesn't yet meet the ${target.name} requirement.`}
                </p>
                <p className="text-gray-600 mt-2">Here&apos;s a 4-week plan to close it.</p>
              </>
            ) : (
              <p className="text-lg font-bold text-emerald-700">
                Your scores meet {target.name}&apos;s requirement on every sub-test — check the table
                below for other regulators you might be considering.
              </p>
            )}
          </div>

          <div className="overflow-x-auto rounded-2xl border border-gray-200 bg-white shadow-sm mb-8">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th scope="col" className="px-4 py-3 text-left font-bold text-[#0F2356]">
                    Regulator
                  </th>
                  {MODULES.map((m) => (
                    <th key={m} scope="col" className="px-4 py-3 text-center font-bold text-[#0F2356]">
                      {MODULE_LABELS[m]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {REGULATORS.map((reg, i) => (
                  <tr key={reg.id} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50/60'}>
                    <th scope="row" className="px-4 py-3 text-left font-medium text-gray-700">
                      {reg.name}
                      <span className="block text-xs text-gray-400 font-normal">{reg.country}</span>
                    </th>
                    {MODULES.map((m) => (
                      <td key={m} className="px-4 py-3 text-center">
                        <StatusBadge status={compareToRequirement(userValues[m], reg.requirements[m])} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {weakest && (
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm mb-8">
              <h2 className="text-lg font-bold text-[#0F2356] mb-4">
                4-week plan: {MODULE_LABELS[weakest.module]}
              </h2>
              <ol className="space-y-4">
                {FOUR_WEEK_PLANS[weakest.module].map((step) => (
                  <li key={step.title} className="flex gap-3">
                    <span className="shrink-0 text-sm font-bold text-[#0F2356] w-16">{step.title}</span>
                    <span className="text-sm text-gray-600">{step.body}</span>
                  </li>
                ))}
              </ol>
              <Link
                href="/auth/register"
                className="mt-6 inline-flex items-center justify-center bg-[#0F2356] text-white font-semibold px-6 py-3 rounded-xl hover:bg-[#0F2356]/90 transition-colors"
              >
                Start practicing {MODULE_LABELS[weakest.module]} free →
              </Link>
            </div>
          )}

          <div className="text-center">
            <button
              type="button"
              onClick={handleCopyLink}
              className="text-sm text-gray-500 hover:text-[#0F2356] underline"
            >
              {copied ? 'Link copied!' : 'Copy a link to this result'}
            </button>
          </div>
        </div>
      )}

      <p className="text-xs text-gray-400 mt-6 text-center">
        Grade input uses the low end of each grade&apos;s numeric band ({scoreToGrade(350)} = 350+), so a
        result marked <span className="text-amber-500 font-bold">?</span> means enter your exact number
        for a precise check. Regulator requirements change — always confirm on the regulator&apos;s own
        site before you rely on this.
      </p>
    </div>
  )
}
