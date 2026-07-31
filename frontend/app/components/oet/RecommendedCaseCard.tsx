'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Star } from 'lucide-react'
import api from '@/lib/api'

interface CaseData {
  scenario_id: number
  title: string
  difficulty: string
  reason: string
}

export function RecommendedCaseCard() {
  const router = useRouter()
  const [rec, setRec] = useState<CaseData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .get('/speaking/scenarios/recommend')
      .then((res) => setRec(res.data))
      .catch(() => setRec(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="w-full rounded-2xl p-5 animate-pulse bg-gradient-to-r from-slate-50 to-slate-100" style={{ background: 'linear-gradient(135deg, #f0fdf4, #dcfce7)' }}>
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-col gap-2 flex-1">
            <div className="h-4 bg-emerald-200 rounded w-1/4" />
            <div className="h-6 bg-slate-200 rounded w-3/4" />
            <div className="h-4 bg-slate-200 rounded w-1/2" />
          </div>
          <div className="w-12 h-12 rounded-full bg-emerald-200 shrink-0" />
        </div>
      </div>
    )
  }

  if (!rec) {
    return (
      <div className="w-full rounded-2xl p-5 bg-white border border-dashed border-slate-200 motion-safe:animate-[message-in_0.4s_ease-out_both]">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Recommended for you
          </span>
          <p className="text-sm text-slate-400 mb-3">
            Complete a speaking session to get a personalized recommendation.
          </p>
          <Link
            href="/practice/speaking"
            className="inline-block rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white hover:bg-primary/90 self-start"
          >
            Start Practicing
          </Link>
        </div>
      </div>
    )
  }

  const diffLabel =
    rec.difficulty === 'beginner' || rec.difficulty === 'easy'
      ? 'Beginner'
      : rec.difficulty === 'advanced' || rec.difficulty === 'hard'
        ? 'Advanced'
        : 'Medium'

  return (
    <button
      onClick={() => router.push(`/practice/speaking?scenario=${rec.scenario_id}`)}
      className="w-full text-left rounded-2xl p-5 flex items-center justify-between gap-4 cursor-pointer hover:opacity-90 hover:shadow-md active:opacity-80 active:scale-[0.99] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 motion-safe:animate-[message-in_0.4s_ease-out_both]"
      style={{ background: 'linear-gradient(135deg, #f0fdf4, #dcfce7)' }}
      aria-label={`Start ${rec.title} case`}
    >
      <div className="flex flex-col gap-1 min-w-0">
        <span className="text-xs font-semibold uppercase tracking-wide text-emerald-700 flex items-center gap-1">
          <Star className="w-3.5 h-3.5" aria-hidden="true" /> Recommended for you
        </span>
        <h3 className="text-xl font-bold text-slate-800 text-balance truncate">
          {rec.title}
        </h3>
        <p className="text-sm text-slate-500 truncate">
          {diffLabel} · {rec.reason}
        </p>
      </div>

      <div
        className="flex-shrink-0 flex items-center justify-center rounded-full text-white text-lg shadow-sm"
        style={{ width: 48, height: 48, backgroundColor: '#047857' }}
        aria-hidden="true"
      >
        ▶
      </div>
    </button>
  )
}
