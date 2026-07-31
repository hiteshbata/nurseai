'use client'

import { useState } from "react"
import { Calendar, TrendingUp, Trophy } from "lucide-react"

export function HeroCards({
  examDaysLeft,
  currentGrade,
  targetBand,
  onSetExamDate,
  savingExamDate,
}: {
  examDaysLeft: number | null
  currentGrade: string
  targetBand: string
  onSetExamDate?: (date: string) => void
  savingExamDate?: boolean
}) {
  const [isEditing, setIsEditing] = useState(false)
  const [dateValue, setDateValue] = useState('')

  const handleSave = () => {
    if (dateValue && onSetExamDate) {
      onSetExamDate(dateValue)
      setIsEditing(false)
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 motion-safe:animate-[message-in_0.4s_ease-out_both]">
      {/* Days until exam — navy */}
      <div className="flex flex-col justify-between rounded-2xl border border-primary bg-primary p-6 text-primary-foreground shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-primary-foreground/70">
            Days until exam
          </span>
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-foreground/10">
            <Calendar className="h-5 w-5" aria-hidden="true" />
          </span>
        </div>

        {examDaysLeft !== null ? (
          <p className="mt-6 text-5xl font-bold tabular-nums">{examDaysLeft}</p>
        ) : isEditing ? (
          <div className="mt-6 flex items-center gap-2">
            <input
              type="date"
              autoFocus
              value={dateValue}
              onChange={(e) => setDateValue(e.target.value)}
              className="rounded-lg bg-white/10 px-2 py-1.5 text-sm text-white [color-scheme:dark] focus:outline-none focus:ring-2 focus:ring-white/40"
            />
            <button
              onClick={handleSave}
              disabled={!dateValue || savingExamDate}
              className="rounded-lg bg-white px-3 py-1.5 text-sm font-semibold text-primary transition disabled:opacity-50"
            >
              {savingExamDate ? 'Saving…' : 'Set'}
            </button>
          </div>
        ) : onSetExamDate ? (
          <button
            onClick={() => setIsEditing(true)}
            className="mt-6 self-start text-sm font-semibold text-white underline decoration-white/40 underline-offset-4 transition hover:decoration-white"
          >
            Set your exam date →
          </button>
        ) : (
          <p className="mt-6 text-5xl font-bold tabular-nums">—</p>
        )}
      </div>

      {/* Current level — emerald accent */}
      <div className="flex flex-col justify-between rounded-2xl border border-gray-100 bg-card p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-muted-foreground">
            Current Level
          </span>
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-50">
            <TrendingUp className="h-5 w-5 text-accent" aria-hidden="true" />
          </span>
        </div>
        <p className="mt-6 text-5xl font-bold text-emerald-700">{currentGrade}</p>
      </div>

      {/* Target band — navy accent */}
      <div className="flex flex-col justify-between rounded-2xl border border-gray-100 bg-card p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-muted-foreground">
            Target Band
          </span>
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-secondary">
            <Trophy className="h-5 w-5 text-primary" aria-hidden="true" />
          </span>
        </div>
        <p className="mt-6 text-5xl font-bold text-primary">{targetBand}</p>
      </div>
    </div>
  )
}
