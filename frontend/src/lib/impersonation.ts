import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

const STORAGE_KEY = 'speakoet_impersonation'
export const IMPERSONATION_EVENT = 'speakoet:impersonation-changed'

interface ImpersonationRecord {
  adminAccessToken: string
  targetEmail: string
  targetName: string
  logId: string
}

export function getImpersonationState(): ImpersonationRecord | null {
  if (typeof window === 'undefined') return null
  const raw = sessionStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

// Swaps the browser's active Supabase session to the target user's, after
// stashing the admin's own tokens so exitImpersonation() can restore them.
// The caller (admin UI) is responsible for navigating away afterward --
// staying on an /admin/* page as a non-admin session just bounces the
// AdminShell guard back out with a confusing "Admin access required" toast.
export async function beginImpersonation(session: {
  access_token: string
  refresh_token: string
  target_email: string
  target_name: string
  log_id: string
}) {
  const { data: { session: adminSession } } = await supabase.auth.getSession()
  if (!adminSession) throw new Error('No active admin session to preserve')

  // Refresh_token is never persisted to sessionStorage (XSS-readable) --
  // only the short-lived access_token is stashed. If it's close to expiry,
  // refresh now so it stays valid for the duration of the impersonation.
  let adminAccessToken = adminSession.access_token
  const expiresInSec = (adminSession.expires_at ?? 0) - Math.floor(Date.now() / 1000)
  if (expiresInSec < 300) {
    const { data, error } = await supabase.auth.refreshSession()
    if (error || !data.session) throw new Error('Failed to refresh admin session before impersonation')
    adminAccessToken = data.session.access_token
  }

  const record: ImpersonationRecord = {
    adminAccessToken,
    targetEmail: session.target_email,
    targetName: session.target_name,
    logId: session.log_id,
  }
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(record))

  await supabase.auth.setSession({
    access_token: session.access_token,
    refresh_token: session.refresh_token,
  })
  window.dispatchEvent(new Event(IMPERSONATION_EVENT))
}

// Restores the admin's own session and closes out the impersonation_log
// entry. Caller navigates away afterward (back to the user's admin profile).
export async function endImpersonation() {
  const record = getImpersonationState()
  if (!record) return

  // No refresh_token was stashed, so restore is only possible while the
  // stashed access_token is still valid (it was refreshed to be fresh at
  // beginImpersonation). If it's since expired, this fails and the admin
  // must sign in again -- an intentional tradeoff for not persisting a
  // long-lived refresh token in sessionStorage.
  //
  // gotrue-js's setSession() throws AuthSessionMissingError whenever
  // refresh_token is falsy -- checked via `!refresh_token`, never validated
  // -- so '' always fails here, even with a perfectly valid access_token.
  // It only reads refresh_token for a real network call when access_token
  // has already expired; while still valid it just verifies access_token
  // via getUser() and stores whatever string is passed. A non-empty
  // placeholder satisfies the truthiness check and goes unused unless the
  // token has expired, at which point the refresh attempt correctly fails.
  const { error: restoreError } = await supabase.auth.setSession({
    access_token: record.adminAccessToken,
    refresh_token: '__INVALID_REFRESH_TOKEN_IMPERSONATION_RESTORE__',
  })
  if (restoreError) {
    console.error('[impersonation] admin session expired, sign-in required:', restoreError)
  }

  try {
    await api.post(`/admin/impersonation/${record.logId}/end`)
  } catch (e) {
    console.error('[impersonation] failed to close log entry (non-fatal):', e)
  }

  sessionStorage.removeItem(STORAGE_KEY)
  window.dispatchEvent(new Event(IMPERSONATION_EVENT))
}
