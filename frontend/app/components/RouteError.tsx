'use client'

import { useEffect } from 'react'
import * as Sentry from '@sentry/nextjs'

// Shared body for every route segment's error.tsx. Next.js requires each
// error.tsx to be its own file/default export, so this just holds the one
// bit of actual logic (report + recovery UI) they all share.
export function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    Sentry.captureException(error)
  }, [error])

  return (
    <div className="flex flex-col items-center justify-center gap-3 px-4 py-24 text-center">
      <p className="text-base font-semibold text-foreground">Something went wrong.</p>
      <p className="text-sm text-muted-foreground">
        This page hit an error. You can try again, or head back to the dashboard.
      </p>
      <div className="mt-2 flex gap-3">
        <button
          onClick={reset}
          className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
        >
          Try again
        </button>
        <a
          href="/dashboard"
          className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-foreground hover:bg-muted"
        >
          Go to dashboard
        </a>
      </div>
    </div>
  )
}
