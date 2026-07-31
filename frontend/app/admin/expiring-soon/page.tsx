'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { downloadCsv } from '@/lib/csv'

interface ExpiringUser {
  user_id: string
  email: string
  plan: string
  plan_expires_at: string
  subscription_status: string
  auto_renew_enabled: boolean
  expiry_reminder_sent_for: string | null
}

function formatDate(ts: string) {
  return new Date(ts).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function daysUntil(ts: string): number {
  return Math.ceil((new Date(ts).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
}

export default function AdminExpiringSoonPage() {
  const router = useRouter()
  const [rows, setRows] = useState<ExpiringUser[]>([])
  const [days, setDays] = useState(7)
  const [loading, setLoading] = useState(true)

  const fetchRows = (windowDays: number) => {
    setLoading(true)
    api.get('/admin/subscriptions/expiring-soon', { params: { days: windowDays } })
      .then((res) => setRows(res.data || []))
      .catch((error: any) => {
        if (error.response?.status === 403) router.push('/dashboard')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchRows(days)
  }, [])

  const dayBtn = (label: string, value: number) => (
    <button
      onClick={() => { setDays(value); fetchRows(value) }}
      aria-pressed={days === value}
      className={`px-4 py-2 rounded-lg text-sm font-semibold transition ${
        days === value ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
      }`}
    >
      {label}
    </button>
  )

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-start justify-between gap-4 mb-2">
          <h1 className="text-3xl font-bold">Expiring Soon</h1>
          <button
            onClick={() => downloadCsv('expiring-soon.csv', rows)}
            disabled={rows.length === 0}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-semibold hover:bg-gray-200 disabled:opacity-50 shrink-0"
          >
            Export CSV
          </button>
        </div>
        <p className="text-sm text-gray-500 mb-6">
          Paid users whose plan runs out soon -- reach out before they silently drop to free.
          A reminder email also goes out automatically once a day (see Reminder column).
        </p>

        <div className="flex gap-2 mb-6 flex-wrap">
          {dayBtn('Next 3 days', 3)}
          {dayBtn('Next 7 days', 7)}
          {dayBtn('Next 14 days', 14)}
          {dayBtn('Next 30 days', 30)}
        </div>

        {loading ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center text-gray-500">Loading...</div>
        ) : rows.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center text-gray-500">
            Nobody expiring in this window.
          </div>
        ) : (
          <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Expires</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">User</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Plan</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Auto-renew</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Reminder</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.map((row) => {
                    const left = daysUntil(row.plan_expires_at)
                    const reminded = row.expiry_reminder_sent_for === row.plan_expires_at
                    return (
                      <tr key={row.user_id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">
                          {formatDate(row.plan_expires_at)}
                          <span className={`ml-2 text-xs font-semibold ${left <= 3 ? 'text-red-600' : 'text-amber-600'}`}>
                            ({left <= 0 ? 'today' : `${left}d`})
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-700">
                          {row.email || `${row.user_id.slice(0, 8)}...`}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 capitalize">{row.plan}</td>
                        <td className="px-4 py-3 text-sm">
                          {row.auto_renew_enabled ? (
                            <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded text-xs font-semibold">On</span>
                          ) : (
                            <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded text-xs font-semibold">Off</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          {reminded ? (
                            <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded text-xs font-semibold">Sent</span>
                          ) : (
                            <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-xs font-semibold">Pending</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
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
