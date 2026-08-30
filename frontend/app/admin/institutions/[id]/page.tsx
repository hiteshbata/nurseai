'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import toast from 'react-hot-toast'
import { Plus, Copy, Check } from 'lucide-react'
import api from '@/lib/api'
import { Input } from '@/components/ui/input'
import { useAdminUser } from '@/app/admin/AdminShell'
import {
  deriveDisplayStatus, usesLabel, formatInviteDate, validateMaxUses, validateExpiration,
} from '@/app/institution/invites/helpers'
import {
  MODULE_VALUES, validateRequired, validateContactEmail, validateQuota, classifySaveError,
} from './helpers'

interface InstitutionDetail {
  id: string
  name: string
  slug: string
  logo_url: string | null
  status: string
  contact_email: string
  speaking_sessions_per_month: number | null
  enabled_modules: string[]
  active_student_count: number
  admin_emails: string[]
  created_at: string
}

interface StudentRow {
  name: string | null
  email: string
  status: string
  joined_at: string | null
  sessions_used_this_month: number
  sessions_remaining: number | null
  latest_speaking_score: number | null
}

interface UsageSnapshot {
  active_student_count: number
  sessions_this_month: number
  speaking_sessions_per_month: number | null
  enabled_modules: string[]
}

interface AdminRow {
  email: string
  name: string | null
  status: string
  joined_at: string | null
}

interface InviteRow {
  id: string
  status: string
  max_uses: number | null
  use_count: number
  remaining_uses: number | null
  expires_at: string | null
  created_at: string
}

interface CreatedInvite {
  id: string
  token: string
  join_url: string
  role: string
  max_uses: number | null
  expires_at: string | null
}

interface SettingsForm {
  name: string
  slug: string
  logo_url: string
  contact_email: string
  modules: Set<string>
  quota: string
}

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking', reading: 'Reading', listening: 'Listening',
  writing: 'Writing', mock_tests: 'Mock Tests',
}

const TABS = ['Overview', 'Students', 'Usage', 'Admins', 'Invitations', 'Settings'] as const
type Tab = typeof TABS[number]

