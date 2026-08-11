'use client'

import { useEffect, useRef } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'

export function ConsentBanner({
  onAcceptAll,
  onRejectAll,
  onManage,
}: {
  onAcceptAll: () => void
  onRejectAll: () => void
  onManage: () => void
}) {
  const regionRef = useRef<HTMLDivElement>(null)

  // Move focus to the banner once it appears, the same way a toast/alert
  // announces itself to screen-reader users -- without stealing focus on
  // every render (only once, on mount).
  useEffect(() => {
    regionRef.current?.focus()
  }, [])

  return (
    <div
      ref={regionRef}
      role="region"
      aria-label="Cookie consent"
      tabIndex={-1}
      className="fixed inset-x-0 bottom-0 z-[90] p-3 sm:p-4 motion-safe:animate-[panel-slide-in_0.4s_ease-out_both] focus:outline-none"
    >
      <div className="mx-auto max-w-4xl rounded-2xl border border-gray-200 bg-white p-5 shadow-premium-lg sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="max-w-2xl">
            <h2 className="font-display text-base font-semibold text-[#0F2356]">
              We use cookies and similar technologies
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-gray-600">
              We use necessary technologies to keep SpeakOET secure and working. With your
              permission, we also use analytics to understand how SpeakOET is used, and marketing
              technologies to measure and improve our outreach.{' '}
              <Link href="/cookies" className="underline underline-offset-2 hover:text-[#047857]">
                Learn more
              </Link>
              .
            </p>
          </div>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:shrink-0 sm:items-center">
            <Button variant="outline" size="sm" onClick={onManage}>
              Manage preferences
            </Button>
            <Button variant="ghost" size="sm" onClick={onRejectAll}>
              Reject non-essential
            </Button>
            <Button variant="default" size="sm" onClick={onAcceptAll}>
              Accept all
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
