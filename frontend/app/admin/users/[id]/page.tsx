'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import api from '@/lib/api'
import { beginImpersonation } from '@/lib/impersonation'

interface Submission {
  id: number
  scenario_id: number | null
  module: string
  score: number | null
  created_at: string
}

interface ModerationStatus {
  status: 'active' | 'suspended' | 'banned'
  reason?: string
  until?: string
  since?: string
}

interface UserDetail {
  user_id: string
  email: string
  name: string
  created_at: string
  last_sign_in_at: string | null
  role: string
  profile: Record<string, any>
  recent_submissions: Submission[]
  moderation: ModerationStatus
}

interface Transcript {
  id: number
  session_usage_id: number
  scenario_id: number | null
  transcript: { role: string; text: string }[]
  created_at: string
}

interface Payment {
  id: string
  order_id: string | null
  payment_id: string | null
  plan_id: string
  amount: number
  currency: string
  status: string
  created_at: string
}

export default function AdminUserDetailPage() {
  const router = useRouter()
  const params = useParams()
  const userId = params.id as string

  const [user, setUser] = useState<UserDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [savingRole, setSavingRole] = useState(false)
  const [impersonating, setImpersonating] = useState(false)
  const [showPlanForm, setShowPlanForm] = useState(false)
  const [planChoice, setPlanChoice] = useState('pro')
  const [periodDays, setPeriodDays] = useState(30)
  const [savingPlan, setSavingPlan] = useState(false)
  const [showBonusForm, setShowBonusForm] = useState(false)
  const [bonusAmount, setBonusAmount] = useState(1)
  const [bonusReason, setBonusReason] = useState('')
  const [savingBonus, setSavingBonus] = useState(false)
  const [moderating, setModerating] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [payments, setPayments] = useState<Payment[]>([])
  const [cancelling, setCancelling] = useState(false)
  const [transcripts, setTranscripts] = useState<Transcript[]>([])
  const [openTranscriptId, setOpenTranscriptId] = useState<number | null>(null)

  useEffect(() => {
    fetchUser()
    fetchPayments()
    fetchTranscripts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId])

  const fetchUser = async () => {
    setLoading(true)
    try {
      const response = await api.get(`/admin/users/${userId}`)
      setUser(response.data)
    } catch (error: any) {
      if (error.response?.status === 403) {
        alert('Admin access required')
        router.push('/')
      } else if (error.response?.status === 404) {
        alert('User not found')
        router.push('/admin/users')
      }
      console.error('Failed to fetch user:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchPayments = async () => {
    try {
      const response = await api.get(`/admin/users/${userId}/payments`)
      setPayments(response.data.payments)
    } catch (error) {
      console.error('Failed to fetch payment history:', error)
    }
  }

  const fetchTranscripts = async () => {
    try {
      const response = await api.get(`/admin/users/${userId}/transcripts`)
      setTranscripts(response.data.transcripts)
    } catch (error) {
      console.error('Failed to fetch transcripts:', error)
    }
  }

  const handleCancelSubscription = async () => {
    if (!user) return
    if (!confirm(`Turn off auto-renew for ${user.name || user.email}? Their plan stays active until it expires.`)) return

    setCancelling(true)
    try {
      await api.post(`/admin/users/${user.user_id}/subscription/cancel`)
      await fetchUser()
    } catch (error: any) {
      console.error('Failed to cancel subscription:', error)
      alert(error.response?.data?.detail || 'Failed to cancel subscription.')
    } finally {
      setCancelling(false)
    }
  }

  const toggleRole = async () => {
    if (!user) return
    const newRole = user.role === 'admin' ? 'user' : 'admin'
    if (!confirm(`Change this user's role to "${newRole}"?`)) return
    setSavingRole(true)
    try {
      await api.post('/admin/users/role', { user_id: user.user_id, role: newRole })
      setUser({ ...user, role: newRole })
    } catch (error) {
      console.error('Failed to update role:', error)
      alert('Failed to update role.')
    } finally {
      setSavingRole(false)
    }
  }

  const handleChangePlan = async () => {
    if (!user) return
    const label = planChoice === 'free' ? 'Free' : `${planChoice} for ${periodDays} days`
    if (!confirm(`Set this user's plan to ${label}?`)) return

    setSavingPlan(true)
    try {
      await api.post(`/admin/users/${user.user_id}/plan`, {
        plan: planChoice,
        period_days: planChoice === 'free' ? undefined : periodDays,
      })
      await fetchUser()
      setShowPlanForm(false)
    } catch (error: any) {
      console.error('Failed to change plan:', error)
      alert(error.response?.data?.detail || 'Failed to change plan.')
    } finally {
      setSavingPlan(false)
    }
  }

  const handleGrantBonus = async () => {
    if (!user) return
    if (!bonusReason.trim()) {
      alert('A reason is required.')
      return
    }
    if (!confirm(`Grant ${bonusAmount} bonus session(s) to ${user.name || user.email}?`)) return

    setSavingBonus(true)
    try {
      await api.post(`/admin/users/${user.user_id}/bonus-sessions`, {
        amount: bonusAmount,
        reason: bonusReason,
      })
      await fetchUser()
      setShowBonusForm(false)
      setBonusReason('')
    } catch (error: any) {
      console.error('Failed to grant bonus sessions:', error)
      alert(error.response?.data?.detail || 'Failed to grant bonus sessions.')
    } finally {
      setSavingBonus(false)
    }
  }

  const handleModerate = async (action: 'suspend' | 'ban' | 'reinstate') => {
    if (!user) return
    const verb = action === 'suspend' ? 'suspend (30 days)' : action === 'ban' ? 'ban' : 'reinstate'
    const reason = window.prompt(`Reason to ${verb} ${user.name || user.email}:`)
    if (reason === null) return
    if (!reason.trim()) {
      alert('A reason is required.')
      return
    }

    setModerating(true)
    try {
      await api.post(`/admin/users/${user.user_id}/moderate`, { action, reason })
      await fetchUser()
    } catch (error: any) {
      console.error('Failed to moderate user:', error)
      alert(error.response?.data?.detail || 'Failed to update user.')
    } finally {
      setModerating(false)
    }
  }

  const handleDelete = async () => {
    if (!user) return
    const reason = window.prompt(`Reason to permanently delete ${user.name || user.email}:`)
    if (reason === null) return
    if (!reason.trim()) {
      alert('A reason is required.')
      return
    }
    if (!confirm(`This permanently deletes ${user.email} and all their data. This cannot be undone. Continue?`)) return

    setDeleting(true)
    try {
      await api.post(`/admin/users/${user.user_id}/delete`, { reason })
      alert('User deleted.')
      router.push('/admin/users')
    } catch (error: any) {
      console.error('Failed to delete user:', error)
      alert(error.response?.data?.detail || 'Failed to delete user.')
      setDeleting(false)
    }
  }

  const handleImpersonate = async () => {
    if (!user) return
    if (!confirm(
      `Log in as ${user.name || user.email}?\n\nYou'll have full access as this user until you exit. This is logged.`
    )) return

    setImpersonating(true)
    try {
      const response = await api.post(`/admin/users/${user.user_id}/impersonate`)
      await beginImpersonation(response.data)
      router.push('/dashboard')
    } catch (error: any) {
      console.error('Failed to start impersonation:', error)
      alert(error.response?.data?.detail || 'Failed to start impersonation.')
    } finally {
      setImpersonating(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading user...</div>
      </div>
    )
  }

  if (!user) return null

  const p = user.profile

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-5xl mx-auto">
        <button
          onClick={() => router.push('/admin/users')}
          className="text-sm text-gray-500 hover:text-gray-700 mb-4"
        >
          ← Back to Users
        </button>

        {/* Identity header */}
        <div className="bg-white rounded-lg shadow p-6 mb-6 flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold">{user.name || '(no name)'}</h1>
            <p className="text-gray-500">{user.email}</p>
            <p className="text-xs text-muted-foreground font-mono mt-1">{user.user_id}</p>
            <div className="flex gap-4 mt-3 text-sm text-gray-500">
              <span>Joined {new Date(user.created_at).toLocaleDateString()}</span>
              <span>
                Last sign-in {user.last_sign_in_at ? new Date(user.last_sign_in_at).toLocaleDateString() : 'never'}
              </span>
            </div>
          </div>
          <div className="text-right">
            <span className={`inline-block px-3 py-1 rounded text-xs font-semibold ${
              user.role === 'admin' ? 'bg-purple-100 text-purple-800' : 'bg-gray-100 text-gray-600'
            }`}>
              {user.role}
            </span>
            <button
              onClick={toggleRole}
              disabled={savingRole}
              className="block mt-2 text-sm text-blue-600 hover:underline disabled:opacity-50"
            >
              {savingRole ? 'Saving...' : user.role === 'admin' ? 'Revoke admin' : 'Make admin'}
            </button>
            {user.role !== 'admin' && (
              <button
                onClick={handleImpersonate}
                disabled={impersonating}
                className="mt-3 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
              >
                {impersonating ? 'Starting...' : 'Log in as this user'}
              </button>
            )}
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-6 mb-6">
          {/* Plan & subscription */}
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold">Plan &amp; Subscription</h2>
              <button
                onClick={() => { setPlanChoice(p.plan || 'free'); setShowPlanForm(!showPlanForm) }}
                className="text-sm text-blue-600 hover:underline"
              >
                {showPlanForm ? 'Cancel' : 'Change plan'}
              </button>
            </div>
            <dl className="space-y-2 text-sm">
              <Row label="Plan" value={p.plan || 'free'} />
              <Row label="Status" value={p.subscription_status || 'none'} />
              <Row label="Expires" value={p.plan_expires_at ? new Date(p.plan_expires_at).toLocaleDateString() : '—'} />
              <Row label="Auto-renew" value={p.auto_renew_enabled ? 'On' : 'Off'} />
              <Row label="Sessions used this month" value={p.sessions_used_this_month ?? '—'} />
              <Row label="Sessions reset" value={p.sessions_reset_date ? new Date(p.sessions_reset_date).toLocaleDateString() : '—'} />
              <Row label="Bonus sessions" value={p.bonus_sessions ?? 0} />
              <Row label="Razorpay subscription" value={p.razorpay_subscription_id || '—'} mono />
            </dl>

            <button
              onClick={() => setShowBonusForm(!showBonusForm)}
              className="mt-3 text-sm text-blue-600 hover:underline"
            >
              {showBonusForm ? 'Cancel' : 'Grant bonus sessions'}
            </button>

            {showBonusForm && (
              <div className="mt-4 pt-4 border-t space-y-3">
                <div>
                  <label htmlFor="bonusAmount" className="block text-xs text-gray-500 mb-1">Sessions to grant</label>
                  <input
                    id="bonusAmount"
                    type="number"
                    value={bonusAmount}
                    onChange={(e) => setBonusAmount(Number(e.target.value))}
                    className="w-full border rounded px-3 py-2 text-sm"
                  />
                  <p className="text-xs text-muted-foreground mt-1">Use a negative number to correct an over-grant.</p>
                </div>
                <div>
                  <label htmlFor="bonusReason" className="block text-xs text-gray-500 mb-1">Reason</label>
                  <input
                    id="bonusReason"
                    type="text"
                    value={bonusReason}
                    onChange={(e) => setBonusReason(e.target.value)}
                    placeholder="e.g. valid bug report — duplicate audio bug"
                    className="w-full border rounded px-3 py-2 text-sm"
                  />
                </div>
                <button
                  onClick={handleGrantBonus}
                  disabled={savingBonus}
                  className="w-full py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
                >
                  {savingBonus ? 'Saving...' : 'Grant'}
                </button>
              </div>
            )}

            {p.razorpay_subscription_id && p.auto_renew_enabled && (
              <button
                onClick={handleCancelSubscription}
                disabled={cancelling}
                className="mt-3 text-sm text-red-600 hover:underline disabled:opacity-50"
              >
                {cancelling ? 'Cancelling...' : 'Cancel subscription (turn off auto-renew)'}
              </button>
            )}

            {showPlanForm && (
              <div className="mt-4 pt-4 border-t space-y-3">
                <div>
                  <label htmlFor="planChoice" className="block text-xs text-gray-500 mb-1">Plan</label>
                  <select
                    id="planChoice"
                    value={planChoice}
                    onChange={(e) => setPlanChoice(e.target.value)}
                    className="w-full border rounded px-3 py-2 text-sm"
                  >
                    <option value="free">Free (reset now, no expiry)</option>
                    <option value="basic">Basic</option>
                    <option value="pro">Pro</option>
                    <option value="elite">Elite</option>
                  </select>
                </div>
                {planChoice !== 'free' && (
                  <div>
                    <label htmlFor="periodDays" className="block text-xs text-gray-500 mb-1">Days to grant</label>
                    <input
                      id="periodDays"
                      type="number"
                      min={1}
                      value={periodDays}
                      onChange={(e) => setPeriodDays(Number(e.target.value))}
                      className="w-full border rounded px-3 py-2 text-sm"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Extends from today, or from the current expiry if this is the same plan and it hasn&apos;t lapsed.
                    </p>
                  </div>
                )}
                <button
                  onClick={handleChangePlan}
                  disabled={savingPlan}
                  className="w-full py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
                >
                  {savingPlan ? 'Saving...' : 'Save'}
                </button>
              </div>
            )}
          </div>

          {/* OET profile */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-bold mb-4">OET Profile</h2>
            <dl className="space-y-2 text-sm">
              <Row label="Onboarding" value={p.onboarding_completed ? 'Completed' : 'Incomplete'} />
              <Row label="Exam date" value={p.exam_date ? new Date(p.exam_date).toLocaleDateString() : '—'} />
              <Row label="Target band" value={p.target_band || '—'} />
              <Row label="Has taken OET" value={p.has_taken_oet ? 'Yes' : 'No'} />
              <Row label="Previous band" value={p.previous_band ?? '—'} />
              <Row label="Nursing specialty" value={p.nursing_specialty || '—'} />
              <Row label="Years of experience" value={p.years_of_experience ?? '—'} />
              <Row label="Destination country" value={p.destination_country || '—'} />
            </dl>
          </div>
        </div>

        {/* Recent activity */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <h2 className="text-lg font-bold p-6 pb-0">Recent Practice Sessions</h2>
          <table className="w-full mt-4">
            <thead className="bg-gray-100">
              <tr>
                <th className="text-left py-3 px-6">Module</th>
                <th className="text-left py-3 px-6">Scenario</th>
                <th className="text-left py-3 px-6">Score</th>
                <th className="text-left py-3 px-6">Date</th>
              </tr>
            </thead>
            <tbody>
              {user.recent_submissions.map((s) => (
                <tr key={s.id} className="border-t">
                  <td className="py-3 px-6 capitalize">{s.module}</td>
                  <td className="py-3 px-6">{s.scenario_id ?? '—'}</td>
                  <td className="py-3 px-6">{s.score ?? '—'}</td>
                  <td className="py-3 px-6 text-sm text-gray-500">
                    {new Date(s.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {user.recent_submissions.length === 0 && (
            <div className="p-8 text-center text-gray-500">No practice sessions yet.</div>
          )}
        </div>

        {/* Voice session transcripts */}
        <div className="bg-white rounded-lg shadow overflow-hidden mt-6">
          <h2 className="text-lg font-bold p-6 pb-0">Voice Session Transcripts</h2>
          <p className="text-xs text-muted-foreground px-6 pt-1">Retained 90 days, admin-only. For background-check/account-safety review.</p>
          <div className="divide-y mt-4">
            {transcripts.map((t) => (
              <div key={t.id} className="p-6">
                <button
                  onClick={() => setOpenTranscriptId(openTranscriptId === t.id ? null : t.id)}
                  className="w-full flex justify-between items-center text-left"
                >
                  <span className="text-sm">
                    Scenario {t.scenario_id ?? '—'} · {t.transcript.length} turns
                  </span>
                  <span className="text-sm text-gray-500">
                    {new Date(t.created_at).toLocaleString()} {openTranscriptId === t.id ? '▲' : '▼'}
                  </span>
                </button>
                {openTranscriptId === t.id && (
                  <div className="mt-4 space-y-2 bg-gray-50 rounded p-4 max-h-96 overflow-y-auto">
                    {t.transcript.map((turn, i) => (
                      <p key={i} className="text-sm">
                        <span className={`font-semibold capitalize ${turn.role === 'nurse' ? 'text-blue-700' : 'text-gray-700'}`}>
                          {turn.role}:
                        </span>{' '}
                        {turn.text}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          {transcripts.length === 0 && (
            <div className="p-8 text-center text-gray-500">No voice session transcripts yet.</div>
          )}
        </div>

        {/* Payment history */}
        <div className="bg-white rounded-lg shadow overflow-hidden mt-6">
          <h2 className="text-lg font-bold p-6 pb-0">Payment History</h2>
          <table className="w-full mt-4">
            <thead className="bg-gray-100">
              <tr>
                <th className="text-left py-3 px-6">Date</th>
                <th className="text-left py-3 px-6">Plan</th>
                <th className="text-left py-3 px-6">Amount</th>
                <th className="text-left py-3 px-6">Status</th>
                <th className="text-left py-3 px-6">Payment ID</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((pay) => (
                <tr key={pay.id} className="border-t">
                  <td className="py-3 px-6 text-sm text-gray-500 whitespace-nowrap">
                    {new Date(pay.created_at).toLocaleString()}
                  </td>
                  <td className="py-3 px-6 capitalize">{pay.plan_id}</td>
                  <td className="py-3 px-6">
                    {(pay.amount / 100).toLocaleString(undefined, { style: 'currency', currency: pay.currency || 'INR' })}
                  </td>
                  <td className="py-3 px-6">
                    <span className={`px-2 py-1 rounded text-xs font-semibold capitalize ${
                      pay.status === 'paid' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-700'
                    }`}>
                      {pay.status}
                    </span>
                  </td>
                  <td className="py-3 px-6 text-xs font-mono text-muted-foreground">{pay.payment_id || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {payments.length === 0 && (
            <div className="p-8 text-center text-gray-500">No payments recorded.</div>
          )}
        </div>

        {/* Danger zone */}
        {user.role !== 'admin' && (
          <div className="bg-white rounded-lg shadow p-6 mt-6 border border-red-200">
            <h2 className="text-lg font-bold mb-4 text-red-700">Danger Zone</h2>

            {user.moderation.status !== 'active' && (
              <div className={`mb-4 p-3 rounded text-sm ${
                user.moderation.status === 'banned' ? 'bg-red-50 text-red-800' : 'bg-amber-50 text-amber-800'
              }`}>
                <div className="font-semibold capitalize">{user.moderation.status}</div>
                {user.moderation.reason && <div>Reason: {user.moderation.reason}</div>}
                {user.moderation.until && (
                  <div>Until {new Date(user.moderation.until).toLocaleString()}</div>
                )}
              </div>
            )}

            <div className="flex flex-wrap gap-3">
              {user.moderation.status === 'active' ? (
                <>
                  <button
                    onClick={() => handleModerate('suspend')}
                    disabled={moderating}
                    className="px-4 py-2 bg-amber-100 text-amber-800 text-sm font-semibold rounded-lg hover:bg-amber-200 transition disabled:opacity-50"
                  >
                    Suspend (30 days)
                  </button>
                  <button
                    onClick={() => handleModerate('ban')}
                    disabled={moderating}
                    className="px-4 py-2 bg-red-100 text-red-800 text-sm font-semibold rounded-lg hover:bg-red-200 transition disabled:opacity-50"
                  >
                    Ban
                  </button>
                </>
              ) : (
                <button
                  onClick={() => handleModerate('reinstate')}
                  disabled={moderating}
                  className="px-4 py-2 bg-green-100 text-green-800 text-sm font-semibold rounded-lg hover:bg-green-200 transition disabled:opacity-50"
                >
                  Reinstate
                </button>
              )}
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white text-sm font-semibold rounded-lg hover:bg-red-700 transition disabled:opacity-50 ml-auto"
              >
                {deleting ? 'Deleting...' : 'Delete user'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex justify-between border-b pb-2">
      <dt className="text-gray-500">{label}</dt>
      <dd className={mono ? 'font-mono text-xs' : 'font-semibold'}>{value}</dd>
    </div>
  )
}
