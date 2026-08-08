'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import api from '@/lib/api'

interface DraftListItem {
  id: number
  module: string
  draft_name: string
  ai_title: string | null
  status: string
  model_used: string | null
  validation_warnings: string[]
  created_at: string
  updated_at: string
  approved_at: string | null
  published_at: string | null
}

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking', reading: 'Reading', listening: 'Listening',
  writing: 'Writing', vocab: 'Vocabulary', grammar: 'Grammar',
}

const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  review: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-blue-100 text-blue-800',
  published: 'bg-green-100 text-green-800',
  archived: 'bg-red-100 text-red-700',
}

export default function DraftsListPage() {
  const [drafts, setDrafts] = useState<DraftListItem[]>([])
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.get('/admin/content-studio/drafts', { params: status ? { status } : {} })
      .then((res) => setDrafts(res.data.drafts || []))
      .finally(() => setLoading(false))
  }, [status])

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-5xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold">Drafts</h1>
          <Link href="/admin/content-studio/generate" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700">
            Generate New
          </Link>
        </div>

        <div className="mb-4">
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-3 py-2 border rounded-lg text-sm" data-testid="filter-status">
            <option value="">All statuses</option>
            {Object.keys(STATUS_STYLES).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {loading && <div className="text-gray-500">Loading...</div>}

        {!loading && drafts.length === 0 && (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">No drafts yet.</div>
        )}

        {!loading && drafts.length > 0 && (
          <div className="bg-white rounded-lg shadow divide-y">
            {drafts.map((d) => (
              <Link
                key={d.id}
                href={`/admin/content-studio/drafts/${d.id}`}
                className="flex items-center justify-between px-6 py-4 hover:bg-gray-50"
                data-testid="draft-row"
              >
                <div>
                  <div className="font-medium text-gray-900">{d.draft_name}</div>
                  <div className="text-xs text-gray-500">{MODULE_LABELS[d.module] || d.module} &middot; updated {new Date(d.updated_at).toLocaleString()}</div>
                </div>
                <span className={`px-3 py-1 rounded text-xs font-semibold capitalize ${STATUS_STYLES[d.status] || 'bg-gray-100 text-gray-700'}`}>
                  {d.status}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
