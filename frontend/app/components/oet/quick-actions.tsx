'use client'

import { Mic, PenLine, ArrowRight } from "lucide-react"
import { useRouter } from "next/navigation"

const WRITING_PLANS = ["pro", "elite"]

type QuickActionProps = {
  title: string
  cta: string
  icon: React.ReactNode
  badge?: string
  onClick?: () => void
}

function QuickActionCard({ title, cta, icon, badge, onClick }: QuickActionProps) {
  return (
    <button
      onClick={onClick}
      className="group flex flex-col gap-8 rounded-2xl p-6 text-left shadow-sm transition-transform bg-primary text-primary-foreground cursor-pointer hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98]"
    >
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/15">
        {icon}
      </span>
      <div>
        <p className="flex items-center gap-2 text-lg font-bold">
          {title}
          {badge && (
            <span className="rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide">
              {badge}
            </span>
          )}
        </p>
        <span className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-white/80">
          {cta}
          <ArrowRight
            className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </span>
      </div>
    </button>
  )
}

export function QuickActions({ plan }: { plan?: string | null }) {
  const router = useRouter()
  const hasWritingAccess = !plan || WRITING_PLANS.includes(plan)

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
      <QuickActionCard
        title="Practice Speaking"
        cta="Start roleplay"
        icon={<Mic className="h-6 w-6" aria-hidden="true" />}
        onClick={() => router.push("/practice/speaking")}
      />
      <QuickActionCard
        title="Practice Writing"
        cta="Start writing task"
        icon={<PenLine className="h-6 w-6" aria-hidden="true" />}
        badge={hasWritingAccess ? undefined : "Pro"}
        onClick={() => router.push("/practice/writing")}
      />
    </div>
  )
}
