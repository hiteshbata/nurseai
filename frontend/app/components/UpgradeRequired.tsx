'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Lock } from 'lucide-react'
import { useSessionUsage } from '@/components/AppShell'

interface UpgradeRequiredProps {
  title?: string
  message?: string
  ctaLabel?: string
  className?: string
}

// Full-page/section replacement for whenever an API call 403s with
// upgrade_required=true -- same visual language as StudyPlanCard's locked
// state, generalized so every module shows one consistent "blocked" screen
// instead of its own "failed to load" / empty state.
export function UpgradeRequired({
  title = 'Pro or Elite feature',
  message = 'This feature isn’t included in your current plan.',
  ctaLabel = 'Upgrade to Pro',
  className = '',
}: UpgradeRequiredProps) {
  // Every UpgradeRequired call site (18+ across the app) hardcodes a B2C
  // "Upgrade to Pro"-style prop set. Rather than threading an institution
  // flag through each one, read entitlement here -- the single place this
  // component renders -- so an institution student sees institution-aware
  // messaging with zero caller changes, and self-serve callers are untouched.
  const { usage } = useSessionUsage()
  const isInstitutionStudent = !!usage?.is_institution_member && !usage.institution_admin_role

  // Round-trips the user back to whatever they were trying to reach, query
  // string included (e.g. a specific reading test) instead of dropping them
  // on a generic post-upgrade screen -- read by /upgrade's `next` handling.
  // Computed client-side (not useSearchParams/usePathname) to match the
  // Suspense-boundary-avoidance convention used on the test pages.
  const [href, setHref] = useState('/upgrade')
  useEffect(() => {
    const next = window.location.pathname + window.location.search
    setHref(`/upgrade?next=${encodeURIComponent(next)}`)
  }, [])

  const displayTitle = isInstitutionStudent ? 'Not included in your institution access' : title
  const displayMessage = isInstitutionStudent
    ? "This feature isn’t included in your institution’s access."
    : message
  // Never offers B2C purchase -- routes to /upgrade, which shows an
  // institution student their plain access summary, not a pricing grid.
  const displayCtaLabel = isInstitutionStudent ? 'View your institution access' : ctaLabel

  return (
    <div className={`rounded-2xl bg-indigo-50 border border-indigo-100 p-6 ${className}`}>
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center shrink-0">
          <Lock className="w-4 h-4 text-indigo-600" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600 mb-1">
            {displayTitle}
          </p>
          <p className="text-sm text-muted-foreground mb-3">{displayMessage}</p>
          <Link
            href={href}
            className="inline-block bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm font-semibold hover:opacity-90 transition"
          >
            {displayCtaLabel} &rarr;
          </Link>
        </div>
      </div>
    </div>
  )
}
