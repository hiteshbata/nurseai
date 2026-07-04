import { Calendar, TrendingUp, Trophy } from "lucide-react"

export function HeroCards({
  examDaysLeft,
  currentGrade,
  targetBand,
}: {
  examDaysLeft: number | null
  currentGrade: string
  targetBand: string
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
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
        <p className="mt-6 text-5xl font-bold tabular-nums">
          {examDaysLeft ?? "—"}
        </p>
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
        <p className="mt-6 text-5xl font-bold text-accent">{currentGrade}</p>
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
