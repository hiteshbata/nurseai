import { supabase } from '@/lib/supabase'
import api from '@/lib/api'

const STORAGE_KEY = 'speakoet_impersonation'
export const IMPERSONATION_EVENT = 'speakoet:impersonation-changed'

interface ImpersonationRecord {
  adminAccessToken: string
  adminRefreshToken: string
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

  const record: ImpersonationRecord = {
    adminAccessToken: adminSession.access_token,
    adminRefreshToken: adminSession.refresh_token,
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

  await supabase.auth.setSession({
    access_token: record.adminAccessToken,
    refresh_token: record.adminRefreshToken,
  })

  try {
    await api.post(`/admin/impersonation/${record.logId}/end`)
  } catch (e) {
    console.error('[impersonation] failed to close log entry (non-fatal):', e)
  }

  sessionStorage.removeItem(STORAGE_KEY)
  window.dispatchEvent(new Event(IMPERSONATION_EVENT))
}
