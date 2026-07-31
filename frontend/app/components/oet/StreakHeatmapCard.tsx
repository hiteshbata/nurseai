'use client'

import { useMemo } from 'react'
import Link from 'next/link'

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
      <div className="bg-card rounded-2xl border border-border p-6 w-full animate-pulse">
        <div className="h-8 bg-muted rounded w-1/2 mb-4" />
        <div className="grid grid-cols-7 gap-1.5">
          {Array.from({ length: 28 }, (_, i) => (
            <div key={i} className="aspect-square rounded-md bg-muted" />
          ))}
        </div>
        <div className="h-4 bg-muted rounded w-1/3 mt-3" />
      </div>
    )
  }

  return (
    <div className="bg-card rounded-2xl border border-border p-6 w-full motion-safe:animate-[message-in_0.4s_ease-out_0.48s_both]">
      <div className="mb-4">
        <h2 className="text-2xl font-bold text-foreground">
          {streak > 0 ? `🔥 ${streak}-day streak` : 'No active streak'}
        </h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          {streak > 0 ? 'Practice today to keep it' : 'Start a session to begin your streak'}
        </p>
        {streak === 0 && (
          <Link
            href="/practice/speaking"
            className="inline-block mt-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white hover:bg-primary/90"
          >
            Start Practicing
          </Link>
        )}
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
                practiced ? 'bg-accent' : 'bg-muted'
              } ${isToday ? 'ring-2 ring-muted-foreground ring-offset-1' : ''}`}
              title={`${key}: ${practiced ? 'practiced' : 'not practiced'}`}
            />
          )
        })}
      </div>

      <p className="text-xs text-muted-foreground mt-3">
        Last 28 days · {daysPracticed} day{daysPracticed !== 1 ? 's' : ''} practiced
      </p>
    </div>
  )
}
