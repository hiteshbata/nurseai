'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Bot, ArrowRight } from 'lucide-react'
import api, { isUpgradeRequiredError } from '@/lib/api'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { UpgradeRequired } from '@/components/UpgradeRequired'

interface CoachResponse {
  summary: string
  key_issue: string
  why_it_happens: string
  next_action: string
  recommended_practice: { part: 'A' | 'B' | 'C'; reason: string }
}

const PART_LABELS: Record<string, string> = { A: 'Part A', B: 'Part B', C: 'Part C' }

/** E2.3 -- AI Coach card for Listening. Backend (GET /listening/coach)
 * already returns the same fixed shape for the AI answer, the "not enough
 * history yet" deterministic response, and the AI-failure fallback, so this
 * component doesn't special-case any of those -- it just renders whatever
 * shape comes back. Only upgrade-required (403) and rate-limit/network
 * errors need their own state. */
export function ListeningCoachCard() {
  const router = useRouter()
  const [data, setData] = useState<CoachResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [upgradeRequired, setUpgradeRequired] = useState(false)
  const [error, setError] = useState(false)

  const load = useCallback(() => {
    setIsLoading(true)
    setError(false)
    setUpgradeRequired(false)
    api
      .get('/listening/coach')
      .then((res) => setData(res.data))
      .catch((err) => {
        if (isUpgradeRequiredError(err)) setUpgradeRequired(true)
        else setError(true)
      })
      .finally(() => setIsLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (isLoading) {
    return (
      <Card className="p-6 mt-8 animate-pulse">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-full bg-muted shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="h-3 bg-muted rounded w-1/4" />
            <div className="h-3 bg-muted rounded w-full" />
            <div className="h-3 bg-muted rounded w-2/3" />
          </div>
        </div>
      </Card>
    )
  }

  if (upgradeRequired) {
    return (
      <UpgradeRequired
        className="mt-8"
        title="Listening AI Coach is a Basic/Pro/Elite feature"
        message="Upgrade your plan to get a personalized breakdown of your Listening mistakes and what to practice next."
      />
    )
  }

  if (error || !data) {
    return (
      <Card className="p-6 mt-8">
        <p className="text-sm text-muted-foreground mb-3">Couldn't load your Listening Coach right now.</p>
        <Button variant="outline" onClick={load}>Try again</Button>
      </Card>
    )
  }

  return (
    <Card className="p-6 mt-8 border-indigo-100 bg-indigo-50/30">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center shrink-0">
          <Bot className="w-4 h-4 text-indigo-600" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-indigo-600 mb-1">AI Coach</h2>
          <p className="font-semibold text-gray-800">{data.summary}</p>
          <p className="text-sm text-gray-600 mt-2">{data.key_issue}</p>
          <p className="text-sm text-gray-500 mt-1">{data.why_it_happens}</p>
          <p className="text-sm text-gray-800 mt-3 font-medium">Next: {data.next_action}</p>

          <div className="mt-4 flex items-center justify-between gap-3 flex-wrap bg-white/70 rounded-lg px-4 py-3">
            <div className="min-w-0">
              <span className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
                Recommended: {PART_LABELS[data.recommended_practice.part] || data.recommended_practice.part}
              </span>
              <p className="text-sm text-gray-600 mt-0.5">{data.recommended_practice.reason}</p>
            </div>
            <Button size="sm" onClick={() => router.push('/practice/listening')} className="shrink-0">
              Practice now <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          </div>
        </div>
      </div>
    </Card>
  )
}
