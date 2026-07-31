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
      <div className="rounded-2xl bg-white border border-slate-200 p-5 animate-pulse">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-full bg-slate-100 shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="h-3 bg-slate-100 rounded w-1/4" />
            <div className="h-3 bg-slate-100 rounded w-full" />
            <div className="h-3 bg-slate-100 rounded w-2/3" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-2xl bg-white border border-slate-200 p-5">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center shrink-0">
          <Bot className="w-4 h-4 text-indigo-600" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600 mb-0.5">
            AI Coach
          </p>
          {summary ? (
            <p className="text-sm text-slate-700 leading-relaxed">{summary}</p>
          ) : (
            <p className="text-sm text-slate-400">{message || 'No summary available.'}</p>
          )}
        </div>
      </div>
    </div>
  )
}
