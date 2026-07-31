'use client'

import { useMountReveal } from '@/app/hooks/useMountReveal'

const gradePoints: Record<string, number> = {
  E: 0,
  D: 1,
  C: 2,
  "C+": 3,
  B: 4,
  A: 5,
}

export function ProgressSection({
  baselineGrade,
  currentGrade,
  targetBand,
}: {
  baselineGrade: string
  currentGrade: string
  targetBand: string
}) {
  const currentValue = gradePoints[currentGrade] ?? 0
  const targetValue = gradePoints[targetBand] ?? 5

  // If Now equals Target, show 95% (reached target)
  // Otherwise calculate: (points[Now] / points[Target]) * 100, capped at 95%
  let progressPercent = 0
  if (currentGrade === targetBand) {
    progressPercent = 95
  } else {
    progressPercent = (currentValue / targetValue) * 100
    progressPercent = Math.min(95, progressPercent)
  }

  const clamped = Math.min(100, Math.max(0, progressPercent))
  const revealed = useMountReveal()

  return (
    <section className="rounded-2xl border border-gray-100 bg-card p-6 shadow-sm motion-safe:animate-[message-in_0.4s_ease-out_both]">
      <h2 className="text-lg font-bold text-primary">Your Journey</h2>

      <div className="mt-6">
        <div
          className="relative h-3 w-full overflow-hidden rounded-full bg-secondary"
          role="progressbar"
          aria-valuenow={clamped}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Progress toward target band"
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-emerald-600 transition-[width] duration-[1100ms] ease-[cubic-bezier(0.16,1,0.3,1)]"
            style={{ width: revealed ? `${clamped}%` : '0%' }}
          />
        </div>

        <div className="mt-4 grid grid-cols-3 text-center">
          <div className="text-left">
            <p className="text-xs font-medium text-muted-foreground">Start</p>
            <p className="text-sm font-bold text-primary">{baselineGrade}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Now</p>
            <p className="text-sm font-bold text-emerald-700">{currentGrade}</p>
          </div>
          <div className="text-right">
            <p className="text-xs font-medium text-muted-foreground">Target</p>
            <p className="text-sm font-bold text-primary">{targetBand}</p>
          </div>
        </div>
      </div>

      <p className="mt-4 text-sm text-muted-foreground">
        Keep practicing daily to reach your target
      </p>
    </section>
  )
}
