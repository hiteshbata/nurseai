'use client'

import { useState } from 'react'
import Link from 'next/link'
import api from '@/lib/api'
import {
  REGULATORS,
  MODULE_LABELS,
  gradeToFloorScore,
  type OetGrade,
  type OetModule,
} from '@/lib/oetScoring'

const MODULES: OetModule[] = ['listening', 'reading', 'writing', 'speaking']
const GRADES: OetGrade[] = ['A', 'B', 'C+', 'C', 'D', 'E']

const REGULATORS_BY_COUNTRY = REGULATORS.reduce<Record<string, typeof REGULATORS>>((acc, r) => {
  ;(acc[r.country] ??= []).push(r)
  return acc
}, {})

type Mode = 'grade' | 'number'
type Inputs = Record<OetModule, string>

const EMPTY_INPUTS: Inputs = { listening: '', reading: '', writing: '', speaking: '' }

interface Week {
  title: string
  focus: string
  action_steps: string[]
}

interface PlanResult {
  weakest_module: OetModule | null
  gap: number
  summary: string
  weeks: Week[]
  pacing_note: string
}

export function StudyPlanGenerator() {
  const [mode, setMode] = useState<Mode>('grade')
  const [inputs, setInputs] = useState<Inputs>(EMPTY_INPUTS)
  const [targetId, setTargetId] = useState('nmc')
  const [examDate, setExamDate] = useState('')
  const [hoursPerWeek, setHoursPerWeek] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [plan, setPlan] = useState<PlanResult | null>(null)

  const allFilled = MODULES.every((m) => inputs[m] !== '')
  const target = REGULATORS.find((r) => r.id === targetId) ?? REGULATORS[0]

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!allFilled) return
    setLoading(true)
    setError(null)
    setPlan(null)

    const scores = Object.fromEntries(
      MODULES.map((m) => [
        m,
        mode === 'number' ? Number(inputs[m]) : gradeToFloorScore(inputs[m] as OetGrade),
      ])
    )

    let weeksUntilExam: number | null = null
    if (examDate) {
      const days = Math.ceil((new Date(examDate).getTime() - Date.now()) / 86_400_000)
      weeksUntilExam = Math.max(0, Math.ceil(days / 7))
    }

    try {
      const res = await api.post('/tools/study-plan', {
        scores,
        target_requirements: target.requirements,
        target_regulator_name: target.name,
        weeks_until_exam: weeksUntilExam,
        hours_per_week: hoursPerWeek ? Number(hoursPerWeek) : null,
      })
      setPlan(res.data)
    } catch (err: any) {
      setError(
        err?.response?.status === 429
          ? 'Too many requests — please try again in a while.'
          : "Couldn't generate your plan right now — please try again."
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit} className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
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
            Target regulator
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

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
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

        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-semibold text-[#0F2356] mb-1.5" htmlFor="exam-date">
              Exam date (optional)
            </label>
            <input
              id="exam-date"
              type="date"
              value={examDate}
              onChange={(e) => setExamDate(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-semibold text-[#0F2356] mb-1.5" htmlFor="hours-per-week">
              Hours available per week (optional)
            </label>
            <input
              id="hours-per-week"
              type="number"
              min={1}
              max={100}
              value={hoursPerWeek}
              onChange={(e) => setHoursPerWeek(e.target.value)}
              placeholder="e.g. 8"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={!allFilled || loading}
          className="mt-6 w-full inline-flex items-center justify-center bg-[#0F2356] text-white font-semibold px-6 py-3 rounded-xl hover:bg-[#0F2356]/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Generating your plan…' : 'Generate my AI study plan'}
        </button>
      </form>

      {error && (
        <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-center text-sm text-red-700">
          {error}
        </div>
      )}

      {plan && (
        <div className="mt-8">
          <div
            className={`rounded-2xl p-6 mb-8 text-center ${
              plan.weakest_module ? 'bg-amber-50 border border-amber-200' : 'bg-emerald-50 border border-emerald-200'
            }`}
          >
            <p className="text-lg font-bold text-[#0F2356]">{plan.summary}</p>
            {plan.pacing_note && <p className="text-gray-600 mt-2">{plan.pacing_note}</p>}
          </div>

          {plan.weeks.length > 0 && (
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm mb-8">
              <h2 className="text-lg font-bold text-[#0F2356] mb-4">Your plan</h2>
              <ol className="space-y-5">
                {plan.weeks.map((week) => (
                  <li key={week.title}>
                    <p className="font-bold text-[#0F2356] text-sm mb-1">
                      {week.title} — {week.focus}
                    </p>
                    <ul className="list-disc pl-5 space-y-1">
                      {week.action_steps.map((step) => (
                        <li key={step} className="text-sm text-gray-600">
                          {step}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ol>
              {plan.weakest_module && (
                <Link
                  href="/auth/register"
                  className="mt-6 inline-flex items-center justify-center bg-[#0F2356] text-white font-semibold px-6 py-3 rounded-xl hover:bg-[#0F2356]/90 transition-colors"
                >
                  Start practicing {MODULE_LABELS[plan.weakest_module]} free →
                </Link>
              )}
            </div>
          )}

          <p className="text-center text-sm text-gray-500">
            Want a plan that updates automatically as you practice?{' '}
            <Link href="/pricing" className="text-[#0F2356] font-semibold underline">
              Elite includes a live AI coach
            </Link>{' '}
            built from your actual session history.
          </p>
        </div>
      )}
    </div>
  )
}
