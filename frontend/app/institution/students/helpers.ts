// Pure helpers for institution/students/page.tsx, split out of the page
// module because Next.js App Router only allows page.tsx to export a
// specific reserved set of names (default, metadata, generateStaticParams,
// ...) -- any other named export fails the generated route-type check at
// build time. Kept testable without a DOM (see page.test.mjs).

// Same 403/409/other classification as /institution/page.tsx.
export function classifyLoadError(httpStatus: number | undefined): 'denied' | 'multiple' | 'error' {
  if (httpStatus === 401 || httpStatus === 403) return 'denied'
  if (httpStatus === 409) return 'multiple'
  return 'error'
}

export function formatJoined(joinedAt: string | null): string {
  if (!joinedAt) return '—'
  const d = new Date(joinedAt)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function scoreLabel(score: number | null): string {
  return score === null || score === undefined ? '—' : String(score)
}

// Compact desktop column: "12 / 8 remaining", or just "12 used" when the
// institution has no per-student speaking cap to compare against (unlimited
// quota or speaking module disabled -- backend sends sessions_remaining: null
// for both, spec Sections 5/6).
export function sessionsLabel(used: number, remaining: number | null): string {
  return remaining === null ? `${used} used` : `${used} / ${remaining} remaining`
}

export function mobileSessionsLabel(used: number, remaining: number | null): string {
  return remaining === null ? `${used} used · — left` : `${used} used · ${remaining} left`
}
