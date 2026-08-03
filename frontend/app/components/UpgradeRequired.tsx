'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Lock } from 'lucide-react'

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

  return (
    <div className={`rounded-2xl bg-indigo-50 border border-indigo-100 p-6 ${className}`}>
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center shrink-0">
          <Lock className="w-4 h-4 text-indigo-600" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600 mb-1">
            {title}
          </p>
          <p className="text-sm text-muted-foreground mb-3">{message}</p>
          <Link
            href={href}
            className="inline-block bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm font-semibold hover:opacity-90 transition"
          >
            {ctaLabel} &rarr;
          </Link>
        </div>
      </div>
    </div>
  )
}
