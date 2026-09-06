'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import api from '@/lib/api'

interface SessionRow {
  id: number
  user_id: string | null
  scenario_id: number | null
  created_at: string | null
}

export default function SpeakingEvidenceListPage() {
  const [realtime, setRealtime] = useState<SessionRow[]>([])
  const [legacy, setLegacy] = useState<SessionRow[]>([])
  const [userId, setUserId] = useState('')
  const [scenarioId, setScenarioId] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    const params: Record<string, string> = {}
    if (userId.trim()) params.user_id = userId.trim()
    if (scenarioId.trim()) params.scenario_id = scenarioId.trim()
    return api.get('/admin/speaking-evidence/sessions', { params })
      .then((res) => {
        setRealtime(res.data.realtime || [])
        setLegacy(res.data.legacy || [])
      })
      .finally(() => setLoading(false))
  }, [userId, scenarioId])

  useEffect(() => { load() }, [load])

  const Table = ({ pipeline, rows }: { pipeline: 'realtime' | 'legacy'; rows: SessionRow[] }) => (
    <div className="bg-white rounded-lg shadow p-4 mb-6">
      <h2 className="text-lg font-semibold mb-3 capitalize">{pipeline} sessions</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-gray-500">No sessions found.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="py-1 pr-4">Session ID</th>
              <th className="py-1 pr-4">User</th>
              <th className="py-1 pr-4">Scenario</th>
              <th className="py-1 pr-4">Created</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b last:border-0">
                <td className="py-1 pr-4">{r.id}</td>
                <td className="py-1 pr-4">{r.user_id || 'Not available'}</td>
                <td className="py-1 pr-4">{r.scenario_id ?? 'Not available'}</td>
                <td className="py-1 pr-4">{r.created_at || 'Not available'}</td>
                <td className="py-1">
                  <Link
                    href={`/admin/speaking-evidence/${pipeline}/${r.id}`}
                    className="text-blue-600 hover:underline"
                  >
                    Inspect
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">Speaking Evidence Inspector</h1>
      <p className="text-sm text-gray-500 mb-4">
        QA tool for verifying the Evidence Layer against real conversations. Not connected to scoring.
      </p>

      <div className="bg-white rounded-lg shadow p-4 mb-6 flex flex-wrap gap-3 items-end">
        <div>
          <label className="block text-xs text-gray-500 mb-1">User ID</label>
          <input
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            className="border rounded px-2 py-1 text-sm"
            placeholder="uuid"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Scenario ID</label>
          <input
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
            className="border rounded px-2 py-1 text-sm w-24"
          />
        </div>
        <button
          onClick={load}
          className="bg-blue-600 text-white text-sm px-3 py-1.5 rounded hover:bg-blue-700"
        >
          Filter
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-gray-500">Loading...</p>
      ) : (
        <>
          <Table pipeline="realtime" rows={realtime} />
          <Table pipeline="legacy" rows={legacy} />
        </>
      )}
    </div>
  )
}
