import { cn } from "@/lib/utils"

function pillStyles(score: number) {
  if (score > 4) {
    return "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
  }
  if (score >= 3) {
    return "bg-amber-50 text-amber-700 ring-amber-600/20"
  }
  return "bg-red-50 text-red-700 ring-red-600/20"
}

export function ScorePill({
  score,
  className,
}: {
  score: number
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-sm font-semibold ring-1 ring-inset tabular-nums",
        pillStyles(score),
        className,
      )}
    >
      {score.toFixed(1)}
    </span>
  )
}

export function BandBadge({ band }: { band: string }) {
  return (
    <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-secondary text-sm font-bold text-primary">
      {band}
    </span>
  )
}
