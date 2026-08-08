'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import toast from 'react-hot-toast'

interface UserRow {
  user_id: string
  email: string
  name: string
  created_at: string
  role: string
  plan: string
  subscription_status: string
  plan_expires_at: string | null
  sessions: number
  avg_score: number | null
}

const PAGE_SIZE = 50

export default function AdminUsersPage() {
  const router = useRouter()
  const [users, setUsers] = useState<UserRow[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => fetchUsers(), 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, offset])

  const fetchUsers = async () => {
    setLoading(true)
    try {
      const response = await api.get('/admin/users/list', {
        params: { search: search || undefined, limit: PAGE_SIZE, offset },
      })
      setUsers(response.data.users)
      setTotal(response.data.total)
    } catch (error: any) {
      if (error.response?.status === 403) {
        alert('Admin access required')
        router.push('/')
      }
      console.error('Failed to fetch users:', error)
    } finally {
      setLoading(false)
    }
  }

  const syncUsers = async () => {
    setSyncing(true)
    try {
      const res = await api.post('/admin/users/backfill-mirror')
      toast.success(`Synced ${res.data.synced} users`)
      fetchUsers()
    } catch {
      toast.error('Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  const planBadge = (plan: string) => {
    const colors: Record<string, string> = {
      free: 'bg-gray-100 text-gray-600',
      basic: 'bg-blue-100 text-blue-800',
      pro: 'bg-purple-100 text-purple-800',
      elite: 'bg-amber-100 text-amber-800',
    }
    return colors[plan] || 'bg-gray-100 text-gray-600'
  }

  const statusBadge = (status: string) => {
    if (status === 'active') return 'bg-green-100 text-green-800'
    if (status === 'expired' || status === 'cancelled') return 'bg-red-100 text-red-700'
    return 'bg-gray-100 text-gray-600'
  }

  // Matches backend/app/routers/admin.py's ALLOWED_ROLES.
  const ROLE_LABEL: Record<string, string> = { user: 'None', support: 'Support', analyst: 'Analyst', admin: 'Admin', owner: 'Owner' }
  const roleBadge = (role: string) => {
    const colors: Record<string, string> = {
      owner: 'bg-amber-100 text-amber-800',
      admin: 'bg-purple-100 text-purple-800',
      analyst: 'bg-blue-100 text-blue-800',
      support: 'bg-teal-100 text-teal-800',
    }
    return colors[role] || 'bg-gray-100 text-gray-600'
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-8 gap-4">
          <h1 className="text-3xl font-bold">Users</h1>
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setOffset(0) }}
              placeholder="Search by name or email..."
              className="w-80 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={syncUsers}
              disabled={syncing}
              title="Re-sync this list from Supabase Auth -- run once after setup, or if a user isn't showing up"
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-semibold hover:bg-gray-200 disabled:opacity-50 whitespace-nowrap"
            >
              {syncing ? 'Syncing...' : 'Sync users'}
            </button>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-100">
              <tr>
                <th className="text-left py-4 px-4">User</th>
                <th className="text-left py-4 px-4">Role</th>
                <th className="text-left py-4 px-4">Plan</th>
                <th className="text-left py-4 px-4">Status</th>
                <th className="text-left py-4 px-4">Sessions</th>
                <th className="text-left py-4 px-4">Avg Score</th>
                <th className="text-left py-4 px-4">Joined</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr
                  key={u.user_id}
                  className="border-t cursor-pointer hover:bg-gray-50"
                  onClick={() => router.push(`/admin/users/${u.user_id}`)}
                >
                  <td className="py-4 px-4">
                    <div className="font-semibold">{u.name || '(no name)'}</div>
                    <div className="text-sm text-gray-500">{u.email}</div>
                  </td>
                  <td className="py-4 px-4">
                    <span className={`px-2 py-1 rounded text-xs font-semibold ${roleBadge(u.role)}`}>
                      {ROLE_LABEL[u.role] || u.role}
                    </span>
                  </td>
                  <td className="py-4 px-4">
                    <span className={`px-2 py-1 rounded text-xs font-semibold capitalize ${planBadge(u.plan)}`}>
                      {u.plan}
                    </span>
                  </td>
                  <td className="py-4 px-4">
                    <span className={`px-2 py-1 rounded text-xs font-semibold capitalize ${statusBadge(u.subscription_status)}`}>
                      {u.subscription_status}
                    </span>
                  </td>
                  <td className="py-4 px-4">{u.sessions}</td>
                  <td className="py-4 px-4">{u.avg_score ?? '—'}</td>
                  <td className="py-4 px-4 text-sm text-gray-500">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {!loading && users.length === 0 && (
            <div className="p-8 text-center text-gray-500">
              {search ? 'No users match your search.' : 'No users found.'}
            </div>
          )}
          {loading && (
            <div className="p-8 text-center text-gray-500">Loading...</div>
          )}
        </div>

        {total > PAGE_SIZE && (
          <div className="flex justify-between items-center mt-4 text-sm text-gray-600">
            <span>
              Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <div className="flex gap-2">
              <button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                className="px-3 py-1 border rounded disabled:opacity-40"
              >
                Previous
              </button>
              <button
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                className="px-3 py-1 border rounded disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
