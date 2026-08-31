// Pure param-checks for reset-password/page.tsx, split out so they're
// testable without mounting the React page (see helpers.test.mjs).

export function hasUrlError(search: URLSearchParams, hash: URLSearchParams): boolean {
  return Boolean(search.get('error') || hash.get('error'))
}

// Covers the PKCE flow (?code=...), the implicit flow
// (#access_token=...&type=recovery), and an institution invite forwarded
// here by /auth/confirm as ?type=invite once its SSR session cookie is
// set. This page is only ever the redirectTo target for password recovery
// or invite acceptance, so any of these params landing here can only have
// come from a real recovery/invite email link. The caller still gates
// access on an actual session (getSession) -- the param alone never grants
// 'valid'.
export function hasRecoveryParams(search: URLSearchParams, hash: URLSearchParams): boolean {
  return Boolean(
    search.get('code') || search.get('type') === 'recovery' || search.get('type') === 'invite' ||
    hash.get('access_token') || hash.get('type') === 'recovery'
  )
}
