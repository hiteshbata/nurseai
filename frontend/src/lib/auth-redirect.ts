// Only allow same-origin relative paths (e.g. "/practice/speaking") as a
// redirect target -- never an absolute URL or protocol-relative "//host"
// path, which would let a crafted returnTo param send the user off-site
// after auth. Shared by login, register, and the OAuth/email-confirm
// callback so the check can't drift between call sites.
export function getSafeReturnTo(): string | null {
  if (typeof window === 'undefined') return null
  const returnTo = new URLSearchParams(window.location.search).get('returnTo')
  if (!returnTo || !returnTo.startsWith('/') || returnTo.startsWith('//')) return null
  return returnTo
}
