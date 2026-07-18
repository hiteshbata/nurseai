'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { downloadCsv } from '@/lib/csv'

interface FailedPayment {
  id: number
  user_id: string | null
  email: string
  payment_id: string | null
  plan_id: string | null
  amount: number | null
  currency: string
  reason: string | null
  created_at: string
  reminder_sent_at: string | null
}

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function AdminFailedPaymentsPage() {
  const router = useRouter()
  const [rows, setRows] = useState<FailedPayment[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/admin/failed-payments')
      .then((res) => setRows(res.data || []))
      .catch((error: any) => {
        if (error.response?.status === 403) router.push('/dashboard')
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-start justify-between gap-4 mb-2">
          <h1 className="text-3xl font-bold">Failed Payments</h1>
          <button
            onClick={() => downloadCsv('failed-payments.csv', rows)}
            disabled={rows.length === 0}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-semibold hover:bg-gray-200 disabled:opacity-50 shrink-0"
          >
            Export CSV
          </button>
        </div>
        <p className="text-sm text-gray-500 mb-6">
          Declined charges from Razorpay -- follow up with these people before they lose access at renewal.
          A reminder email also goes out automatically for recent declines (see Reminder column).
        </p>

        {loading ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center text-gray-500">Loading...</div>
        ) : rows.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center text-gray-500">
            No failed payments recorded.
          </div>
        ) : (
          <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">When</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">User</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Plan</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Amount</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Reason</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Reminder</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.map((row) => (
                    <tr key={row.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm text-gray-700 whitespace-nowrap">
                        {formatTimestamp(row.created_at)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {row.email || (row.user_id ? `${row.user_id.slice(0, 8)}...` : '—')}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">{row.plan_id || '—'}</td>
                      <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                        {row.amount != null ? `${row.currency} ${(row.amount / 100).toFixed(2)}` : '—'}
                      </td>
                      <td className="px-4 py-3 text-sm text-red-700 max-w-md truncate" title={row.reason || ''}>
                        {row.reason || '—'}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {row.reminder_sent_at ? (
                          <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded text-xs font-semibold">Sent</span>
                        ) : (
                          <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-xs font-semibold">Pending</span>
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
