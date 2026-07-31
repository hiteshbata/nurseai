'use client'

import { useState } from "react"
import { Mic, Check } from "lucide-react"
import { useRouter } from "next/navigation"

function ChecklistDot({ done }: { done: boolean }) {
  return (
    <span
      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
        done ? "bg-emerald-500 text-white" : "border-2 border-gray-200"
      }`}
    >
      {done && <Check className="h-3.5 w-3.5" aria-hidden="true" />}
    </span>
  )
}

export function FirstRunHero({
  examDateSet,
  targetBandSet,
  onSetExamDate,
  savingExamDate,
}: {
  examDateSet: boolean
  targetBandSet: boolean
  onSetExamDate?: (date: string) => void
  savingExamDate?: boolean
}) {
  const router = useRouter()
  const [isEditingDate, setIsEditingDate] = useState(false)
  const [dateValue, setDateValue] = useState('')

  const handleSaveDate = () => {
    if (dateValue && onSetExamDate) {
      onSetExamDate(dateValue)
      setIsEditingDate(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 motion-safe:animate-[message-in_0.4s_ease-out_both]">
      <div className="flex flex-col gap-5 rounded-2xl bg-primary p-8 text-primary-foreground shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-balance">Start your first 5-minute roleplay</h2>
          <p className="mt-1 max-w-md text-primary-foreground/70">
            Talk to an AI patient and get your first 9-criteria OET score in minutes.
          </p>
        </div>
        <button
          onClick={() => router.push("/practice/speaking")}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-white px-6 py-3 text-sm font-bold text-primary transition hover:opacity-90"
        >
          <Mic className="h-4 w-4" aria-hidden="true" />
          Start Speaking Practice
        </button>
      </div>

      <div className="rounded-2xl border border-gray-100 bg-card p-6 shadow-sm">
        <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-muted-foreground">Get started</h3>
        <ul className="space-y-3">
          <li className="flex items-center gap-3">
            <ChecklistDot done={examDateSet} />
            {examDateSet ? (
              <span className="text-sm font-medium text-gray-400 line-through">Set your exam date</span>
            ) : isEditingDate ? (
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  autoFocus
                  value={dateValue}
                  onChange={(e) => setDateValue(e.target.value)}
                  className="rounded-lg border border-gray-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
                <button
                  onClick={handleSaveDate}
                  disabled={!dateValue || savingExamDate}
                  className="rounded-lg bg-primary px-3 py-1 text-sm font-semibold text-primary-foreground transition disabled:opacity-50"
                >
                  {savingExamDate ? "Saving…" : "Set"}
                </button>
              </div>
            ) : onSetExamDate ? (
              <button
                onClick={() => setIsEditingDate(true)}
                className="text-sm font-medium text-gray-700 transition hover:text-primary"
              >
                Set your exam date
              </button>
            ) : (
              <a href="/profile" className="text-sm font-medium text-gray-700 transition hover:text-primary">
                Set your exam date
              </a>
            )}
          </li>

          <li className="flex items-center gap-3">
            <ChecklistDot done={targetBandSet} />
            {targetBandSet ? (
              <span className="text-sm font-medium text-gray-400 line-through">Set your target band</span>
            ) : (
              <a href="/profile" className="text-sm font-medium text-gray-700 transition hover:text-primary">
                Set your target band
              </a>
            )}
          </li>

          <li className="flex items-center gap-3">
            <ChecklistDot done={false} />
            <a href="/practice/speaking" className="text-sm font-medium text-gray-700 transition hover:text-primary">
              Do your first 5-minute speaking roleplay
            </a>
          </li>

          <li className="flex items-center gap-3">
            <ChecklistDot done={false} />
            <span className="text-sm font-medium text-gray-700">Get your baseline OET band</span>
          </li>
        </ul>
      </div>
    </div>
  )
}
