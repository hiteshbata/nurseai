// Pure helpers for admin/institutions/[id]/page.tsx's Settings tab and
// status control (Phase 5.4 Step 3). Split out for the same reason
// institution/invites/helpers.ts is split out: page.tsx may only export the
// Next.js reserved names. Kept testable without a DOM (see helpers.test.mjs).
//
// Invitation create/list formatting reuses institution/invites/helpers.ts
// directly (deriveDisplayStatus, usesLabel, formatInviteDate, validateMaxUses,
// validateExpiration) rather than duplicating it here -- same invite shape,
// same rules.

// Mirrors admin_institutions.py's MODULE_VALUES (the institution_modules.module
// CHECK constraint) -- the single source of truth for which modules the
// Settings form can toggle.
export const MODULE_VALUES = ['speaking', 'reading', 'listening', 'writing', 'mock_tests'] as const

export interface FieldValidation {
  valid: boolean
  error?: string
}

export function validateRequired(raw: string, label: string): FieldValidation {
  return raw.trim() === '' ? { valid: false, error: `${label} is required.` } : { valid: true }
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function validateContactEmail(raw: string): FieldValidation {
  return EMAIL_RE.test(raw.trim()) ? { valid: true } : { valid: false, error: 'Enter a valid email address.' }
}

export interface QuotaValidation {
  valid: boolean
  error?: string
  value: number | null
}

// Unlike invites' validateMaxUses, blank is NOT valid here -- the Settings
// form always submits a concrete quota (spec: "quota must be > 0"), never an
// "unlimited" sentinel.
export function validateQuota(raw: string): QuotaValidation {
  const trimmed = raw.trim()
  if (!/^\d+$/.test(trimmed)) {
    return { valid: false, error: 'Quota must be a whole number of 1 or more.', value: null }
  }
  const n = Number(trimmed)
  if (n < 1) return { valid: false, error: 'Quota must be a whole number of 1 or more.', value: null }
  return { valid: true, value: n }
}

// Maps a PATCH/POST .../status failure to a user-facing message. 409 carries
// a plain-string `detail` from the backend (e.g. duplicate slug) that's safe
// to show verbatim; every other code gets a fixed message so no raw
// exception/detail payload ever reaches the page.
export function classifySaveError(httpStatus: number | undefined, detail?: unknown): string {
  if (httpStatus === 403) return "You don't have permission to modify this institution."
  if (httpStatus === 404) return 'Institution not found.'
  if (httpStatus === 409) return typeof detail === 'string' ? detail : 'That value conflicts with an existing institution.'
  if (httpStatus === 422) return 'Check the highlighted fields and try again.'
  return 'Something went wrong. Please try again.'
}

// Maps a POST .../staff failure to a user-facing message. 409's `detail` is
// the structured {error: "..."} shape from assign_institution_staff in
// admin_institutions.py (Phase 5.3b) -- every other code carries a plain
// string detail that's safe to show verbatim.
const STAFF_ASSIGN_409_MESSAGES: Record<string, string> = {
  revoked_membership: 'This email’s access was previously revoked. Contact support to restore it.',
  pending_membership: 'This email already has a pending invitation here.',
  already_teacher: 'This email is already a teacher at this institution.',
  already_student: 'This email is already a student at this institution.',
  already_staff_elsewhere: 'This person is already staff at another institution.',
  concurrent_account_creation: 'That account just started signing up elsewhere. Try again in a moment.',
}

export function classifyStaffAssignError(httpStatus: number | undefined, detail?: unknown): string {
  if (httpStatus === 403) return "You don't have permission to assign staff."
  if (httpStatus === 404) return 'Institution not found.'
  if (httpStatus === 409) {
    const key = detail && typeof detail === 'object' ? (detail as { error?: string }).error : undefined
    return (key && STAFF_ASSIGN_409_MESSAGES[key]) || 'That email conflicts with an existing assignment.'
  }
  if (httpStatus === 422) return 'Check the email address and try again.'
  if (typeof detail === 'string') return detail
  return 'Something went wrong. Please try again.'
}
