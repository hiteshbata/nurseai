'use client'

import { Fragment, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { useAdminUser } from '@/app/admin/AdminShell'
import { ValidationErrorPanel, extractValidationResult, type ValidationResult } from '@/app/admin/ValidationErrors'

// RC4.1: cutting a new Mock Test Version is owner-only (require_owner).
const ROLE_RANK: Record<string, number> = { user: 0, support: 1, analyst: 2, admin: 3, owner: 4 }

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
  current_version: number | null  // RC4.1: highest published Mock Test Version, null if generation's own version failed
}

// RC4.3.2.3: Version History (read-only) shapes -- match GET .../versions and
// .../versions/{id} exactly as returned by assessment_versioning.py.
interface VersionSummary {
  id: number
  version: number
  published_at: string | null
  published_by: string | null
  // RC4.3.2.3: human-readable identity resolved server-side from the public.users
  // mirror (never the raw UUID above) -- null only when published_by itself is null.
  published_by_display: string | null
  is_current: boolean
}
interface WritingScenarioSnapshot {
  scenario_id: number
  title: string
  setting: string | null
  nurse_card: unknown
  scoring_criteria: unknown
  key_points: unknown
  difficulty: string | null
  specialty: string | null
}
interface SpeakingScenarioSnapshot {
  scenario_id: number
  title: string
  setting: string | null
  nurse_card: unknown
  interlocutor_card: unknown
  scoring_criteria: unknown
  difficulty: string | null
  specialty: string | null
  voice_config: unknown
  patient_gender: string | null
  patient_age: number | null
}
// Reading/Listening are frozen as version-ID REFERENCES only (never copied
// content -- see assessment_versioning.build_mock_snapshot's docstring), so
// the snapshot literally has no title/body/questions for them to render.
interface MockSnapshot {
  mock_test_id: number
  label: string | null
  reading_test_version_id: number | null
  listening_test_version_id: number | null
  writing_scenario_snapshot: WritingScenarioSnapshot | null
  speaking_scenario_snapshot_1: SpeakingScenarioSnapshot | null
  speaking_scenario_snapshot_2: SpeakingScenarioSnapshot | null
}
interface VersionDetail {
  id: number
  mock_test_id: number
  version: number
  snapshot: MockSnapshot
  published_by: string | null
  published_by_display: string | null
  published_at: string | null
}

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function AdminMockTestsPage() {
  const router = useRouter()
  const { role: viewerRole } = useAdminUser()
  const canPublish = (ROLE_RANK[viewerRole || 'user'] || 0) >= ROLE_RANK.owner
  const [rows, setRows] = useState<MockTestPack[]>([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [publishingId, setPublishingId] = useState<number | null>(null)
  // RC4.2: structured 409 validation errors from a failed pack publish, by pack id.
  const [publishValidation, setPublishValidation] = useState<Record<number, ValidationResult>>({})

  // RC4.3.2.3: Version History modal -- read-only, no owner gate. historyPack
  // holds {id, label} for whichever pack's modal is open (null = closed).
  const [historyPack, setHistoryPack] = useState<{ id: number; label: string } | null>(null)
  const [historyVersions, setHistoryVersions] = useState<VersionSummary[] | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  // Drilled-in snapshot view, or null when showing the list.
  const [viewingVersion, setViewingVersion] = useState<VersionDetail | null>(null)
  const [viewingLoading, setViewingLoading] = useState(false)
  const [viewingError, setViewingError] = useState<string | null>(null)
  // Request-identity refs: each open/view call stamps its own id here. A
  // response only applies its setState if its id is still the latest one --
  // a slower earlier request (switch packs/versions quickly, or close mid-flight)
  // resolving after a newer one must not clobber the newer state.
  const historyReqId = useRef(0)
  const viewReqId = useRef(0)

  const fetchPacks = () => {
    api.get('/mock/admin/tests')
      .then((res) => {
        const packs: MockTestPack[] = res.data || []
        setRows(packs)
        // RC4.2: pull each pack's /preview validation in the background so the
        // panel shows what's blocking publish before an admin even clicks it --
        // same publishValidation state a failed publish attempt populates.
        packs.forEach((p) => {
          api.get(`/mock/admin/tests/${p.id}/preview`)
            .then((r) => { if (r.data?.validation) setPublishValidation((v) => ({ ...v, [p.id]: r.data.validation })) })
            .catch(() => {})
        })
      })
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

  // RC4.1: cuts a new immutable Mock Test Version for this pack, picking up
  // the latest published version of its Reading/Listening test and a fresh
  // snapshot of its Writing/Speaking content. Already-started attempts on
  // this pack keep whatever version they were pinned to -- only new attempts
  // pick up the one this creates.
  const publishVersion = async (p: MockTestPack) => {
    setPublishingId(p.id)
    try {
      const res = await api.post(`/mock/admin/tests/${p.id}/publish`)
      toast.success(`${p.label}: published Version ${res.data.version}`)
      setPublishValidation((v) => { const { [p.id]: _drop, ...rest } = v; return rest })
      fetchPacks()
    } catch (error: any) {
      const validation = extractValidationResult(error)
      if (validation) {
        setPublishValidation((v) => ({ ...v, [p.id]: validation }))
      } else {
        toast.error(error.response?.data?.detail || 'Failed to publish a new version')
      }
    } finally {
      setPublishingId(null)
    }
  }

  // ── Version History (RC4.3.2.3) -- read-only, additive only ──
  const openVersionHistory = (id: number, label: string) => {
    const reqId = ++historyReqId.current
    setHistoryPack({ id, label })
    setHistoryVersions(null)
    setHistoryError(null)
    setViewingVersion(null)
    setViewingError(null)
    setHistoryLoading(true)
    api.get(`/mock/admin/tests/${id}/versions`)
      .then((res) => { if (historyReqId.current === reqId) setHistoryVersions(res.data?.versions || []) })
      .catch((e: any) => { if (historyReqId.current === reqId) setHistoryError(e?.response?.data?.detail || 'Failed to load version history') })
      .finally(() => { if (historyReqId.current === reqId) setHistoryLoading(false) })
  }

  const closeVersionHistory = () => {
    historyReqId.current++ // invalidate any outstanding history-list request
    viewReqId.current++    // invalidate any outstanding version-detail request
    setHistoryPack(null)
    setHistoryVersions(null)
    setHistoryError(null)
    setHistoryLoading(false)
    setViewingVersion(null)
    setViewingError(null)
    setViewingLoading(false)
  }

  const viewVersion = (versionId: number) => {
    if (!historyPack) return
    const reqId = ++viewReqId.current
    setViewingVersion(null)
    setViewingError(null)
    setViewingLoading(true)
    api.get(`/mock/admin/tests/${historyPack.id}/versions/${versionId}`)
      .then((res) => { if (viewReqId.current === reqId) setViewingVersion(res.data) })
      .catch((e: any) => { if (viewReqId.current === reqId) setViewingError(e?.response?.data?.detail || 'Failed to load this version') })
      .finally(() => { if (viewReqId.current === reqId) setViewingLoading(false) })
  }

  const backToVersionList = () => {
    viewReqId.current++ // invalidate any outstanding version-detail request
    setViewingVersion(null)
    setViewingError(null)
    setViewingLoading(false)
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
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Version</th>
                    <th className="px-4 py-3 text-left text-sm font-semibold text-gray-600">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.map((p) => (
                    <Fragment key={p.id}>
                    <tr className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm font-semibold text-gray-800">{p.label}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{p.listening_title || '—'}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{p.reading_title || '—'}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{p.writing_title || '—'}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {p.speaking_title_1 || '—'} / {p.speaking_title_2 || '—'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">{formatTimestamp(p.created_at)}</td>
                      <td className="px-4 py-3 text-sm whitespace-nowrap">
                        {p.current_version != null ? (
                          <span title="Published version -- learners who already started an attempt keep this exact content forever" className="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-semibold">
                            v{p.current_version}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-400">unpublished</span>
                        )}
                        <button
                          onClick={() => publishVersion(p)}
                          disabled={publishingId === p.id || !canPublish}
                          title={canPublish ? "Cut a new immutable version from this pack's current Reading/Listening/Writing/Speaking content" : 'Owner role required to publish'}
                          className="ml-2 text-xs text-blue-600 font-semibold hover:underline disabled:opacity-50"
                        >
                          {publishingId === p.id ? 'Publishing…' : 'Publish new version'}
                        </button>
                        <button
                          onClick={() => openVersionHistory(p.id, p.label)}
                          className="ml-2 text-xs text-gray-600 font-semibold hover:underline"
                        >
                          Version History
                        </button>
                      </td>
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
                    {publishValidation[p.id] && (
                      <tr>
                        <td colSpan={8} className="px-4 pb-3">
                          <ValidationErrorPanel
                            result={publishValidation[p.id]}
                            onDismiss={() => setPublishValidation((v) => { const { [p.id]: _drop, ...rest } = v; return rest })}
                          />
                        </td>
                      </tr>
                    )}
                    </Fragment>
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

      {/* RC4.3.2.3: Version History modal -- strictly read-only, additive only.
          List view when viewingVersion is null, drilled-in snapshot view otherwise. */}
      {historyPack && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={closeVersionHistory}>
          <div
            className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {viewingVersion || viewingLoading || viewingError ? (
              <MockVersionSnapshotView
                packLabel={historyPack.label}
                detail={viewingVersion}
                loading={viewingLoading}
                error={viewingError}
                onBack={backToVersionList}
                onClose={closeVersionHistory}
              />
            ) : (
              <MockVersionHistoryList
                packLabel={historyPack.label}
                versions={historyVersions}
                loading={historyLoading}
                error={historyError}
                onView={viewVersion}
                onClose={closeVersionHistory}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Version History list panel ──
function MockVersionHistoryList({
  packLabel, versions, loading, error, onView, onClose,
}: {
  packLabel: string
  versions: VersionSummary[] | null
  loading: boolean
  error: string | null
  onView: (versionId: number) => void
  onClose: () => void
}) {
  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-1">
        <h2 className="font-bold text-lg">Version History</h2>
        <button onClick={onClose} className="text-sm text-muted-foreground hover:text-gray-600">Close</button>
      </div>
      <p className="text-sm text-gray-500 mb-4 truncate">{packLabel}</p>

      {loading && <p className="text-muted-foreground text-sm py-4">Loading version history…</p>}

      {!loading && error && (
        <p className="text-red-600 text-sm py-4">{error}</p>
      )}

      {!loading && !error && versions && versions.length === 0 && (
        <p className="text-muted-foreground text-sm py-4">No published versions yet — this pack has never been published.</p>
      )}

      {!loading && !error && versions && versions.length > 0 && (
        <div className="space-y-2">
          {versions.map((v) => (
            <div key={v.id} className="flex items-center justify-between gap-3 border rounded-lg p-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">v{v.version}</span>
                  {v.is_current && (
                    <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-emerald-100 text-emerald-700">Current</span>
                  )}
                </div>
                <p className="text-xs text-gray-500 truncate">
                  {v.published_at ? new Date(v.published_at).toLocaleString() : 'Unknown date'}
                  {' · by '}{v.published_by_display || '—'}
                </p>
              </div>
              <button onClick={() => onView(v.id)}
                className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-700 shrink-0">
                View
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Version snapshot detail panel (immutable, read-only) ──
// Mock-specific: Reading/Listening are frozen as version-ID REFERENCES only
// (never copied content), Writing/Speaking as full embedded scenario
// snapshots -- cannot reuse Reading's or Listening's renderer.
function MockVersionSnapshotView({
  packLabel, detail, loading, error, onBack, onClose,
}: {
  packLabel: string
  detail: VersionDetail | null
  loading: boolean
  error: string | null
  onBack: () => void
  onClose: () => void
}) {
  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <button onClick={onBack} className="text-sm text-blue-600 hover:underline font-semibold">← Back</button>
          <h2 className="font-bold text-lg">
            {detail ? `v${detail.version}` : 'Version'}
          </h2>
        </div>
        <button onClick={onClose} className="text-sm text-muted-foreground hover:text-gray-600">Close</button>
      </div>
      <p className="text-sm text-gray-500 mb-4 truncate">{packLabel}</p>

      {loading && <p className="text-muted-foreground text-sm py-4">Loading version…</p>}
      {!loading && error && <p className="text-red-600 text-sm py-4">{error}</p>}

      {!loading && !error && detail && (
        <>
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs font-semibold">
            🔒 Historical snapshot — read-only and cannot be edited, saved, or published.
          </div>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm mb-4">
            <dt className="text-gray-500">Pack label</dt>
            <dd className="font-medium truncate">{detail.snapshot?.label ?? '—'}</dd>
            <dt className="text-gray-500">Version</dt>
            <dd className="font-medium">v{detail.version}</dd>
            <dt className="text-gray-500">Published</dt>
            <dd className="font-medium">{detail.published_at ? new Date(detail.published_at).toLocaleString() : '—'}</dd>
            <dt className="text-gray-500">Published by</dt>
            <dd className="font-medium">{detail.published_by_display || '—'}</dd>
          </dl>

          {/* Reading/Listening: this snapshot stores only a reference to the OTHER
              module's own immutable version -- never a copy of its content. Shown
              exactly as stored, not resolved against live or even that other
              version's data, per the frozen-reference architecture. */}
          <div className="mb-4">
            <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Reading &amp; Listening</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="border rounded-lg p-3 bg-gray-50 text-xs">
                <p className="font-medium text-gray-800">Reading</p>
                {detail.snapshot?.reading_test_version_id != null ? (
                  <p className="text-gray-600">References Reading Test Version #{detail.snapshot.reading_test_version_id}</p>
                ) : (
                  <p className="text-amber-600">No Reading version referenced in this snapshot.</p>
                )}
                <p className="text-gray-400 mt-1">(Reading's own version history has the full frozen content.)</p>
              </div>
              <div className="border rounded-lg p-3 bg-gray-50 text-xs">
                <p className="font-medium text-gray-800">Listening</p>
                {detail.snapshot?.listening_test_version_id != null ? (
                  <p className="text-gray-600">References Listening Test Version #{detail.snapshot.listening_test_version_id}</p>
                ) : (
                  <p className="text-amber-600">No Listening version referenced in this snapshot.</p>
                )}
                <p className="text-gray-400 mt-1">(Listening's own version history has the full frozen content.)</p>
              </div>
            </div>
          </div>

          <MockScenarioSnapshotCard title="Writing" scenario={detail.snapshot?.writing_scenario_snapshot ?? null} />
          <MockScenarioSnapshotCard title="Speaking (role play 1)" scenario={detail.snapshot?.speaking_scenario_snapshot_1 ?? null} />
          <MockScenarioSnapshotCard title="Speaking (role play 2)" scenario={detail.snapshot?.speaking_scenario_snapshot_2 ?? null} />
        </>
      )}
    </div>
  )
}

// One frozen Writing/Speaking scenario snapshot -- embedded content, not a
// reference, so its actual fields are shown (title/difficulty/specialty
// plainly; the richer JSON fields behind a details toggle since neither has
// an established flat-field renderer elsewhere in the admin UI).
function MockScenarioSnapshotCard({
  title, scenario,
}: {
  title: string
  scenario: (WritingScenarioSnapshot | SpeakingScenarioSnapshot) | null
}) {
  return (
    <div className="mb-4 last:mb-0">
      <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">{title}</p>
      {!scenario ? (
        <p className="text-muted-foreground text-xs">No {title.toLowerCase()} scenario recorded in this snapshot.</p>
      ) : (
        <div className="border rounded-lg p-3 bg-gray-50 text-xs space-y-1">
          <p className="font-medium text-gray-800">{scenario.title || '(untitled)'}</p>
          <p className="text-gray-500">
            {scenario.difficulty || '—'} · {scenario.specialty || '—'}
            {scenario.setting ? ` · ${scenario.setting}` : ''}
          </p>
          <details>
            <summary className="cursor-pointer text-gray-600 font-semibold">Full scenario content</summary>
            <pre className="mt-1 max-h-40 overflow-y-auto border rounded bg-white p-2 text-gray-700 whitespace-pre-wrap">
              {JSON.stringify(scenario, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  )
}
