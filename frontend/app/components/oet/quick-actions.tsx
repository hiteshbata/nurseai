'use client'

import { Mic, ArrowRight, Clock } from "lucide-react"
import { useRouter } from "next/navigation"

type QuickActionProps = {
  title: string
  cta: string
  icon: React.ReactNode
  variant: "navy" | "emerald" | "disabled"
  onClick?: () => void
}

function QuickActionCard({ title, cta, icon, variant, onClick }: QuickActionProps) {
  const isDisabled = variant === "disabled"
  const bgClass = isDisabled
    ? "bg-gray-100 text-gray-400 cursor-not-allowed"
    : variant === "navy"
      ? "bg-primary text-primary-foreground cursor-pointer hover:-translate-y-0.5"
      : "bg-accent text-accent-foreground cursor-pointer hover:-translate-y-0.5"

  return (
    <button
      onClick={isDisabled ? undefined : onClick}
      className={`group flex flex-col gap-8 rounded-2xl p-6 text-left shadow-sm transition-transform ${bgClass}`}
    >
      <span className={`flex h-12 w-12 items-center justify-center rounded-xl ${isDisabled ? "bg-gray-200" : "bg-white/15"}`}>
        {isDisabled ? <Clock className="h-6 w-6" aria-hidden="true" /> : icon}
      </span>
      <div>
        <p className="text-lg font-bold">{title}</p>
        <span className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-white/80">
          {isDisabled ? "Coming Soon" : cta}
          {!isDisabled && (
            <ArrowRight
              className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          )}
        </span>
      </div>
    </button>
  )
}

export function QuickActions() {
  const router = useRouter()

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
      <QuickActionCard
        title="Practice Speaking"
        cta="Start roleplay"
        variant="navy"
        icon={<Mic className="h-6 w-6" aria-hidden="true" />}
        onClick={() => router.push("/practice/speaking")}
      />
    </div>
  )
}
