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
