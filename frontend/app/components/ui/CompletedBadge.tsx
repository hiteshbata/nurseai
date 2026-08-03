import { CheckCircle2 } from 'lucide-react'

export function CompletedBadge() {
  return (
    <span className="absolute top-4 right-4 flex items-center gap-1 rounded-full bg-emerald-500 text-white text-[10px] font-semibold px-2.5 py-1">
      <CheckCircle2 className="size-3" />
      Completed
    </span>
  )
}
