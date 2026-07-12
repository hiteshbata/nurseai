'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Progress } from '@/components/ui/progress'
import { getPlans, type Plan } from '@/lib/api'

interface UpgradeBannerProps {
  sessionsUsed: number
  sessionsLimit: number
  sessionsRemaining: number
  plan: string
}

const PCT_THRESHOLD = 80

export function UpgradeBanner({ sessionsUsed, sessionsLimit, sessionsRemaining, plan }: UpgradeBannerProps) {
  const [proLimit, setProLimit] = useState<number | null>(null)

  useEffect(() => {
    getPlans().then((plans: Plan[]) => {
      const pro = plans.find((p: Plan) => p.id === 'pro')
      if (pro) setProLimit(pro.sessions_limit)
    }).catch(() => {})
  }, [])

  if (plan !== 'free') return null

  const pct = sessionsLimit > 0 ? (sessionsUsed / sessionsLimit) * 100 : 0
  const isNearLimit = pct >= PCT_THRESHOLD
  const isNewUser = sessionsUsed === 0

  const headline = isNewUser
    ? 'Start with your free sessions'
    : isNearLimit
      ? `Only ${sessionsRemaining} session${sessionsRemaining !== 1 ? 's' : ''} left this month`
      : `${sessionsUsed} of ${sessionsLimit} sessions used this month`

  const subtitle = isNewUser
    ? `You have ${sessionsLimit} free sessions this month — full OET scoring, pronunciation analysis, and progress tracking included.`
    : isNearLimit
      ? 'Upgrade to Pro to keep practising without interruption.'
      : `Get ${proLimit ?? 30} sessions per month with full OET scoring, pronunciation analysis, and progress tracking.`

  const ctaLabel = isNearLimit ? 'Upgrade to Pro' : 'See Plans & Pricing'

  return (
    <section className="mx-auto w-full max-w-5xl px-4 sm:px-6">
      <div className="rounded-2xl bg-[#0F2356] p-5 sm:p-6 shadow-md">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex-1 min-w-0">
            <h2 className="text-base sm:text-lg font-bold text-white leading-tight">
              {headline}
            </h2>
            <p className="text-sm text-white/80 mt-1 max-w-md">
              {subtitle}
            </p>

            <div className="mt-3 flex items-center gap-3">
              <div className="flex-1 max-w-[200px]">
                <Progress
                  value={Math.min(pct, 100)}
                  className="h-2 bg-white/30 [&>div]:bg-white"
                />
              </div>
              <span className="text-xs font-semibold text-white/70 tabular-nums whitespace-nowrap">
                {Math.round(pct)}%
              </span>
            </div>
          </div>

          <Link
            href="/upgrade"
            className="shrink-0 inline-flex items-center justify-center rounded-xl bg-white px-5 py-2.5 text-sm font-bold text-[#0F2356] hover:bg-white/90 shadow-sm hover:shadow-md transition-all active:scale-[0.97]"
          >
            {ctaLabel}
            <span className="ml-1.5" aria-hidden="true">&rarr;</span>
          </Link>
        </div>
      </div>
    </section>
  )
}
