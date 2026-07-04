'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'

interface LogEntry {
  id: number
  timestamp: string
  user_id: string
  function_name: string
  error_type: string
  error_message: string
  resolved: boolean
}

type LogFilter = 'all' | 'unresolved' | 'today' | 'week'

export default function AdminLogsPage() {
  const router = useRouter()
  const { session, status } = useSupabaseSession()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [filter, setFilter] = useState<LogFilter>('unresolved')
  const [loading, setLoading] = useState(true)
  const [resolving, setResolving] = useState<number | null>(null)
  const [unresolvedCount, setUnresolvedCount] = useState(0)

  const fetchLogs = async (currentFilter: LogFilter) => {
    setLoading(true)
    try {
      const res = await api.get('/admin/logs', {
        params: { filter: currentFilter },
      })
      setLogs(res.data || [])

      const countRes = await api.get('/admin/logs/unresolved-count')
      setUnresolvedCount(countRes.data?.count || 0)
    } catch (error: any) {
      if (error.response?.status === 403) {
        router.push('/dashboard')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (status === 'loading') return
    if (!session?.user) {
      router.push('/auth/login')
      return
    }
    fetchLogs(filter)
  }, [status, session, router])

  const handleFilter = (newFilter: LogFilter) => {
    setFilter(newFilter)
    fetchLogs(newFilter)
  }

  const handleResolve = async (logId: number) => {
    setResolving(logId)
    try {
      await api.put(`/admin/logs/${logId}/resolve`, {})
      setLogs((prev) => prev.map((l) => (l.id === logId ? { ...l, resolved: true } : l)))
      setUnresolvedCount((prev) => Math.max(0, prev - 1))
    } catch (error) {
      console.error('Failed to resolve log:', error)
    } finally {
      setResolving(null)
    }
  }

  const filterBtn = (label: string, value: LogFilter) => (
    <button
      onClick={() => handleFilter(value)}
      className={`px-4 py-2 rounded-lg text-sm font-semibold transition ${
        filter === value
          ? 'bg-blue-600 text-white'
          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
      }`}
    >
      {label}
    </button>
  )

  const formatTimestamp = (ts: string) => {
    const d = new Date(ts)
    return d.toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold">Error Logs</h1>
            {unresolvedCount > 0 && (
              <span className="bg-red-500 text-white text-xs font-bold px-2.5 py-1 rounded-full">
                {unresolvedCount} unresolved
              </span>
            )}
          </div>
        </div>

        <div className="flex gap-2 mb-6 flex-wrap">
          {filterBtn('Unresolved Only', 'unresolved')}
          {filterBtn('Today', 'today')}
          {filterBtn('Last 7 Days', 'week')}
          {filterBtn('All', 'all')}
        </div>

        {loading ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center text-gray-500">
            Loading logs...
          </div>
        ) : logs.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center text-gray-500">
            No log entries found.
          </div>
        ) : (
          <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Timestamp</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">User</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Function</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Error Message</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Status</th>
                    <th className="px-4 py-3 text-right text-sm font-semibold text-gray-600">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {logs.map((log) => (
                    <tr key={log.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">
                        {formatTimestamp(log.timestamp)}
                      </td>
                      <td className="px-4 py-3 text-sm font-mono text-gray-600">
                        {log.user_id ? `${log.user_id.slice(0, 8)}...` : '—'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        <span className="bg-gray-100 px-2 py-0.5 rounded text-xs font-mono">
                          {log.function_name}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600 max-w-md truncate" title={log.error_message}>
                        {log.error_message}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {log.resolved ? (
                          <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded text-xs font-semibold">Resolved</span>
                        ) : (
                          <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded text-xs font-semibold">Unresolved</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {!log.resolved && (
                          <button
                            onClick={() => handleResolve(log.id)}
                            disabled={resolving === log.id}
                            className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-semibold hover:bg-green-700 transition disabled:opacity-50"
                          >
                            {resolving === log.id ? '...' : 'Resolve'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="mt-6">
          <button
            onClick={() => router.push('/admin')}
            className="text-sm text-blue-600 font-semibold hover:underline"
          >
            ← Back to Admin Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}
