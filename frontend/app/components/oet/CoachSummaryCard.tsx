'use client'

import { useState, useEffect } from 'react'
import { Bot } from 'lucide-react'
import api from '@/lib/api'

export function CoachSummaryCard() {
  const [summary, setSummary] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .get('/progress/coach-summary')
      .then((res) => {
        setSummary(res.data.summary_text)
        setMessage(res.data.message)
      })
      .catch(() => setMessage('Could not load coach summary.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="rounded-2xl bg-card border border-border p-5 animate-pulse">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-full bg-muted shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="h-3 bg-muted rounded w-1/4" />
            <div className="h-3 bg-muted rounded w-full" />
            <div className="h-3 bg-muted rounded w-2/3" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-2xl bg-card border border-border p-5 motion-safe:animate-[message-in_0.4s_ease-out_0.36s_both]">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center shrink-0">
          <Bot className="w-4 h-4 text-indigo-600" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-indigo-600 mb-0.5">
            AI Coach
          </h2>
          {summary ? (
            <p className="text-sm text-foreground/90 leading-relaxed">{summary}</p>
          ) : (
            <p className="text-sm text-muted-foreground">{message || 'No summary available.'}</p>
          )}
        </div>
      </div>
    </div>
  )
}
