'use client'

import Link from 'next/link'
import { Progress } from '@/components/ui/progress'

interface UpgradeBannerProps {
  sessionsUsed: number
  sessionsLimit: number
  sessionsRemaining: number
  plan: string
  isInstitutionMember?: boolean
}

const PCT_THRESHOLD = 80

export function UpgradeBanner({ sessionsUsed, sessionsLimit, sessionsRemaining, plan, isInstitutionMember }: UpgradeBannerProps) {
  // An institution member's B2C plan is usually still "free" (their real
  // access comes from the institution grant), so `plan === 'free'` alone
  // would misread them as a brand-new self-serve signup -- institution
  // entitlement takes precedence over that inference.
  if (plan !== 'free' || isInstitutionMember) return null

  const pct = sessionsLimit > 0 ? (sessionsUsed / sessionsLimit) * 100 : 0
  const isNearLimit = pct >= PCT_THRESHOLD
  const isNewUser = sessionsUsed === 0

  // The sidebar plan card already shows the running count, so this banner only
  // earns its space at the two moments it says something new: first visit, and
  // nearly out of sessions. Mid-month "4 of 10 used" was a duplicate ask.
  if (!isNewUser && !isNearLimit) return null

  const headline = isNewUser
    ? 'Start with your free sessions'
    : `Only ${sessionsRemaining} session${sessionsRemaining !== 1 ? 's' : ''} left this month`

  const subtitle = isNewUser
    ? `You have ${sessionsLimit} free sessions this month — full OET scoring, pronunciation analysis, and progress tracking included.`
    : 'Upgrade to Pro to keep practising without interruption.'

  const ctaLabel = isNewUser ? 'See Plans & Pricing' : 'Upgrade to Pro'

  return (
    <section className="w-full motion-safe:animate-[message-in_0.4s_ease-out_both]">
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
                  label="Sessions used this period"
                  className="h-2 bg-white/30 [&>div]:bg-white"
                />
              </div>
              <span className="text-xs font-semibold text-white/70 tabular-nums whitespace-nowrap">
                {Math.round(Math.min(pct, 100))}%
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
