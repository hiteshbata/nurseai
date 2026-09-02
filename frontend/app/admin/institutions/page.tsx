'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import { Plus } from 'lucide-react'
import api from '@/lib/api'
import { Input } from '@/components/ui/input'
import { useAdminUser } from '@/app/admin/AdminShell'
import { MODULE_VALUES, validateRequired, validateContactEmail, validateQuota } from './[id]/helpers'
import { classifyCreateError } from './create-helpers'

interface InstitutionRow {
  id: string
  name: string
  slug: string
  logo_url: string | null
  status: string
  active_students: number
  enabled_modules: string[]
  speaking_sessions_per_month: number | null
  sessions_this_month: number
  admin_emails: string[]
  created_at: string
}

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking', reading: 'Reading', listening: 'Listening',
  writing: 'Writing', mock_tests: 'Mock Tests',
}

function statusBadge(status: string) {
  return status === 'active'
    ? 'bg-green-100 text-green-800'
    : 'bg-gray-100 text-gray-600'
}

interface CreateForm {
  name: string
  slug: string
  logo_url: string
  contact_email: string
  status: 'active' | 'suspended'
  modules: Set<string>
  quota: string
}

const EMPTY_CREATE_FORM: CreateForm = {
  name: '', slug: '', logo_url: '', contact_email: '', status: 'active', modules: new Set(), quota: '',
}

