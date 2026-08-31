'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

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

export default function AdminInstitutionsPage() {
  const router = useRouter()
  const [rows, setRows] = useState<InstitutionRow[]>([])
  const [loading, setLoading] = useState(true)
  const [forbidden, setForbidden] = useState(false)

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

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">Institutions</h1>
        </div>

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