export default function AdminInstitutionDetailPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const institutionId = params.id
  const { role } = useAdminUser()
  // Mirrors backend/app/routers/admin.py's ROLE_RANK -- PATCH/POST
  // .../status/.../invites all require_admin server-side; analyst is
  // read-only there. This is a UI convenience only (hide/disable controls
  // an analyst's request would 403 on anyway), not a security boundary.
  const canMutate = role === 'admin' || role === 'owner'

  const [tab, setTab] = useState<Tab>('Overview')
  const [detail, setDetail] = useState<InstitutionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [statusSaving, setStatusSaving] = useState(false)

  const [students, setStudents] = useState<StudentRow[] | null>(null)
  const [studentsLoading, setStudentsLoading] = useState(false)
  const [usage, setUsage] = useState<UsageSnapshot | null>(null)
  const [usageLoading, setUsageLoading] = useState(false)
  const [admins, setAdmins] = useState<AdminRow[] | null>(null)
  const [adminsLoading, setAdminsLoading] = useState(false)
  const [invites, setInvites] = useState<InviteRow[] | null>(null)
  const [invitesLoading, setInvitesLoading] = useState(false)
  const [invitesRefreshKey, setInvitesRefreshKey] = useState(0)

  const [showInviteForm, setShowInviteForm] = useState(false)
  const [maxUsesInput, setMaxUsesInput] = useState('')
  const [expiresInput, setExpiresInput] = useState('')
  const [maxUsesError, setMaxUsesError] = useState<string | undefined>()
  const [expirationError, setExpirationError] = useState<string | undefined>()
  const [creatingInvite, setCreatingInvite] = useState(false)
  const [createdInvite, setCreatedInvite] = useState<CreatedInvite | null>(null)
  const [copied, setCopied] = useState(false)

  const [settingsForm, setSettingsForm] = useState<SettingsForm | null>(null)
  const [settingsErrors, setSettingsErrors] = useState<{
    name?: string; slug?: string; contact_email?: string; quota?: string
  }>({})
  const [savingSettings, setSavingSettings] = useState(false)

  useEffect(() => {
    if (!institutionId) return
    api.get(`/admin/institutions/${institutionId}`)
      .then((res) => setDetail(res.data))
      .catch((error: any) => {
        if (error.response?.status === 403) router.push('/dashboard')
        if (error.response?.status === 404) setNotFound(true)
      })
      .finally(() => setLoading(false))
  }, [institutionId, router])

  useEffect(() => {
    if (!institutionId) return
    if (tab === 'Students' && students === null && !studentsLoading) {
      setStudentsLoading(true)
      api.get(`/admin/institutions/${institutionId}/students`)
        .then((res) => setStudents(res.data || []))
        .finally(() => setStudentsLoading(false))
    }
    if (tab === 'Usage' && usage === null && !usageLoading) {
      setUsageLoading(true)
      api.get(`/admin/institutions/${institutionId}/usage`)
        .then((res) => setUsage(res.data))
        .finally(() => setUsageLoading(false))
    }
    if (tab === 'Admins' && admins === null && !adminsLoading) {
      setAdminsLoading(true)
      api.get(`/admin/institutions/${institutionId}/admins`)
        .then((res) => setAdmins(res.data || []))
        .finally(() => setAdminsLoading(false))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, institutionId])

  useEffect(() => {
    if (!institutionId) return
    if (tab !== 'Invitations') return
    setInvitesLoading(true)
    api.get(`/admin/institutions/${institutionId}/invites`)
      .then((res) => setInvites(res.data || []))
      .finally(() => setInvitesLoading(false))
  }, [tab, institutionId, invitesRefreshKey])

  // Settings form is seeded from the already-fetched overview `detail` --
  // no separate network round trip. Only seeded once per institution; the
  // Save handler below is what keeps it in sync with the server afterward.
  useEffect(() => {
    if (tab === 'Settings' && !settingsForm && detail) {
      setSettingsForm({
        name: detail.name,
        slug: detail.slug,
        logo_url: detail.logo_url || '',
        contact_email: detail.contact_email,
        modules: new Set(detail.enabled_modules),
        quota: detail.speaking_sessions_per_month != null ? String(detail.speaking_sessions_per_month) : '',
      })
    }
  }, [tab, detail, settingsForm])

  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(t)
  }, [copied])

  async function handleToggleStatus() {
    if (!detail || statusSaving) return
    const nextStatus = detail.status === 'active' ? 'suspended' : 'active'
    const verb = nextStatus === 'suspended' ? 'Suspend' : 'Reactivate'
    if (!confirm(`${verb} ${detail.name}?`)) return

    setStatusSaving(true)
    try {
      const res = await api.post(`/admin/institutions/${institutionId}/status`, { status: nextStatus })
      setDetail(res.data)
      toast.success(nextStatus === 'suspended' ? 'Institution suspended' : 'Institution reactivated')
    } catch (error: any) {
      toast.error(classifySaveError(error.response?.status, error.response?.data?.detail))
    } finally {
      setStatusSaving(false)
    }
  }

  function toggleModule(module: string) {
    setSettingsForm((prev) => {
      if (!prev) return prev
      const modules = new Set(prev.modules)
      if (modules.has(module)) modules.delete(module)
      else modules.add(module)
      return { ...prev, modules }
    })
  }

  async function handleSaveSettings(e: React.FormEvent) {
    e.preventDefault()
    if (!settingsForm || savingSettings) return

    const nameResult = validateRequired(settingsForm.name, 'Name')
    const slugResult = validateRequired(settingsForm.slug, 'Slug')
    const emailResult = validateContactEmail(settingsForm.contact_email)
    const quotaResult = validateQuota(settingsForm.quota)
    setSettingsErrors({
      name: nameResult.error, slug: slugResult.error,
      contact_email: emailResult.error, quota: quotaResult.error,
    })
    if (!nameResult.valid || !slugResult.valid || !emailResult.valid || !quotaResult.valid) return

    setSavingSettings(true)
    try {
      const res = await api.patch(`/admin/institutions/${institutionId}`, {
        name: settingsForm.name.trim(),
        slug: settingsForm.slug.trim(),
        logo_url: settingsForm.logo_url.trim() || null,
        contact_email: settingsForm.contact_email.trim(),
        modules: Array.from(settingsForm.modules),
        speaking_sessions_per_month: quotaResult.value,
      })
      setDetail(res.data)
      toast.success('Settings saved')
    } catch (error: any) {
      toast.error(classifySaveError(error.response?.status, error.response?.data?.detail))
    } finally {
      setSavingSettings(false)
    }
  }

  function openInviteForm() {
    setShowInviteForm(true)
  }

  function resetInviteForm() {
    setCreatedInvite(null)
    setMaxUsesInput('')
    setExpiresInput('')
    setMaxUsesError(undefined)
    setExpirationError(undefined)
  }

  async function handleCreateInvite(e: React.FormEvent) {
    e.preventDefault()
    if (creatingInvite) return
    const maxUsesResult = validateMaxUses(maxUsesInput)
    const expirationResult = validateExpiration(expiresInput)
    setMaxUsesError(maxUsesResult.error)
    setExpirationError(expirationResult.error)
    if (!maxUsesResult.valid || !expirationResult.valid) return

    setCreatingInvite(true)
    try {
      const res = await api.post(`/admin/institutions/${institutionId}/invites`, {
        max_uses: maxUsesResult.value,
        expires_at: expirationResult.iso,
      })
      setCreatedInvite(res.data)
      setInvitesRefreshKey((k) => k + 1)
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Could not create invitation. Please try again.')
    } finally {
      setCreatingInvite(false)
    }
  }

  async function handleCopy(joinUrl: string) {
    try {
      await navigator.clipboard.writeText(joinUrl)
      setCopied(true)
    } catch {
      toast.error('Could not copy — copy the link manually.')
    }
  }

  async function handleRevokeInvite(invite: InviteRow) {
    if (!confirm('Revoke this invitation?\n\nStudents who have already joined will not be affected.')) return
    try {
      await api.post(`/admin/institutions/${institutionId}/invites/${invite.id}/revoke`)
      toast.success('Invitation revoked')
      setInvitesRefreshKey((k) => k + 1)
    } catch (error: any) {
      const httpStatus = error.response?.status
      if (httpStatus === 404) {
        toast.error('Invitation not found.')
        setInvitesRefreshKey((k) => k + 1)
      } else if (httpStatus === 403) {
        toast.error("You don't have permission to manage invitations.")
      } else {
        toast.error('Something went wrong. Please try again.')
      }
    }
  }

  if (loading) {
    return <div className="min-h-screen bg-gray-50 py-12 px-4 text-center text-gray-500">Loading...</div>
  }

  if (notFound || !detail) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4 text-center">
        <p className="text-gray-500 mb-4">Institution not found.</p>
        <Link href="/admin/institutions" className="text-sm text-blue-600 font-semibold hover:underline">
          ← Back to Institutions
        </Link>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-5xl mx-auto">
        <Link href="/admin/institutions" className="text-sm text-blue-600 font-semibold hover:underline">
          ← Back to Institutions
        </Link>

        <div className="flex flex-col gap-3 mt-4 mb-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold">{detail.name}</h1>
            <p className="text-sm text-gray-500">{detail.slug}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className={`px-3 py-1 rounded text-sm font-semibold capitalize ${
              detail.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
            }`}>
              {detail.status}
            </span>
            {canMutate && (
              <button
                onClick={handleToggleStatus}
                disabled={statusSaving}
                className="text-sm font-semibold rounded-md border border-gray-300 px-3 py-1.5 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {statusSaving ? 'Saving...' : detail.status === 'active' ? 'Suspend' : 'Reactivate'}
              </button>
            )}
          </div>
        </div>

        <div className="flex gap-1 mb-6 border-b overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`shrink-0 px-4 py-2 text-sm font-semibold border-b-2 -mb-px ${
                tab === t ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === 'Overview' && (
          <div className="bg-white rounded-lg shadow p-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Contact Email" value={detail.contact_email} />
            <Field label="Created" value={new Date(detail.created_at).toLocaleDateString()} />
            <Field label="Active Students" value={String(detail.active_student_count)} />
            <Field label="Speaking Quota" value={detail.speaking_sessions_per_month != null ? String(detail.speaking_sessions_per_month) : 'Unlimited'} />
            <Field
              label="Enabled Modules"
              value={detail.enabled_modules.length ? detail.enabled_modules.map((m) => MODULE_LABELS[m] || m).join(', ') : '—'}
            />
            <Field label="Admins" value={detail.admin_emails.length ? detail.admin_emails.join(', ') : '—'} />
          </div>
        )}

        {tab === 'Students' && (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            {studentsLoading ? (
              <div className="p-8 text-center text-gray-500">Loading...</div>
            ) : !students || students.length === 0 ? (
              <div className="p-8 text-center text-gray-500">No students yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-100">
                    <tr>
                      <th className="text-left py-3 px-4">Name</th>
                      <th className="text-left py-3 px-4">Email</th>
                      <th className="text-left py-3 px-4">Status</th>
                      <th className="text-left py-3 px-4">Sessions Used</th>
                      <th className="text-left py-3 px-4">Sessions Remaining</th>
                      <th className="text-left py-3 px-4">Latest Speaking Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {students.map((s, i) => (
                      <tr key={i} className="border-t">
                        <td className="py-3 px-4">{s.name || '—'}</td>
                        <td className="py-3 px-4 text-sm text-gray-500">{s.email}</td>
                        <td className="py-3 px-4 capitalize">{s.status}</td>
                        <td className="py-3 px-4">{s.sessions_used_this_month}</td>
                        <td className="py-3 px-4">{s.sessions_remaining ?? 'Unlimited'}</td>
                        <td className="py-3 px-4">{s.latest_speaking_score ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === 'Usage' && (
          <div className="bg-white rounded-lg shadow p-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
            {usageLoading || !usage ? (
              <div className="sm:col-span-2 p-8 text-center text-gray-500">Loading...</div>
            ) : (
              <>
                <Field label="Active Students" value={String(usage.active_student_count)} />
                <Field label="Sessions This Month" value={String(usage.sessions_this_month)} />
                <Field label="Speaking Quota" value={usage.speaking_sessions_per_month != null ? String(usage.speaking_sessions_per_month) : 'Unlimited'} />
                <Field
                  label="Enabled Modules"
                  value={usage.enabled_modules.length ? usage.enabled_modules.map((m) => MODULE_LABELS[m] || m).join(', ') : '—'}
                />
              </>
            )}
          </div>
        )}

        {tab === 'Admins' && (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            {adminsLoading ? (
              <div className="p-8 text-center text-gray-500">Loading...</div>
            ) : !admins || admins.length === 0 ? (
              <div className="p-8 text-center text-gray-500">No admins assigned yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-100">
                    <tr>
                      <th className="text-left py-3 px-4">Name</th>
                      <th className="text-left py-3 px-4">Email</th>
                      <th className="text-left py-3 px-4">Status</th>
                      <th className="text-left py-3 px-4">Joined</th>
                    </tr>
                  </thead>
                  <tbody>
                    {admins.map((a, i) => (
                      <tr key={i} className="border-t">
                        <td className="py-3 px-4">{a.name || '—'}</td>
                        <td className="py-3 px-4 text-sm text-gray-500">{a.email}</td>
                        <td className="py-3 px-4 capitalize">{a.status}</td>
                        <td className="py-3 px-4 text-sm text-gray-500">
                          {a.joined_at ? new Date(a.joined_at).toLocaleDateString() : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === 'Invitations' && (
          <div>
            {canMutate && !showInviteForm && !createdInvite && (
              <div className="mb-4">
                <button
                  onClick={openInviteForm}
                  className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
                >
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  Create Invitation
                </button>
              </div>
            )}

            {createdInvite && (
              <div className="mb-6 rounded-lg border border-green-200 bg-green-50 p-5">
                <h2 className="text-base font-bold text-gray-800">Invitation created</h2>
                <p className="mt-1 text-sm text-gray-600">Share this link with students:</p>
                <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                  <input
                    readOnly
                    value={createdInvite.join_url}
                    onFocus={(e) => e.currentTarget.select()}
                    className="h-11 w-full select-all rounded-md border border-gray-200 bg-white px-3.5 text-sm text-gray-800 outline-none"
                  />
                  <button
                    onClick={() => handleCopy(createdInvite.join_url)}
                    className="flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-md border border-gray-300 px-4 text-sm font-semibold text-gray-800 hover:bg-gray-100"
                  >
                    {copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
                    {copied ? 'Copied' : 'Copy link'}
                  </button>
                </div>
                <button
                  onClick={resetInviteForm}
                  className="mt-4 text-sm font-semibold text-blue-600 hover:underline"
                >
                  Create another invitation
                </button>
              </div>
            )}

            {!createdInvite && showInviteForm && (
              <form onSubmit={handleCreateInvite} className="mb-6 rounded-lg border border-gray-200 bg-white p-5">
                <h2 className="text-base font-bold text-gray-800">Create Invitation</h2>
                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="invite-max-uses" className="text-sm font-semibold text-gray-700">
                      Maximum uses
                    </label>
                    <Input
                      id="invite-max-uses"
                      type="number"
                      min={1}
                      step={1}
                      placeholder="Unlimited"
                      value={maxUsesInput}
                      onChange={(e) => {
                        setMaxUsesInput(e.target.value)
                        if (maxUsesError) setMaxUsesError(undefined)
                      }}
                      className="mt-1.5"
                    />
                    {maxUsesError && <p className="mt-1.5 text-sm text-red-600">{maxUsesError}</p>}
                  </div>
                  <div>
                    <label htmlFor="invite-expires" className="text-sm font-semibold text-gray-700">
                      Expires
                    </label>
                    <Input
                      id="invite-expires"
                      type="datetime-local"
                      value={expiresInput}
                      onChange={(e) => {
                        setExpiresInput(e.target.value)
                        if (expirationError) setExpirationError(undefined)
                      }}
                      className="mt-1.5"
                    />
                    {expirationError && <p className="mt-1.5 text-sm text-red-600">{expirationError}</p>}
                  </div>
                </div>
                <div className="mt-5 flex gap-3">
                  <button
                    type="submit"
                    disabled={creatingInvite}
                    className="min-h-11 rounded-md bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {creatingInvite ? 'Creating...' : 'Create Invitation'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowInviteForm(false)}
                    className="min-h-11 rounded-md border border-gray-300 px-4 text-sm font-semibold text-gray-800 hover:bg-gray-100"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}

            <div className="bg-white rounded-lg shadow overflow-hidden">
              {invitesLoading ? (
                <div className="p-8 text-center text-gray-500">Loading...</div>
              ) : !invites || invites.length === 0 ? (
                <div className="p-8 text-center text-gray-500">No invitations yet.</div>
              ) : (
                <>
                  {/* Desktop: table */}
                  <div className="hidden md:block overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-gray-100">
                        <tr>
                          <th className="text-left py-3 px-4">Status</th>
                          <th className="text-left py-3 px-4">Uses</th>
                          <th className="text-left py-3 px-4">Remaining</th>
                          <th className="text-left py-3 px-4">Expires</th>
                          <th className="text-left py-3 px-4">Created</th>
                          <th className="text-left py-3 px-4">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {invites.map((invite) => {
                          const displayStatus = deriveDisplayStatus(invite.status, invite.expires_at)
                          return (
                            <tr key={invite.id} className="border-t">
                              <td className="py-3 px-4 capitalize">{displayStatus}</td>
                              <td className="py-3 px-4">{invite.use_count}</td>
                              <td className="py-3 px-4">
                                {invite.remaining_uses === null ? 'Unlimited' : invite.remaining_uses}
                              </td>
                              <td className="py-3 px-4 text-sm text-gray-500">{formatInviteDate(invite.expires_at)}</td>
                              <td className="py-3 px-4 text-sm text-gray-500">{formatInviteDate(invite.created_at)}</td>
                              <td className="py-3 px-4">
                                {canMutate && displayStatus === 'active' && (
                                  <button
                                    onClick={() => handleRevokeInvite(invite)}
                                    className="text-sm font-semibold text-red-600 hover:underline"
                                  >
                                    Revoke
                                  </button>
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Mobile: stacked cards */}
                  <div className="flex flex-col gap-3 p-3 md:hidden">
                    {invites.map((invite) => {
                      const displayStatus = deriveDisplayStatus(invite.status, invite.expires_at)
                      return (
                        <div key={invite.id} className="rounded-lg border border-gray-200 p-4">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-semibold capitalize">{displayStatus}</span>
                            {canMutate && displayStatus === 'active' && (
                              <button
                                onClick={() => handleRevokeInvite(invite)}
                                className="text-sm font-semibold text-red-600 hover:underline"
                              >
                                Revoke
                              </button>
                            )}
                          </div>
                          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                            <dt className="text-gray-500">Uses</dt>
                            <dd className="text-gray-800">{usesLabel(invite.use_count, invite.remaining_uses)}</dd>
                            <dt className="text-gray-500">Expires</dt>
                            <dd className="text-gray-800">{formatInviteDate(invite.expires_at)}</dd>
                            <dt className="text-gray-500">Created</dt>
                            <dd className="text-gray-800">{formatInviteDate(invite.created_at)}</dd>
                          </dl>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {tab === 'Settings' && (
          <div className="bg-white rounded-lg shadow p-6">
            {!settingsForm ? (
              <div className="p-8 text-center text-gray-500">Loading...</div>
            ) : (
              <form onSubmit={handleSaveSettings}>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="settings-name" className="text-sm font-semibold text-gray-700">Name</label>
                    <Input
                      id="settings-name"
                      value={settingsForm.name}
                      onChange={(e) => setSettingsForm({ ...settingsForm, name: e.target.value })}
                      className="mt-1.5"
                    />
                    {settingsErrors.name && <p className="mt-1.5 text-sm text-red-600">{settingsErrors.name}</p>}
                  </div>
                  <div>
                    <label htmlFor="settings-slug" className="text-sm font-semibold text-gray-700">Slug</label>
                    <Input
                      id="settings-slug"
                      value={settingsForm.slug}
                      onChange={(e) => setSettingsForm({ ...settingsForm, slug: e.target.value })}
                      className="mt-1.5"
                    />
                    {settingsErrors.slug && <p className="mt-1.5 text-sm text-red-600">{settingsErrors.slug}</p>}
                  </div>
                  <div>
                    <label htmlFor="settings-logo" className="text-sm font-semibold text-gray-700">Logo URL</label>
                    <Input
                      id="settings-logo"
                      value={settingsForm.logo_url}
                      onChange={(e) => setSettingsForm({ ...settingsForm, logo_url: e.target.value })}
                      className="mt-1.5"
                    />
                  </div>
                  <div>
                    <label htmlFor="settings-email" className="text-sm font-semibold text-gray-700">Contact Email</label>
                    <Input
                      id="settings-email"
                      type="email"
                      value={settingsForm.contact_email}
                      onChange={(e) => setSettingsForm({ ...settingsForm, contact_email: e.target.value })}
                      className="mt-1.5"
                    />
                    {settingsErrors.contact_email && <p className="mt-1.5 text-sm text-red-600">{settingsErrors.contact_email}</p>}
                  </div>
                  <div>
                    <label htmlFor="settings-quota" className="text-sm font-semibold text-gray-700">Speaking Sessions / Month</label>
                    <Input
                      id="settings-quota"
                      type="number"
                      min={1}
                      step={1}
                      value={settingsForm.quota}
                      onChange={(e) => setSettingsForm({ ...settingsForm, quota: e.target.value })}
                      className="mt-1.5"
                    />
                    {settingsErrors.quota && <p className="mt-1.5 text-sm text-red-600">{settingsErrors.quota}</p>}
                  </div>
                </div>

                <div className="mt-6">
                  <div className="text-sm font-semibold text-gray-700 mb-2">Enabled Modules</div>
                  <div className="flex flex-wrap gap-4">
                    {MODULE_VALUES.map((module) => (
                      <label key={module} className="flex items-center gap-2 text-sm text-gray-800">
                        <input
                          type="checkbox"
                          checked={settingsForm.modules.has(module)}
                          onChange={() => toggleModule(module)}
                          className="h-4 w-4"
                        />
                        {MODULE_LABELS[module] || module}
                      </label>
                    ))}
                  </div>
                </div>

                <div className="mt-6">
                  <button
                    type="submit"
                    disabled={savingSettings || !canMutate}
                    title={!canMutate ? 'Admin role required' : undefined}
                    className="min-h-11 rounded-md bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {savingSettings ? 'Saving...' : 'Save Settings'}
                  </button>
                </div>
              </form>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-semibold text-gray-500 mb-1">{label}</div>
      <div className="text-sm text-gray-800">{value}</div>
    </div>
  )
}
