'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import toast from 'react-hot-toast'

interface MockTestPack {
  id: number
  label: string
  is_active: boolean
  created_at: string
  listening_title: string | null
  reading_title: string | null
  writing_title: string | null
  speaking_title_1: string | null
  speaking_title_2: string | null
}

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function AdminMockTestsPage() {
  const router = useRouter()
  const [rows, setRows] = useState<MockTestPack[]>([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)

  const fetchPacks = () => {
    api.get('/mock/admin/tests')
      .then((res) => setRows(res.data || []))
      .catch((error: any) => {
        if (error.response?.status === 403) router.push('/dashboard')
      })
      .finally(() => setLoading(false))
  }

  useEffect(fetchPacks, [])

  const generate = async () => {
    setGenerating(true)
    try {
      await api.post('/mock/admin/generate')
      toast.success('New mock test pack generated')
      fetchPacks()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to generate a new pack')
    } finally {
      setGenerating(false)
    }
  }

  const toggleActive = async (p: MockTestPack) => {
    setRows(rows.map((r) => (r.id === p.id ? { ...r, is_active: !p.is_active } : r)))
    try {
      await api.post(`/mock/admin/tests/${p.id}/active`, { is_active: !p.is_active })
    } catch {
      toast.error('Failed to update pack')
      fetchPacks()
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">Mock Tests</h1>
        <p className="text-sm text-gray-500 mb-6">
          Each pack freezes one Listening test + Reading test + Writing scenario + 2 Speaking scenarios.
          Generate always pulls content that no earlier pack has used — if a content pool runs dry
          it'll tell you which one to add more of instead of repeating a pack.
        </p>

        <button
          onClick={generate}
          disabled={generating}
          className="mb-8 px-5 py-2 bg-[#0F2356] text-white rounded-lg text-sm font-semibold disabled:opacity-50"
        >
          {generating ? 'Generating…' : `Generate Mock Test ${rows.length + 1}`}
        </button>

        {loading ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center text-gray-500">Loading...</div>
        ) : rows.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-lg p-12 text-center text-gray-500">
            No mock test packs yet. Click Generate to build the first one.
          </div>
        ) : (
          <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Pack</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Listening</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Reading</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Writing</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Speaking</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Created</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.map((p) => (
                    <tr key={p.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm font-semibold text-gray-800">{p.label}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{p.listening_title || '—'}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{p.reading_title || '—'}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{p.writing_title || '—'}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {p.speaking_title_1 || '—'} / {p.speaking_title_2 || '—'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">{formatTimestamp(p.created_at)}</td>
                      <td className="px-4 py-3 text-sm">
                        <button
                          onClick={() => toggleActive(p)}
                          className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            p.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                          }`}
                        >
                          {p.is_active ? 'Active' : 'Inactive'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="mt-6">
          <button onClick={() => router.push('/admin')} className="text-sm text-blue-600 font-semibold hover:underline">
            ← Back to Admin Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}
