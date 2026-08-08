import Link from "next/link"
import { Mic, BookOpen, Headphones, PenTool, TrendingUp, TrendingDown, Minus, type LucideIcon } from "lucide-react"
import { ScorePill } from "./score-pill"
import type { ModuleAverage, ModuleName } from "./types"

const MODULE_META: Record<ModuleName, { label: string; icon: LucideIcon; href: string }> = {
  speaking: { label: "Speaking", icon: Mic, href: "/practice/speaking" },
  reading: { label: "Reading", icon: BookOpen, href: "/practice/reading" },
  listening: { label: "Listening", icon: Headphones, href: "/practice/listening" },
  writing: { label: "Writing", icon: PenTool, href: "/practice/writing" },
}

const TREND_META: Record<ModuleAverage["trend"], { label: string; icon: LucideIcon; className: string }> = {
  improving: { label: "Improving", icon: TrendingUp, className: "text-emerald-600" },
  stable: { label: "Stable", icon: Minus, className: "text-muted-foreground" },
  declining: { label: "Declining", icon: TrendingDown, className: "text-red-600" },
  insufficient_data: { label: "Not enough data yet", icon: Minus, className: "text-muted-foreground" },
}

function formatLastActivity(iso: string | null): string {
  if (!iso) return "No sessions yet"
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24))
  if (days <= 0) return "Today"
  if (days === 1) return "Yesterday"
  return `${days} days ago`
}

export function ModuleProgressCard({ module, data }: { module: ModuleName; data: ModuleAverage }) {
  const meta = MODULE_META[module]
  const trend = TREND_META[data.trend]
  const Icon = meta.icon
  const TrendIcon = trend.icon

  if (data.submission_count === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border bg-card p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2 text-muted-foreground">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary">
            <Icon className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="text-sm font-semibold">{meta.label}</span>
        </div>
        <p className="text-sm text-muted-foreground">No sessions yet.</p>
        <Link href={meta.href} className="text-sm font-semibold text-primary hover:underline self-start">
          Start {meta.label} practice
        </Link>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-3 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-muted-foreground">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary">
            <Icon className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="text-sm font-semibold text-foreground">{meta.label}</span>
        </div>
        <div className="flex items-baseline gap-1">
          <ScorePill score={data.average} />
          <span className="text-xs text-muted-foreground">/6</span>
        </div>
      </div>

      <div className={`flex items-center gap-1.5 text-xs font-medium ${trend.className}`}>
        <TrendIcon className="h-3.5 w-3.5" aria-hidden="true" />
        {trend.label}
      </div>

      <div className="text-xs text-muted-foreground">{formatLastActivity(data.last_activity)}</div>

      <div className="mt-1 space-y-1 text-xs">
        {data.strongest_skill && (
          <p className="text-emerald-700">
            <span className="font-semibold">Strongest:</span> {data.strongest_skill.label} ({data.strongest_skill.band}/6)
          </p>
        )}
        {data.weakest_skill && (
          <p className="text-amber-700">
            <span className="font-semibold">Weakest:</span> {data.weakest_skill.label} ({data.weakest_skill.band}/6)
          </p>
        )}
        {!data.strongest_skill && !data.weakest_skill && (
          <p className="text-muted-foreground">A couple more sessions will surface skill-level detail here.</p>
        )}
      </div>

      <Link href={meta.href} className="mt-1 text-xs font-semibold text-primary hover:underline self-start">
        Practice {meta.label}
      </Link>
    </div>
  )
}

export { MODULE_META }
