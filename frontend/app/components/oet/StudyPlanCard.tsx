'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface WeakCriterion {
  key: string
  label: string
  average: number | null
}

interface RecommendedScenario {
  id: number
  title: string
  difficulty: string | null
}

interface StudyPlanData {
  locked: boolean
  ready: boolean
  upgrade_required: boolean
  message?: string
  weekly_focus?: string
  why_it_matters?: string
  action_steps?: string[]
  pacing_note?: string
  weak_criteria?: WeakCriterion[]
  recommended_scenarios?: RecommendedScenario[]
  weeks_to_exam?: number | null
}

export function StudyPlanCard() {
  const router = useRouter()
  const [data, setData] = useState<StudyPlanData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .get('/progress/study-plan')
      .then((res) => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="rounded-2xl bg-white border border-slate-200 p-5 animate-pulse">
        <div className="h-3 bg-slate-100 rounded w-1/3 mb-3" />
        <div className="h-5 bg-slate-100 rounded w-2/3 mb-2" />
        <div className="h-3 bg-slate-100 rounded w-full mb-1" />
        <div className="h-3 bg-slate-100 rounded w-5/6" />
      </div>
    )
  }

  if (!data) return null

  if (data.locked) {
    return (
      <div className="rounded-2xl bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-100 p-5">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center shrink-0 text-sm">
            🔒
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600 mb-1">
              AI Study Plan
            </p>
            <p className="text-sm text-slate-600 mb-3">
              Get a personalized weekly plan built from your weakest OET criteria — which scenarios to
              practice next and exactly what to focus on. Elite feature.
            </p>
            <a
              href="/upgrade"
              className="inline-block bg-[#0F2356] text-white rounded-lg px-4 py-2 text-sm font-semibold hover:bg-[#0F2356]/90 transition"
            >
              Upgrade to Elite →
            </a>
          </div>
        </div>
      </div>
    )
  }

  if (!data.ready) {
    return (
      <div className="rounded-2xl bg-white border border-dashed border-slate-200 p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600 mb-1">
          AI Study Plan
        </p>
        <p className="text-sm text-slate-400">{data.message}</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl bg-white border border-slate-200 p-5">
      <div className="flex items-center justify-between gap-2 mb-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
          🎯 Your Weekly Study Plan
        </p>
        {typeof data.weeks_to_exam === 'number' && (
          <span className="text-xs font-semibold bg-amber-100 text-amber-700 px-2.5 py-1 rounded-full shrink-0">
            {data.weeks_to_exam} week{data.weeks_to_exam !== 1 ? 's' : ''} to exam
          </span>
        )}
      </div>

      <h3 className="text-lg font-bold text-slate-800 mb-1">{data.weekly_focus}</h3>
      {data.why_it_matters && (
        <p className="text-sm text-slate-600 mb-3">{data.why_it_matters}</p>
      )}

      {data.weak_criteria && data.weak_criteria.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {data.weak_criteria.map((c) => (
            <span
              key={c.key}
              className="text-xs font-semibold bg-red-50 text-red-600 px-2.5 py-1 rounded-full"
            >
              {c.label}{c.average !== null ? ` · ${c.average}/6` : ''}
            </span>
          ))}
        </div>
      )}

      {data.action_steps && data.action_steps.length > 0 && (
        <ul className="space-y-1.5 mb-4">
          {data.action_steps.map((step, i) => (
            <li key={i} className="flex gap-2 text-sm text-slate-700">
              <span className="shrink-0 text-indigo-500">✓</span>
              <span>{step}</span>
            </li>
          ))}
        </ul>
      )}

      {data.recommended_scenarios && data.recommended_scenarios.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Recommended Scenarios
          </p>
          <div className="flex flex-wrap gap-2">
            {data.recommended_scenarios.map((s) => (
              <button
                key={s.id}
                onClick={() => router.push(`/practice/speaking?scenario=${s.id}`)}
                className="text-sm bg-indigo-50 text-indigo-700 px-3 py-1.5 rounded-lg font-medium hover:bg-indigo-100 transition"
              >
                {s.title} →
              </button>
            ))}
          </div>
        </div>
      )}

      {data.pacing_note && (
        <p className="text-xs text-slate-400 italic">{data.pacing_note}</p>
      )}
    </div>
  )
}
