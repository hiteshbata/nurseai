'use client'

import { useSupabaseSession, signIn, updatePassword, signOut, humanizeAuthError } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import api from '@/lib/api'
import { useSessionUsage } from '@/components/AppShell'
import toast from 'react-hot-toast'
import { Calendar, Mail, Shield, Pencil } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'

interface SessionUsage {
  sessions_used: number
  sessions_limit: number
  sessions_remaining: number
  plan: string
  auto_renew_enabled: boolean
  plan_expires_at: string | null
}

interface UserProfile {
  created_at: string | null
  plan: string | null
  onboarding_completed: boolean
  target_band: string | null
  exam_date: string | null
  days_per_week: number | null
}

interface Receipt {
  payment_id: string
  plan_name: string
  amount: number
  currency: string
  status: string
  created_at: string | null
}

const PLAN_LABELS: Record<string, string> = {
  free: 'Free Plan',
  basic: 'Basic Plan',
  pro: 'Pro Plan',
  elite: 'Elite Plan',
}

const TARGET_BANDS = ['A', 'B', 'C+', 'C', 'D']

const toDateInputValue = (iso: string | null): string => {
  if (!iso) return ''
  return iso.slice(0, 10)
}

const formatDisplayDate = (iso: string | null): string => {
  if (!iso) return 'Not set'
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
}

