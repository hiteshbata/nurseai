'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Star } from 'lucide-react'
import api from '@/lib/api'
import { MODULE_META } from './ModuleProgressCard'
import type { ModuleName, NextBestAction } from './types'

const MODULE_RECOMMEND_ENDPOINT: Record<ModuleName, string> = {
  speaking: '/speaking/scenarios/recommend',
  writing: '/writing/scenarios/recommend',
  reading: '/reading/tests/recommend',
  listening: '/listening/tests/recommend',
}

type RecommendedItem = {
  title: string
  reason: string
  scenario_id?: number
}

export function AdaptiveRecommendationCard({ nextBestAction }: { nextBestAction: NextBestAction }) {
  const router = useRouter()
  const [item, setItem] = useState<RecommendedItem | null>(null)
  const [loading, setLoading] = useState(!!nextBestAction)

  useEffect(() => {
    if (!nextBestAction) {
      setLoading(false)
      return
    }
    setLoading(true)
    api
      .get(MODULE_RECOMMEND_ENDPOINT[nextBestAction.module])
      .then((res) => setItem(res.data))
      .catch(() => setItem(null))
      .finally(() => setLoading(false))
  }, [nextBestAction])

  if (loading) {
    return (
      <div className="w-full rounded-2xl p-5 animate-pulse bg-muted" style={{ background: 'linear-gradient(135deg, #f0fdf4, #dcfce7)' }}>
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-col gap-2 flex-1">
            <div className="h-4 bg-emerald-200 rounded w-1/4" />
            <div className="h-6 bg-muted rounded w-3/4" />
            <div className="h-4 bg-muted rounded w-1/2" />
          </div>
          <div className="w-12 h-12 rounded-full bg-emerald-200 shrink-0" />
        </div>
      </div>
    )
  }

  if (!nextBestAction || !item) {
    return (
      <div className="w-full rounded-2xl p-5 bg-card border border-dashed border-border">
        <div className="flex flex-col gap-1">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Adaptive Recommendation
          </h2>
          <p className="text-sm text-muted-foreground mb-3">
            Complete a session in any module to get a personalized recommendation.
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

  const meta = MODULE_META[nextBestAction.module]
  const href = nextBestAction.module === 'speaking' && item.scenario_id
    ? `${meta.href}?scenario=${item.scenario_id}`
    : meta.href

  return (
    <button
      onClick={() => router.push(href)}
      className="w-full text-left rounded-2xl p-5 flex items-center justify-between gap-4 cursor-pointer hover:opacity-90 hover:shadow-md active:opacity-80 active:scale-[0.99] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
      style={{ background: 'linear-gradient(135deg, #f0fdf4, #dcfce7)' }}
      aria-label={`Start ${item.title} in ${meta.label}`}
    >
      <div className="flex flex-col gap-1 min-w-0">
        <span className="text-xs font-semibold uppercase tracking-wide text-emerald-700 flex items-center gap-1">
          <Star className="w-3.5 h-3.5" aria-hidden="true" /> Next Best Action · {meta.label}
        </span>
        <h3 className="text-xl font-bold text-foreground text-balance truncate">
          {item.title}
        </h3>
        <p className="text-sm text-muted-foreground truncate">{nextBestAction.reason}</p>
        <p className="text-xs text-muted-foreground/80">{nextBestAction.confidence_message}</p>
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
