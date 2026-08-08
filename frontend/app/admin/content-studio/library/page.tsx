'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface ContentItem {
  content_id: string
  id: number
  module: string
  title: string
  status: string
  difficulty: string | null
  updated_at: string
}

const PAGE_SIZE = 50

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking',
  writing: 'Writing',
  reading: 'Reading',
  listening: 'Listening',
}

// Raw values as they exist in the DB today (see docs/CONTENT_FOUNDATION.md
// S:4) -- not the proposed 5-tier ladder, which isn't applied to any row
// yet. Filtering on ladder values here would silently return zero rows.
const DIFFICULTY_VALUES = ['easy', 'medium', 'hard', 'intermediate', 'advanced']

export default function ContentLibraryPage() {
  const router = useRouter()
  const [items, setItems] = useState<ContentItem[]>([])
  const [total, setTotal] = useState(0)
  const [module, setModule] = useState('')
  const [status, setStatus] = useState('')
  const [difficulty, setDifficulty] = useState('')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const timer = setTimeout(() => fetchItems(), 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [module, status, difficulty, search, offset])

  const fetchItems = async () => {
    setLoading(true)
    try {
      const res = await api.get('/admin/content-studio/items', {
        params: {
          module: module || undefined,
          status: status || undefined,
          difficulty: difficulty || undefined,
          search: search || undefined,
          limit: PAGE_SIZE,
          offset,
        },
      })
      setItems(res.data.items)
      setTotal(res.data.total)
    } finally {
      setLoading(false)
    }
  }

  const resetAndSet = (setter: (v: string) => void) => (v: string) => {
    setter(v)
    setOffset(0)
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">Content Library</h1>

        <div className="flex flex-wrap gap-3 mb-6">
          <input
            type="text"
            value={search}
            onChange={(e) => resetAndSet(setSearch)(e.target.value)}
            placeholder="Search by title or Content ID..."
            aria-label="Search content"
            className="w-72 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <select
            value={module}
            onChange={(e) => resetAndSet(setModule)(e.target.value)}
            aria-label="Filter by module"
            className="px-3 py-2 border rounded-lg"
          >
            <option value="">All Modules</option>
            {Object.entries(MODULE_LABELS).map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>
          <select
            value={status}
            onChange={(e) => resetAndSet(setStatus)(e.target.value)}
            aria-label="Filter by status"
            className="px-3 py-2 border rounded-lg"
          >
            <option value="">All Statuses</option>
            <option value="Published">Published</option>
            <option value="Unpublished">Unpublished</option>
          </select>
          <select
            value={difficulty}
            onChange={(e) => resetAndSet(setDifficulty)(e.target.value)}
            aria-label="Filter by difficulty"
            className="px-3 py-2 border rounded-lg"
          >
            <option value="">All Difficulties</option>
            {DIFFICULTY_VALUES.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </div>

        <div className="bg-white rounded-lg shadow overflow-hidden">
          {/* Wide table (6 cols) doesn't fit a mobile viewport -- scrolling
              lives here, not on the page body (see Playwright responsive check). */}
          <div className="overflow-x-auto" data-testid="content-table">
          <table className="w-full min-w-[720px]">
            <thead className="bg-gray-100">
              <tr>
                <th className="text-left py-4 px-4">Content ID</th>
                <th className="text-left py-4 px-4">Title</th>
                <th className="text-left py-4 px-4">Module</th>
                <th className="text-left py-4 px-4">Difficulty</th>
                <th className="text-left py-4 px-4">Status</th>
                <th className="text-left py-4 px-4">Updated</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.content_id}
                  data-testid={`content-row-${item.content_id}`}
                  className="border-t cursor-pointer hover:bg-gray-50"
                  onClick={() => router.push(`/admin/content-studio/${item.module}/${item.id}`)}
                >
                  <td className="py-4 px-4 font-mono text-sm">{item.content_id}</td>
                  <td className="py-4 px-4">{item.title}</td>
                  <td className="py-4 px-4" data-testid="cell-module">{MODULE_LABELS[item.module] || item.module}</td>
                  <td className="py-4 px-4" data-testid="cell-difficulty">{item.difficulty || '—'}</td>
                  <td className="py-4 px-4" data-testid="cell-status">
                    <span className={`px-2 py-1 rounded text-xs font-semibold ${
                      item.status === 'Published' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                    }`}>
                      {item.status}
                    </span>
                  </td>
                  <td className="py-4 px-4 text-sm text-gray-500">
                    {new Date(item.updated_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>

          {!loading && items.length === 0 && (
            <div className="p-8 text-center text-gray-500">No content items match these filters.</div>
          )}
          {loading && <div className="p-8 text-center text-gray-500">Loading...</div>}
        </div>

        {total > PAGE_SIZE && (
          <div data-testid="pagination" className="flex justify-between items-center mt-4 text-sm text-gray-600">
            <span>Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}</span>
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