export default function ProfilePage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  // /sessions/usage is fetched once by AppShell (this page always renders
  // inside it) and read here instead of fetching it again -- that was a
  // confirmed duplicate request on every profile load. AppShell's own type
  // for this endpoint only declares the fields it displays; this page also
  // needs auto_renew_enabled/plan_expires_at, which the same response
  // already carries. cancelAutoRenew below still needs an instant local
  // flip after the POST succeeds, so that one field can be overridden
  // on top of the shared value without mutating AppShell's copy.
  const { usage: sharedUsage } = useSessionUsage()
  const [autoRenewOverride, setAutoRenewOverride] = useState<boolean | null>(null)
  const sessionUsage: SessionUsage | null = sharedUsage
    ? {
        ...(sharedUsage as unknown as SessionUsage),
        ...(autoRenewOverride !== null ? { auto_renew_enabled: autoRenewOverride } : {}),
      }
    : null
  const [receipts, setReceipts] = useState<Receipt[]>([])
  const [downloadingReceiptId, setDownloadingReceiptId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  const [editTargetBand, setEditTargetBand] = useState('')
  const [editExamDate, setEditExamDate] = useState('')
  const [editDaysPerWeek, setEditDaysPerWeek] = useState<number | null>(null)
  const [cancellingAutoRenew, setCancellingAutoRenew] = useState(false)

  const [changingPassword, setChangingPassword] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmNewPassword, setConfirmNewPassword] = useState('')
  const [savingPassword, setSavingPassword] = useState(false)
  const [deletingAccount, setDeletingAccount] = useState(false)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      fetchProfile()
    }
  }, [status])

  const fetchProfile = async () => {
    try {
      const [profileRes, receiptsRes] = await Promise.all([
        api.get('/onboarding/status'),
        api.get('/payments/receipts').catch(() => ({ data: [] })),
      ])
      if (profileRes.data?.user_id) {
        setProfile(profileRes.data)
      }
      setReceipts(receiptsRes.data || [])
    } catch (err) {
      console.error('Failed to load profile', err)
    } finally {
      setLoading(false)
    }
  }

  const downloadReceipt = async (paymentId: string) => {
    setDownloadingReceiptId(paymentId)
    try {
      const res = await api.get(`/payments/receipts/${paymentId}/pdf`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `receipt-${paymentId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error('Failed to download receipt')
    } finally {
      setDownloadingReceiptId(null)
    }
  }

  const cancelAutoRenew = async () => {
    if (!confirm('Turn off auto-renew? Your current plan stays active until it expires, then you’ll drop to Free.')) {
      return
    }
    setCancellingAutoRenew(true)
    try {
      await api.post('/payments/cancel-subscription')
      setAutoRenewOverride(false)
      toast.success('Auto-renew turned off')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to turn off auto-renew')
    } finally {
      setCancellingAutoRenew(false)
    }
  }

  const startChangingPassword = () => {
    setCurrentPassword('')
    setNewPassword('')
    setConfirmNewPassword('')
    setChangingPassword(true)
  }

  const cancelChangingPassword = () => {
    setChangingPassword(false)
  }

  const savePassword = async () => {
    if (newPassword.length < 8) {
      toast.error('New password must be at least 8 characters')
      return
    }
    if (newPassword !== confirmNewPassword) {
      toast.error('New passwords do not match')
      return
    }
    setSavingPassword(true)
    try {
      // Re-authenticate with the current password before changing it -- the
      // active session alone isn't proof the user at the keyboard knows the
      // old password (e.g. a left-open browser tab).
      await signIn(email, currentPassword)
      await updatePassword(newPassword)
      toast.success('Password updated')
      setChangingPassword(false)
    } catch (err: any) {
      toast.error(humanizeAuthError(err?.message))
    } finally {
      setSavingPassword(false)
    }
  }

  const deleteAccount = async () => {
    if (!confirm('Delete your account? This permanently removes your profile, practice plan, and session history. This cannot be undone.')) {
      return
    }
    if (!confirm('Are you absolutely sure? This is your last chance to cancel.')) {
      return
    }
    setDeletingAccount(true)
    try {
      await api.delete('/profile/account')
      await signOut()
      toast.success('Your account has been deleted')
      router.push('/')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to delete account')
      setDeletingAccount(false)
    }
  }

  const startEditing = () => {
    setEditTargetBand(profile?.target_band ?? '')
    setEditExamDate(toDateInputValue(profile?.exam_date))
    setEditDaysPerWeek(profile?.days_per_week ?? null)
    setEditing(true)
  }

  const cancelEditing = () => {
    setEditing(false)
  }

  const savePracticePlan = async () => {
    setSaving(true)
    try {
      const body: Record<string, any> = {}
      if (editTargetBand !== (profile?.target_band ?? '')) {
        body.target_band = editTargetBand || null
      }
      if (editExamDate !== (profile?.exam_date ?? '')) {
        body.exam_date = editExamDate || null
      }
      if (editDaysPerWeek !== (profile?.days_per_week ?? null)) {
        body.days_per_week = editDaysPerWeek
      }

      if (Object.keys(body).length === 0) {
        setEditing(false)
        return
      }

      const res = await api.put('/profile/practice-plan', body)
      if (res.data?.user_id) {
        setProfile(res.data)
      }
      toast.success('Practice plan updated')
      setEditing(false)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to update practice plan')
    } finally {
      setSaving(false)
    }
  }

  if (status === 'loading' || loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-gray-500 text-lg">Loading...</div>
      </div>
    )
  }

  const email = session?.user?.email ?? '—'
  const isEmailUser = session?.user?.app_metadata?.provider === 'email'
  const plan = sessionUsage?.plan ?? 'free'
  const planLabel = PLAN_LABELS[plan] ?? plan
  const memberSince = profile?.created_at
    ? new Date(profile.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
    : '—'

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold text-[#0F2356] mb-8">Settings</h1>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 mb-6">
          <h2 className="text-lg font-bold text-[#0F2356] mb-4">Account</h2>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Mail className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm text-gray-500">Email</p>
                <p className="text-sm font-semibold text-gray-800">{email}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Calendar className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm text-gray-500">Member since</p>
                <p className="text-sm font-semibold text-gray-800">{memberSince}</p>
              </div>
            </div>
          </div>

          {isEmailUser && (
            <div className="mt-5 pt-5 border-t border-gray-50">
              {changingPassword ? (
                <div className="space-y-4">
                  <div>
                    <label htmlFor="currentPassword" className="block text-sm font-semibold text-gray-700 mb-2">Current password</label>
                    <Input
                      id="currentPassword"
                      type="password"
                      autoComplete="current-password"
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                    />
                  </div>
                  <div>
                    <label htmlFor="newPassword" className="block text-sm font-semibold text-gray-700 mb-2">New password</label>
                    <Input
                      id="newPassword"
                      type="password"
                      autoComplete="new-password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                    />
                  </div>
                  <div>
                    <label htmlFor="confirmNewPassword" className="block text-sm font-semibold text-gray-700 mb-2">Confirm new password</label>
                    <Input
                      id="confirmNewPassword"
                      type="password"
                      autoComplete="new-password"
                      value={confirmNewPassword}
                      onChange={(e) => setConfirmNewPassword(e.target.value)}
                    />
                  </div>
                  <div className="flex gap-3 pt-1">
                    <button
                      onClick={savePassword}
                      disabled={savingPassword || !currentPassword || !newPassword}
                      className="flex-1 bg-[#0F2356] text-white font-semibold px-6 py-3 rounded-xl hover:bg-[#0F2356]/90 transition disabled:opacity-50"
                    >
                      {savingPassword ? 'Updating...' : 'Update password'}
                    </button>
                    <button
                      onClick={cancelChangingPassword}
                      disabled={savingPassword}
                      className="flex-1 bg-gray-100 text-gray-700 font-semibold px-6 py-3 rounded-xl hover:bg-gray-200 transition disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={startChangingPassword}
                  className="text-sm font-semibold text-[#0F2356] hover:text-[#0F2356]/70 transition-colors"
                >
                  Change password
                </button>
              )}
            </div>
          )}
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 mb-6">
          <h2 className="text-lg font-bold text-[#0F2356] mb-4">Billing</h2>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Shield className="w-5 h-5 text-gray-400" />
              <div>
                <p className="text-sm text-gray-500">Plan</p>
                <p className="text-sm font-semibold text-gray-800">
                  {planLabel}
                  {sessionUsage && (
                    <span className="text-muted-foreground font-normal">
                      {' '}— {sessionUsage.sessions_used} / {sessionUsage.sessions_limit} sessions used
                    </span>
                  )}
                </p>
              </div>
            </div>
            {plan !== 'free' && (
              <>
                <div className="flex items-center gap-3">
                  <Calendar className="w-5 h-5 text-gray-400" />
                  <div>
                    <p className="text-sm text-gray-500">
                      {sessionUsage?.auto_renew_enabled ? 'Next charge' : 'Active until'}
                    </p>
                    <p className="text-sm font-semibold text-gray-800">
                      {formatDisplayDate(sessionUsage?.plan_expires_at ?? null)}
                      {!sessionUsage?.auto_renew_enabled && sessionUsage?.plan_expires_at && (
                        <span className="text-muted-foreground font-normal"> — then drops to Free</span>
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-gray-50">
                  <div>
                    <p className="text-sm text-gray-500">Auto-renew</p>
                    <p className="text-sm font-semibold text-gray-800">
                      {sessionUsage?.auto_renew_enabled ? 'On — renews automatically each month' : 'Off'}
                    </p>
                  </div>
                  {sessionUsage?.auto_renew_enabled && (
                    <button
                      onClick={cancelAutoRenew}
                      disabled={cancellingAutoRenew}
                      className="text-sm font-semibold text-red-600 hover:text-red-700 transition-colors disabled:opacity-50"
                    >
                      {cancellingAutoRenew ? 'Turning off…' : 'Turn off'}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>

          {receipts.length > 0 && (
            <div className="mt-5 pt-5 border-t border-gray-50">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Payment history</h3>
              <ul className="space-y-2">
                {receipts.map((r) => (
                  <li key={r.payment_id} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-gray-600">
                      {formatDisplayDate(r.created_at)} — {r.plan_name} — {r.currency} {(r.amount / 100).toFixed(2)}
                    </span>
                    <button
                      onClick={() => downloadReceipt(r.payment_id)}
                      disabled={downloadingReceiptId === r.payment_id}
                      className="font-semibold text-[#0F2356] hover:text-[#0F2356]/70 transition-colors disabled:opacity-50 whitespace-nowrap"
                    >
                      {downloadingReceiptId === r.payment_id ? 'Downloading…' : 'Download receipt'}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div id="practice-plan" className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 scroll-mt-24">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-[#0F2356]">Practice Plan</h2>
            {!editing && (
              <button
                onClick={startEditing}
                className="flex items-center gap-1.5 text-sm font-semibold text-[#0F2356] hover:text-[#0F2356]/70 transition-colors"
              >
                <Pencil className="w-4 h-4" />
                Edit
              </button>
            )}
          </div>

          {editing ? (
            <div className="space-y-5">
              <div>
                <label htmlFor="editTargetBand" className="block text-sm font-semibold text-gray-700 mb-2">
                  Target Band
                </label>
                <Select
                  id="editTargetBand"
                  value={editTargetBand}
                  onChange={(e) => setEditTargetBand(e.target.value)}
                >
                  <option value="">Select target band...</option>
                  {TARGET_BANDS.map((b) => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </Select>
              </div>

              <div>
                <label htmlFor="editExamDate" className="block text-sm font-semibold text-gray-700 mb-2">
                  Exam Date <span className="text-muted-foreground font-normal">(optional)</span>
                </label>
                <Input
                  id="editExamDate"
                  type="date"
                  value={editExamDate}
                  onChange={(e) => setEditExamDate(e.target.value)}
                />
                {editExamDate && (
                  <button
                    onClick={() => setEditExamDate('')}
                    className="text-xs text-gray-500 hover:text-gray-700 mt-1 underline"
                  >
                    Clear date
                  </button>
                )}
              </div>

              <div>
                <span id="editDaysPerWeekLabel" className="block text-sm font-semibold text-gray-700 mb-2">
                  Practice days per week
                </span>
                <div role="group" aria-labelledby="editDaysPerWeekLabel" className="flex gap-2">
                  {[2, 3, 4, 5, 6, 7].map((d) => (
                    <button
                      key={d}
                      onClick={() => setEditDaysPerWeek(d)}
                      aria-pressed={editDaysPerWeek === d}
                      className={`flex-1 py-3 rounded-xl font-semibold border-2 transition ${
                        editDaysPerWeek === d
                          ? 'border-blue-600 bg-blue-50 text-blue-700'
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={savePracticePlan}
                  disabled={saving}
                  className="flex-1 bg-[#0F2356] text-white font-semibold px-6 py-3 rounded-xl hover:bg-[#0F2356]/90 transition disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button
                  onClick={cancelEditing}
                  disabled={saving}
                  className="flex-1 bg-gray-100 text-gray-700 font-semibold px-6 py-3 rounded-xl hover:bg-gray-200 transition disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between py-2 border-b border-gray-50">
                <span className="text-sm text-gray-500">Target Band</span>
                <span className="text-sm font-semibold text-gray-800">{profile?.target_band ?? 'Not set'}</span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-gray-50">
                <span className="text-sm text-gray-500">Exam Date</span>
                <span className="text-sm font-semibold text-gray-800">
                  {formatDisplayDate(profile?.exam_date)}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-gray-50">
                <span className="text-sm text-gray-500">Practice days per week</span>
                <span className="text-sm font-semibold text-gray-800">{profile?.days_per_week ?? 'Not set'}</span>
              </div>
            </div>
          )}
        </div>

        <div className="bg-white rounded-2xl border border-red-100 shadow-sm p-6 mt-6">
          <h2 className="text-lg font-bold text-red-600 mb-1">Danger Zone</h2>
          <p className="text-sm text-gray-500 mb-4">
            Permanently delete your account, profile, practice plan, and session history. This cannot be undone.
          </p>
          <button
            onClick={deleteAccount}
            disabled={deletingAccount}
            className="text-sm font-semibold text-red-600 hover:text-red-700 transition-colors disabled:opacity-50"
          >
            {deletingAccount ? 'Deleting account…' : 'Delete my account'}
          </button>
        </div>
      </div>
    </div>
  )
}