export default function AdminInstitutionsPage() {
  const router = useRouter()
  const { role } = useAdminUser()
  // Mirrors backend's require_admin on POST /admin/institutions -- a UI
  // convenience (hide a control the server would 403 on anyway), not the
  // authorization boundary itself.
  const canMutate = role === 'admin' || role === 'owner'

  const [rows, setRows] = useState<InstitutionRow[]>([])
  const [loading, setLoading] = useState(true)
  const [forbidden, setForbidden] = useState(false)

  const [showCreateForm, setShowCreateForm] = useState(false)
  const [createForm, setCreateForm] = useState<CreateForm>(EMPTY_CREATE_FORM)
  const [createErrors, setCreateErrors] = useState<{
    name?: string; slug?: string; contact_email?: string; quota?: string
  }>({})
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    api.get('/admin/institutions')
      .then((res) => setRows(res.data || []))
      .catch((error: any) => {
        if (error.response?.status === 403) {
          setForbidden(true)
          router.push('/dashboard')
        }
      })
      .finally(() => setLoading(false))
  }, [router])

  function toggleCreateModule(module: string) {
    setCreateForm((prev) => {
      const modules = new Set(prev.modules)
      if (modules.has(module)) modules.delete(module)
      else modules.add(module)
      return { ...prev, modules }
    })
  }

  async function handleCreateInstitution(e: React.FormEvent) {
    e.preventDefault()
    if (creating) return

    const nameResult = validateRequired(createForm.name, 'Name')
    const slugResult = validateRequired(createForm.slug, 'Slug')
    const emailResult = validateContactEmail(createForm.contact_email)
    const quotaResult = validateQuota(createForm.quota)
    setCreateErrors({
      name: nameResult.error, slug: slugResult.error,
      contact_email: emailResult.error, quota: quotaResult.error,
    })
    if (!nameResult.valid || !slugResult.valid || !emailResult.valid || !quotaResult.valid) return

    setCreating(true)
    try {
      const res = await api.post('/admin/institutions', {
        name: createForm.name.trim(),
        slug: createForm.slug.trim(),
        logo_url: createForm.logo_url.trim() || null,
        contact_email: createForm.contact_email.trim(),
        status: createForm.status,
        modules: Array.from(createForm.modules),
        speaking_sessions_per_month: quotaResult.value,
      })
      router.push(`/admin/institutions/${res.data.id}`)
    } catch (error: any) {
      toast.error(classifyCreateError(error.response?.status, error.response?.data?.detail))
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">Institutions</h1>
          {canMutate && !showCreateForm && (
            <button
              onClick={() => setShowCreateForm(true)}
              className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add Institution
            </button>
          )}
        </div>

        {showCreateForm && (
          <form onSubmit={handleCreateInstitution} className="mb-6 rounded-lg border border-gray-200 bg-white p-5">
            <h2 className="text-base font-bold text-gray-800">Add Institution</h2>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="create-name" className="text-sm font-semibold text-gray-700">Name</label>
                <Input
                  id="create-name"
                  value={createForm.name}
                  onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                  className="mt-1.5"
                />
                {createErrors.name && <p className="mt-1.5 text-sm text-red-600">{createErrors.name}</p>}
              </div>
              <div>
                <label htmlFor="create-slug" className="text-sm font-semibold text-gray-700">Slug</label>
                <Input
                  id="create-slug"
                  value={createForm.slug}
                  onChange={(e) => setCreateForm({ ...createForm, slug: e.target.value })}
                  className="mt-1.5"
                />
                {createErrors.slug && <p className="mt-1.5 text-sm text-red-600">{createErrors.slug}</p>}
              </div>
              <div>
                <label htmlFor="create-logo" className="text-sm font-semibold text-gray-700">Logo URL</label>
                <Input
                  id="create-logo"
                  value={createForm.logo_url}
                  onChange={(e) => setCreateForm({ ...createForm, logo_url: e.target.value })}
                  className="mt-1.5"
                />
              </div>
              <div>
                <label htmlFor="create-email" className="text-sm font-semibold text-gray-700">Contact Email</label>
                <Input
                  id="create-email"
                  type="email"
                  value={createForm.contact_email}
                  onChange={(e) => setCreateForm({ ...createForm, contact_email: e.target.value })}
                  className="mt-1.5"
                />
                {createErrors.contact_email && <p className="mt-1.5 text-sm text-red-600">{createErrors.contact_email}</p>}
              </div>
              <div>
                <label htmlFor="create-status" className="text-sm font-semibold text-gray-700">Status</label>
                <select
                  id="create-status"
                  value={createForm.status}
                  onChange={(e) => setCreateForm({ ...createForm, status: e.target.value as 'active' | 'suspended' })}
                  className="mt-1.5 h-11 w-full rounded-xl border border-gray-200 bg-gray-50/60 px-3.5 text-sm outline-none"
                >
                  <option value="active">Active</option>
                  <option value="suspended">Suspended</option>
                </select>
              </div>
              <div>
                <label htmlFor="create-quota" className="text-sm font-semibold text-gray-700">Speaking Sessions / Month</label>
                <Input
                  id="create-quota"
                  type="number"
                  min={1}
                  step={1}
                  value={createForm.quota}
                  onChange={(e) => setCreateForm({ ...createForm, quota: e.target.value })}
                  className="mt-1.5"
                />
                {createErrors.quota && <p className="mt-1.5 text-sm text-red-600">{createErrors.quota}</p>}
              </div>
            </div>

            <div className="mt-6">
              <div className="text-sm font-semibold text-gray-700 mb-2">Enabled Modules</div>
              <div className="flex flex-wrap gap-4">
                {MODULE_VALUES.map((module) => (
                  <label key={module} className="flex items-center gap-2 text-sm text-gray-800">
                    <input
                      type="checkbox"
                      checked={createForm.modules.has(module)}
                      onChange={() => toggleCreateModule(module)}
                      className="h-4 w-4"
                    />
                    {MODULE_LABELS[module] || module}
                  </label>
                ))}
              </div>
            </div>

            <div className="mt-6 flex gap-3">
              <button
                type="submit"
                disabled={creating}
                className="min-h-11 rounded-md bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {creating ? 'Creating...' : 'Create Institution'}
              </button>
              <button
                type="button"
                onClick={() => { setShowCreateForm(false); setCreateForm(EMPTY_CREATE_FORM); setCreateErrors({}) }}
                className="min-h-11 rounded-md border border-gray-300 px-4 text-sm font-semibold text-gray-800 hover:bg-gray-100"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-100">
                <tr>
                  <th className="text-left py-4 px-4">Institution</th>
                  <th className="text-left py-4 px-4">Status</th>
                  <th className="text-left py-4 px-4">Active Students</th>
                  <th className="text-left py-4 px-4">Enabled Modules</th>
                  <th className="text-left py-4 px-4">Speaking Quota</th>
                  <th className="text-left py-4 px-4">Sessions This Month</th>
                  <th className="text-left py-4 px-4">Admin</th>
                  <th className="text-left py-4 px-4">Created</th>
                  <th className="text-left py-4 px-4"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    className="border-t cursor-pointer hover:bg-gray-50"
                    onClick={() => router.push(`/admin/institutions/${r.id}`)}
                  >
                    <td className="py-4 px-4">
                      <div className="font-semibold">{r.name}</div>
                      <div className="text-sm text-gray-500">{r.slug}</div>
                    </td>
                    <td className="py-4 px-4">
                      <span className={`px-2 py-1 rounded text-xs font-semibold capitalize ${statusBadge(r.status)}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="py-4 px-4">{r.active_students}</td>
                    <td className="py-4 px-4 text-sm text-gray-600">
                      {r.enabled_modules.length
                        ? r.enabled_modules.map((m) => MODULE_LABELS[m] || m).join(', ')
                        : '—'}
                    </td>
                    <td className="py-4 px-4">{r.speaking_sessions_per_month ?? '—'}</td>
                    <td className="py-4 px-4">{r.sessions_this_month}</td>
                    <td className="py-4 px-4 text-sm text-gray-600">
                      {r.admin_emails.length ? r.admin_emails.join(', ') : '—'}
                    </td>
                    <td className="py-4 px-4 text-sm text-gray-500">
                      {new Date(r.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-4 px-4 text-right">
                      <button
                        onClick={(e) => { e.stopPropagation(); router.push(`/admin/institutions/${r.id}`) }}
                        className="text-xs text-blue-600 font-semibold hover:underline"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!loading && !forbidden && rows.length === 0 && (
            <div className="p-8 text-center text-gray-500">No institutions yet.</div>
          )}
          {loading && (
            <div className="p-8 text-center text-gray-500">Loading...</div>
          )}
        </div>
      </div>
    </div>
  )
}
