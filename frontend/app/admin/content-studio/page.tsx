'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import api from '@/lib/api'

interface ModuleSummary {
  total: number
  published: number
  unpublished: number
}

interface Summary {
  total: number
  published: number
  unpublished: number
  modules: Record<string, ModuleSummary>
}

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking',
  writing: 'Writing',
  reading: 'Reading',
  listening: 'Listening',
}

// Neither table is admin-authored content yet (vocab_cards is a per-user SRS
// deck, Grammar has no table at all) -- static facts, not fetched/fabricated
// zero-data. See docs/CONTENT_FOUNDATION.md S:1/S:2.
const COMING_SOON_MODULES = ['Vocabulary', 'Grammar']

export default function ContentStudioDashboard() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/admin/content-studio/summary')
      .then((res) => setSummary(res.data))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">Content Studio</h1>
          <Link
            href="/admin/content-studio/library"
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700"
          >
            Open Library
          </Link>
        </div>

        {loading && <div className="text-gray-500">Loading...</div>}

        {summary && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
              <StatCard testId="stat-total-content" label="Total Content" value={summary.total} />
              <StatCard testId="stat-published" label="Published" value={summary.published} tone="green" />
              <StatCard testId="stat-unpublished" label="Unpublished" value={summary.unpublished} tone="gray" />
            </div>

            <h2 className="text-lg font-semibold mb-3">By Module</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Object.entries(summary.modules).map(([module, m]) => (
                <div key={module} data-testid={`module-card-${module}`} className="bg-white rounded-lg shadow p-5">
                  <div className="font-semibold mb-3">{MODULE_LABELS[module] || module}</div>
                  <div className="flex justify-between text-sm text-gray-600 mb-1">
                    <span>Total</span><span className="font-medium text-gray-900">{m.total}</span>
                  </div>
                  <div className="flex justify-between text-sm text-gray-600 mb-1">
                    <span>Published</span><span className="font-medium text-green-700">{m.published}</span>
                  </div>
                  <div className="flex justify-between text-sm text-gray-600">
                    <span>Unpublished</span><span className="font-medium text-gray-500">{m.unpublished}</span>
                  </div>
                </div>
              ))}

              {COMING_SOON_MODULES.map((label) => (
                <div key={label} data-testid={`module-card-${label.toLowerCase()}`} className="bg-white rounded-lg shadow p-5 opacity-60">
                  <div className="font-semibold mb-3">{label}</div>
                  <div className="text-sm text-gray-500">Coming Soon</div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value, tone, testId }: { label: string; value: number; tone?: 'green' | 'gray'; testId: string }) {
  const color = tone === 'green' ? 'text-green-700' : tone === 'gray' ? 'text-gray-500' : 'text-gray-900'
  return (
    <div data-testid={testId} className="bg-white rounded-lg shadow p-6">
      <div className="text-sm text-gray-500 mb-1">{label}</div>
      <div className={`text-3xl font-bold ${color}`}>{value}</div>
    </div>
  )
}
