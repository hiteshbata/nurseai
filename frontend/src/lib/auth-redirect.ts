// Only allow same-origin relative paths (e.g. "/practice/speaking") as a
// redirect target -- never an absolute URL or protocol-relative "//host"
// path, which would let a crafted returnTo param send the user off-site
// after auth. Shared by login, register, and the OAuth/email-confirm
// callback so the check can't drift between call sites.
export function getSafeReturnTo(): string | null {
  if (typeof window === 'undefined') return null
  return sanitizeNext(new URLSearchParams(window.location.search).get('returnTo'), window.location.origin)
}

// Server-side counterpart used by the /auth/confirm route handler, where
// there's no `window` to read from. `next` there comes from GoTrue's
// `.RedirectTo` template variable -- attacker-controlled the moment someone
// edits the confirmation link -- so it's checked against the same rule:
// relative-and-not-protocol-relative, or an absolute URL that resolves to
// this same origin. Anything else (a bare relative path elsewhere, a
// different host) is rejected.
export function sanitizeNext(next: string | null, origin: string): string | null {
  if (!next) return null
  if (next.startsWith('/') && !next.startsWith('//')) return next
  try {
    const url = new URL(next)
    if (url.origin === origin) return url.pathname + url.search + url.hash
  } catch {
    // not a valid absolute URL either -- fall through to reject
  }
  return null
}

// Displayed on /auth/verify so the user can confirm they're checking the
// right inbox without the page leaking the full address to anyone glancing
// at a shared screen. Keeps the first character and domain, stars the rest
// of the local part.
export function maskEmail(email: string): string {
  const [local, domain] = email.split('@')
  if (!local || !domain) return email
  return `${local[0]}${'*'.repeat(Math.max(local.length - 1, 3))}@${domain}`
}

// Picks the redirect target for /auth/confirm once `next` has been
// sanitized. An invite confirmation has no password yet, so it must ALWAYS
// land on the password-setting page -- never /auth/callback, which assumes
// the account is already usable. `next` is ignored entirely for type=invite:
// the backend's invite_user_by_email call sets redirect_to=/auth/callback
// (for the unrelated case of an already-confirmed user re-clicking an old
// invite), and if a Supabase Dashboard email template ever surfaces that as
// `next` on the link, honoring it here would let a brand-new invited user
// skip password setup entirely. Every other type keeps the explicit-next
// override.
export function resolveConfirmNext(
  type: string | null,
  rawNext: string | null,
  origin: string
): string {
  if (type === 'invite') return '/auth/reset-password?type=invite'
  return sanitizeNext(rawNext, origin) || '/auth/callback'
}
