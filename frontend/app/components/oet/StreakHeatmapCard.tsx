'use client'

import { useMemo } from 'react'

function getLast28Days(): Date[] {
  const days: Date[] = []
  const now = new Date()
  for (let i = 27; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    days.push(d)
  }
  return days
}

function dateToStr(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function calcStreak(allDates: Set<string>): number {
  let streak = 0
  const now = new Date()
  for (let i = 0; i < 365; i++) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    if (allDates.has(dateToStr(d))) {
      streak++
    } else {
      break
    }
  }
  return streak
}

export function StreakHeatmapCard({
  practicedDates,
  isLoading,
}: {
  practicedDates: string[]
  isLoading?: boolean
}) {
  const days = useMemo(() => getLast28Days(), [])

  const practicedSet = useMemo(() => new Set(practicedDates), [practicedDates])
  const streak = useMemo(() => calcStreak(practicedSet), [practicedSet])
  const daysPracticed = useMemo(
    () => days.filter((d) => practicedSet.has(dateToStr(d))).length,
    [days, practicedSet]
  )

  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-6 w-full animate-pulse">
        <div className="h-8 bg-slate-100 rounded w-1/2 mb-4" />
        <div className="grid grid-cols-7 gap-1.5">
          {Array.from({ length: 28 }, (_, i) => (
            <div key={i} className="aspect-square rounded-md bg-slate-100" />
          ))}
        </div>
        <div className="h-4 bg-slate-100 rounded w-1/3 mt-3" />
      </div>
    )
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6 w-full">
      <div className="mb-4">
        <p className="text-2xl font-bold text-slate-800">
          {streak > 0 ? `🔥 ${streak}-day streak` : 'No active streak'}
        </p>
        <p className="text-sm text-slate-500 mt-0.5">
          {streak > 0 ? 'Practice today to keep it' : 'Start a session to begin your streak'}
        </p>
      </div>

      <div className="grid grid-cols-7 gap-1.5">
        {days.map((d, i) => {
          const key = dateToStr(d)
          const practiced = practicedSet.has(key)
          const isToday = i === days.length - 1
          return (
            <div
              key={key}
              className={`aspect-square rounded-md transition-colors ${
                practiced ? 'bg-teal-600' : 'bg-slate-100'
              } ${isToday ? 'ring-2 ring-slate-400 ring-offset-1' : ''}`}
              title={`${key}: ${practiced ? 'practiced' : 'not practiced'}`}
            />
          )
        })}
      </div>

      <p className="text-xs text-slate-400 mt-3">
        Last 28 days · {daysPracticed} day{daysPracticed !== 1 ? 's' : ''} practiced
      </p>
    </div>
  )
}
