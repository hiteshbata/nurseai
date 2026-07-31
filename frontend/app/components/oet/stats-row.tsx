import { Layers, Gauge, Mic, CalendarDays } from "lucide-react"
import { ScorePill } from "./score-pill"

type StatCardProps = {
  label: string
  icon: React.ReactNode
  children: React.ReactNode
}

function StatCard({ label, icon, children }: StatCardProps) {
  return (
    <div className="rounded-2xl border border-gray-100 bg-card p-5 shadow-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary">
          {icon}
        </span>
        <span className="text-sm font-medium">{label}</span>
      </div>
      <div className="mt-4">{children}</div>
    </div>
  )
}

export function StatsRow({
  totalSubmissions,
  averageScore,
  speakingAvg,
  thisWeekCount,
}: {
  totalSubmissions: number
  averageScore: number
  speakingAvg: number
  thisWeekCount: number
}) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 motion-safe:animate-[message-in_0.4s_ease-out_both]">
      <StatCard
        label="Total Sessions"
        icon={<Layers className="h-4 w-4 text-primary" aria-hidden="true" />}
      >
        <p className="text-3xl font-bold tabular-nums text-primary">
          {totalSubmissions}
        </p>
      </StatCard>

      <StatCard
        label="Average Score"
        icon={<Gauge className="h-4 w-4 text-primary" aria-hidden="true" />}
      >
        <div className="flex items-baseline gap-1">
          <ScorePill score={averageScore} />
          <span className="text-sm text-muted-foreground">/6</span>
        </div>
      </StatCard>

      <StatCard
        label="Speaking"
        icon={<Mic className="h-4 w-4 text-primary" aria-hidden="true" />}
      >
        <div className="flex items-baseline gap-1">
          <ScorePill score={speakingAvg} />
          <span className="text-sm text-muted-foreground">/6</span>
        </div>
      </StatCard>

      <StatCard
        label="This Week"
        icon={<CalendarDays className="h-4 w-4 text-primary" aria-hidden="true" />}
      >
        <p className="text-3xl font-bold tabular-nums text-primary">
          {thisWeekCount}
          <span className="ml-1 text-sm font-medium text-muted-foreground">
            sessions
          </span>
        </p>
      </StatCard>
    </div>
  )
}
