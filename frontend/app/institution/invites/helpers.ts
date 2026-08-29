// Pure helpers for institution/invites/page.tsx, split out of the page
// module because Next.js App Router only allows page.tsx to export a
// specific reserved set of names (default, metadata, generateStaticParams,
// ...) -- any other named export fails the generated route-type check at
// build time. Kept testable without a DOM (see page.test.mjs).

export type DisplayStatus = 'active' | 'revoked' | 'expired'

// Same 401/403 -> denied, 409 -> multiple, else -> error classification as
// /institution/students/page.tsx.
export function classifyLoadError(httpStatus: number | undefined): 'denied' | 'multiple' | 'error' {
  if (httpStatus === 401 || httpStatus === 403) return 'denied'
  if (httpStatus === 409) return 'multiple'
  return 'error'
}

// Backend `status` stays "active" past expires_at (it doesn't get flipped
// server-side) -- this is a display-only projection, never written back.
export function deriveDisplayStatus(
  status: string,
  expiresAt: string | null,
  now: Date = new Date(),
): DisplayStatus {
  if (status === 'revoked') return 'revoked'
  if (expiresAt) {
    const exp = new Date(expiresAt)
    if (!Number.isNaN(exp.getTime()) && exp.getTime() <= now.getTime()) return 'expired'
  }
  return 'active'
}

export function usesLabel(useCount: number, remainingUses: number | null): string {
  return remainingUses === null ? `${useCount} used · Unlimited` : `${useCount} used · ${remainingUses} remaining`
}

export function formatInviteDate(iso: string | null): string {
  if (!iso) return 'No expiration'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'No expiration'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export interface MaxUsesValidation {
  valid: boolean
  error?: string
  value: number | null
}

export function validateMaxUses(raw: string): MaxUsesValidation {
  const trimmed = raw.trim()
  if (trimmed === '') return { valid: true, value: null }
  if (!/^\d+$/.test(trimmed)) {
    return { valid: false, error: 'Must be blank or a whole number of 1 or more.', value: null }
  }
  const n = Number(trimmed)
  if (n < 1) return { valid: false, error: 'Must be blank or a whole number of 1 or more.', value: null }
  return { valid: true, value: n }
}

export interface ExpirationValidation {
  valid: boolean
  error?: string
  iso: string | null
}

// `raw` is a <input type="datetime-local"> value ("YYYY-MM-DDTHH:mm"), which
// carries no timezone. `new Date(raw)` parses that exact form as browser-local
// wall-clock time (per the ECMA-262 Date Time String Format), so
// `.toISOString()` below correctly converts it to UTC. Do NOT append "Z" to
// `raw` before parsing -- that would misinterpret the local time the admin
// typed as if it were already UTC, silently shifting the expiration by the
// browser's UTC offset.
export function validateExpiration(raw: string, now: Date = new Date()): ExpirationValidation {
  const trimmed = raw.trim()
  if (trimmed === '') return { valid: true, iso: null }
  const d = new Date(trimmed)
  if (Number.isNaN(d.getTime())) return { valid: false, error: 'Enter a valid date and time.', iso: null }
  if (d.getTime() <= now.getTime()) return { valid: false, error: 'Expiration must be in the future.', iso: null }
  return { valid: true, iso: d.toISOString() }
}
