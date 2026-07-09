'use client'

import { useEffect, useState } from 'react'
import api from '@/lib/api'

interface Stats {
  total_users: number
  total_submissions: number
  total_active_scenarios: number
  submissions_by_module: Record<string, number>
  unresolved_logs: number
}

interface User {
  user_id: string
  role: string
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchStats()
    fetchUsers()
  }, [])

  const fetchStats = async () => {
    try {
      const response = await api.get('/admin/stats')
      setStats(response.data)
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    }
  }

  const fetchUsers = async () => {
    try {
      const response = await api.get('/admin/users')
      setUsers(response.data)
    } catch (error) {
      console.error('Failed to fetch users:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading admin panel...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">SpeakOET Admin Dashboard</h1>
        
        {/* Stats Cards */}
        <div className="grid md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-lg font-semibold text-gray-600 mb-2">Total Users</h3>
            <p className="text-4xl font-bold text-blue-600">{stats?.total_users || 0}</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-lg font-semibold text-gray-600 mb-2">Total Submissions</h3>
            <p className="text-4xl font-bold text-green-600">{stats?.total_submissions || 0}</p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-lg font-semibold text-gray-600 mb-2">Active Scenarios</h3>
            <p className="text-4xl font-bold text-purple-600">{stats?.total_active_scenarios || 0}</p>
          </div>
        </div>

        {/* Quick Links */}
          <div className="bg-white p-6 rounded-lg shadow mb-8">
            <h2 className="text-2xl font-bold mb-4">Quick Actions</h2>
            <div className="flex flex-wrap gap-4">
              <a
                href="/admin/scenarios"
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
              >
                Manage Scenarios
              </a>
              <a
                href="/admin/scenario-generator"
                className="px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition flex items-center gap-2"
              >
                <span>🪄</span> Scenario Generator
              </a>
              <a
                href="/admin/logs"
                className="px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition flex items-center gap-2"
              >
                <span>⚠️</span> Error Logs
                {(stats?.unresolved_logs ?? 0) > 0 && (
                  <span className="bg-white text-red-600 text-xs font-bold px-2 py-0.5 rounded-full ml-1">
                    {stats.unresolved_logs}
                  </span>
                )}
              </a>
              <a
                href="/admin/settings"
                className="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
              >
                Settings
              </a>
            </div>
          </div>

        {/* Modules Breakdown */}
        <div className="bg-white p-6 rounded-lg shadow mb-8">
          <h2 className="text-2xl font-bold mb-4">Submissions by Module</h2>
          <div className="space-y-2">
            {stats?.submissions_by_module && Object.entries(stats.submissions_by_module).map(([mod, count]) => (
              <div key={mod} className="flex justify-between py-2 border-b">
                <span className="font-semibold capitalize">{mod}</span>
                <span>{count as number}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Users Table */}
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-2xl font-bold mb-4">Users</h2>
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2">User ID</th>
                <th className="text-left py-2">Role</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.user_id} className="border-b">
                  <td className="py-2 font-mono text-sm">{user.user_id.slice(0, 8)}...</td>
                  <td className="py-2">
                    <span className={`px-2 py-1 rounded text-xs font-semibold ${
                      user.role === 'admin' ? 'bg-purple-100 text-purple-800' : 'bg-gray-100'
                    }`}>
                      {user.role}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
