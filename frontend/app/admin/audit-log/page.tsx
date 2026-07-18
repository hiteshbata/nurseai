'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface AuditEntry {
  created_at: string
  admin_email: string
  action: string
  target_type: string
  target_label: string | null
  detail: Record<string, any> | null
}

const ACTION_COLORS: Record<string, string> = {
  role_changed: 'bg-purple-100 text-purple-800',
  plan_changed: 'bg-blue-100 text-blue-800',
  scenario_created: 'bg-green-100 text-green-800',
  scenario_updated: 'bg-green-100 text-green-800',
  scenario_deactivated: 'bg-gray-100 text-gray-600',
  setting_updated: 'bg-indigo-100 text-indigo-800',
  suspend: 'bg-amber-100 text-amber-800',
  ban: 'bg-red-100 text-red-800',
  reinstate: 'bg-green-100 text-green-800',
  delete: 'bg-red-100 text-red-800',
  impersonated: 'bg-blue-100 text-blue-800',
}

function formatDetail(detail: Record<string, any> | null): string {
  if (!detail) return ''
  return Object.entries(detail)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${k}: ${v}`)
    .join(', ')
}

export default function AdminAuditLogPage() {
  const router = useRouter()
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchLog()
  }, [])

  const fetchLog = async () => {
    try {
      const response = await api.get('/admin/audit-log', { params: { limit: 150 } })
      setEntries(response.data)
    } catch (error: any) {
      if (error.response?.status === 403) {
        alert('Admin access required')
        router.push('/')
      }
      console.error('Failed to fetch audit log:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading audit log...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">Action History</h1>
        <p className="text-gray-500 mb-8">Every admin action — role and plan changes, content edits, suspensions, bans, and impersonation sessions.</p>

        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-100">
              <tr>
                <th className="text-left py-3 px-4">When</th>
                <th className="text-left py-3 px-4">Admin</th>
                <th className="text-left py-3 px-4">Action</th>
                <th className="text-left py-3 px-4">Target</th>
                <th className="text-left py-3 px-4">Detail</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i} className="border-t">
                  <td className="py-3 px-4 text-sm text-gray-500 whitespace-nowrap">
                    {new Date(e.created_at).toLocaleString()}
                  </td>
                  <td className="py-3 px-4 text-sm">{e.admin_email}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-1 rounded text-xs font-semibold ${ACTION_COLORS[e.action] || 'bg-gray-100 text-gray-600'}`}>
                      {e.action.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-sm">{e.target_label || '—'}</td>
                  <td className="py-3 px-4 text-sm text-gray-500">{formatDetail(e.detail)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {entries.length === 0 && (
            <div className="p-8 text-center text-gray-500">No admin actions recorded yet.</div>
          )}
        </div>
      </div>
    </div>
  )
}
