'use client'

import { useEffect, useState } from 'react'
import api from '@/lib/api'
import toast from 'react-hot-toast'

interface Draft {
  key: string // client-side only, keys the review card -- never sent to the API
  title: string
  difficulty: string
  case_notes: string
  task: string
  key_points: string[]
}

interface ScenarioRow {
  id: number
  title: string
  difficulty: string
  is_active: boolean
}

// FastAPI 422 returns `detail` as an array of objects; collapse to a string so
// toast.error() never tries to render an object as a React child.
function errorMessage(e: any, fallback: string): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d?.msg || JSON.stringify(d)).join('; ')
  return fallback
}

export default function AdminWritingPage() {
  const [rows, setRows] = useState<ScenarioRow[]>([])
  // Multiple task PDFs get extracted one at a time and reviewed as separate cards.
  const [files, setFiles] = useState<File[]>([])
  const [extracting, setExtracting] = useState(false)
  const [extractProgress, setExtractProgress] = useState<{ done: number; total: number } | null>(null)
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set())
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const fetchRows = async () => {
    try {
      const res = await api.get('/admin/scenarios', { params: { module: 'writing' } })
      setRows(res.data || [])
      setSelected(new Set())
    } catch {
      // non-fatal: the list is a convenience, extraction still works without it
    }
  }

  useEffect(() => {
    fetchRows()
  }, [])

  const handleExtract = async () => {
    if (files.length === 0) {
      toast.error('Choose at least one PDF first')
      return
    }
    setExtracting(true)
    setExtractProgress({ done: 0, total: files.length })
    try {
      // One extraction call per file, run in sequence -- each PDF gets its own
      // OCR + AI call, and each becomes its own review card below.
      const newDrafts: Draft[] = []
      const failed: string[] = []
      for (let i = 0; i < files.length; i++) {
        const f = files[i]
        try {
          const form = new FormData()
          form.append('file', f)
          const res = await api.post('/writing/admin/extract', form, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
          const d = res.data
          newDrafts.push({
            key: crypto.randomUUID(),
            title: d.title || '',
            difficulty: d.difficulty || 'medium',
            case_notes: d.case_notes || '',
            task: d.task || '',
            key_points: (d.key_points && d.key_points.length ? d.key_points : ['']) as string[],
          })
        } catch (e: any) {
          failed.push(`${f.name}: ${errorMessage(e, 'extraction failed')}`)
        }
        setExtractProgress({ done: i + 1, total: files.length })
      }

      if (newDrafts.length === 0) {
        toast.error(failed[0] || 'Extraction failed')
        return
      }
      setDrafts((prev) => [...prev, ...newDrafts])
      setFiles([])
      if (failed.length) toast.error(`${failed.length} of ${files.length} file(s) failed: ${failed.join('; ')}`)
      toast.success(`Extracted ${newDrafts.length} task${newDrafts.length === 1 ? '' : 's'} — review each before saving`)
    } finally {
      setExtracting(false)
      setExtractProgress(null)
    }
  }

  const updateDraft = (key: string, patch: Partial<Draft>) =>
    setDrafts((prev) => prev.map((d) => (d.key === key ? { ...d, ...patch } : d)))

  const discardDraft = (key: string) => setDrafts((prev) => prev.filter((d) => d.key !== key))

  const saveDraft = async (key: string) => {
    const draft = drafts.find((d) => d.key === key)
    if (!draft) return
    if (!draft.title.trim() || !draft.case_notes.trim() || !draft.task.trim()) {
      toast.error('Title, case notes and task are all required')
      return
    }
    setSavingKeys((s) => new Set(s).add(key))
    try {
      await api.post('/admin/scenarios', {
        module: 'writing',
        title: draft.title.trim(),
        setting: draft.case_notes.trim(),
        difficulty: draft.difficulty,
        nurse_card: {
          role: draft.task.trim(),
          tasks: draft.key_points.map((k) => k.trim()).filter(Boolean),
        },
      })
      toast.success('Writing scenario saved')
      discardDraft(key)
      fetchRows()
    } catch (e: any) {
      toast.error(errorMessage(e, 'Save failed'))
    } finally {
      setSavingKeys((s) => {
        const next = new Set(s)
        next.delete(key)
        return next
      })
    }
  }

  const setKeyPoint = (key: string, idx: number, value: string) => {
    const draft = drafts.find((d) => d.key === key)
    if (!draft) return
    const kp = [...draft.key_points]
    kp[idx] = value
    updateDraft(key, { key_points: kp })
  }

  const toggleActive = async (r: ScenarioRow) => {
    try {
      await api.put(`/admin/scenarios/${r.id}`, { is_active: !r.is_active })
      toast.success(r.is_active ? 'Unpublished' : 'Now live')
      fetchRows()
    } catch (e: any) {
      toast.error(errorMessage(e, 'Update failed'))
    }
  }

  const deleteScenario = async (r: ScenarioRow) => {
    if (!confirm(`Delete "${r.title}"? This cannot be undone (scenarios with practice history are kept as inactive instead).`)) return
    try {
      const res = await api.delete(`/admin/scenarios/${r.id}`, { params: { hard: true } })
      toast.success(res.data?.message || 'Deleted')
      fetchRows()
    } catch (e: any) {
      toast.error(errorMessage(e, 'Delete failed'))
    }
  }

  const toggleSelect = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const toggleSelectAll = () =>
    setSelected((prev) => (prev.size === rows.length ? new Set() : new Set(rows.map((r) => r.id))))

  const deleteSelected = async () => {
    const ids = [...selected]
    if (!ids.length) return
    if (!confirm(`Delete ${ids.length} scenario${ids.length === 1 ? '' : 's'}? This cannot be undone (any with practice history are kept as inactive instead).`)) return
    setBulkDeleting(true)
    try {
      const results = await Promise.allSettled(
        ids.map((id) => api.delete(`/admin/scenarios/${id}`, { params: { hard: true } })),
      )
      const failed = results.filter((r) => r.status === 'rejected').length
      if (failed) toast.error(`${failed} of ${ids.length} couldn't be deleted`)
      else toast.success(`Deleted ${ids.length} scenario${ids.length === 1 ? '' : 's'}`)
      fetchRows()
    } finally {
      setBulkDeleting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Writing Scenarios</h1>
          <p className="text-gray-500 mt-1">Upload real OET Writing task PDFs — the case notes and task are extracted for you to review, then save. Select multiple PDFs to extract them one by one.</p>
        </div>

        {/* Upload */}
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-bold mb-3">Upload OET Writing PDF(s)</h2>
          <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
            <input
              type="file"
              accept="application/pdf"
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              className="block text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 file:font-semibold hover:file:bg-blue-100"
            />
            <button
              onClick={handleExtract}
              disabled={extracting || files.length === 0}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition disabled:opacity-50 whitespace-nowrap"
            >
              {extracting
                ? `Extracting…${extractProgress ? ` (${extractProgress.done}/${extractProgress.total})` : ''}`
                : files.length > 1 ? `Extract ${files.length} PDFs` : 'Extract'}
            </button>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            {files.length > 1 ? `${files.length} files selected. ` : ''}
            PDF up to 10MB each. Extraction reads the pages with OCR and can take up to a minute per file.
          </p>
        </div>

        {/* Review drafts */}
        {drafts.map((draft) => (
          <div key={draft.key} className="bg-white p-6 rounded-xl shadow space-y-5">
            <h2 className="text-lg font-bold">Review before saving</h2>

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor={`draftTitle-${draft.key}`} className="block text-sm font-semibold text-gray-700 mb-1">Title</label>
                <input
                  id={`draftTitle-${draft.key}`}
                  value={draft.title}
                  onChange={(e) => updateDraft(draft.key, { title: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                />
              </div>
              <div>
                <label htmlFor={`draftDifficulty-${draft.key}`} className="block text-sm font-semibold text-gray-700 mb-1">Difficulty</label>
                <select
                  id={`draftDifficulty-${draft.key}`}
                  value={draft.difficulty}
                  onChange={(e) => updateDraft(draft.key, { difficulty: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                >
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </div>
            </div>

            <div>
              <label htmlFor={`draftCaseNotes-${draft.key}`} className="block text-sm font-semibold text-gray-700 mb-1">Case notes (what the student reads)</label>
              <textarea
                id={`draftCaseNotes-${draft.key}`}
                value={draft.case_notes}
                onChange={(e) => updateDraft(draft.key, { case_notes: e.target.value })}
                rows={16}
                className="w-full px-3 py-2 border rounded-lg font-mono text-sm whitespace-pre"
              />
            </div>

            <div>
              <label htmlFor={`draftTask-${draft.key}`} className="block text-sm font-semibold text-gray-700 mb-1">Writing task (recipient + what to write + word count)</label>
              <textarea
                id={`draftTask-${draft.key}`}
                value={draft.task}
                onChange={(e) => updateDraft(draft.key, { task: e.target.value })}
                rows={4}
                className="w-full px-3 py-2 border rounded-lg text-sm"
              />
            </div>

            <div>
              <span id={`draftKeyPoints-${draft.key}`} className="block text-sm font-semibold text-gray-700 mb-1">
                Key points for scoring <span className="font-normal text-muted-foreground">(not shown to the student)</span>
              </span>
              <div role="group" aria-labelledby={`draftKeyPoints-${draft.key}`}>
                {draft.key_points.map((kp, idx) => (
                  <input
                    key={idx}
                    value={kp}
                    onChange={(e) => setKeyPoint(draft.key, idx, e.target.value)}
                    className="w-full px-3 py-2 border rounded-lg mb-2 text-sm"
                    placeholder={`Key point ${idx + 1}`}
                  />
                ))}
                <button
                  type="button"
                  onClick={() => updateDraft(draft.key, { key_points: [...draft.key_points, ''] })}
                  className="text-blue-600 text-sm font-semibold"
                >
                  + Add key point
                </button>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => saveDraft(draft.key)}
                disabled={savingKeys.has(draft.key)}
                className="px-6 py-2 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-700 transition disabled:opacity-50"
              >
                {savingKeys.has(draft.key) ? 'Saving…' : 'Save scenario'}
              </button>
              <button
                onClick={() => discardDraft(draft.key)}
                className="px-6 py-2 border border-gray-300 text-gray-600 rounded-lg font-semibold hover:bg-gray-50 transition"
              >
                Discard
              </button>
            </div>
          </div>
        ))}

        {/* Existing scenarios */}
        <div className="bg-white p-6 rounded-xl shadow">
          <div className="flex items-center justify-between mb-3 gap-4">
            <h2 className="text-lg font-bold">Existing writing scenarios ({rows.length})</h2>
            {selected.size > 0 && (
              <button
                onClick={deleteSelected}
                disabled={bulkDeleting}
                className="text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg px-4 py-2 transition disabled:opacity-50"
              >
                {bulkDeleting ? 'Deleting…' : `Delete ${selected.size} selected`}
              </button>
            )}
          </div>
          {rows.length === 0 ? (
            <p className="text-muted-foreground text-sm">None yet — extract one above.</p>
          ) : (
            <ul className="divide-y">
              <li className="py-2 flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={selected.size === rows.length && rows.length > 0}
                  onChange={toggleSelectAll}
                  className="h-4 w-4"
                  aria-label="Select all"
                />
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Select all</span>
              </li>
              {rows.map((r) => (
                <li key={r.id} className="py-3 flex items-center justify-between gap-4">
                  <span className="flex items-center gap-3 min-w-0">
                    <input
                      type="checkbox"
                      checked={selected.has(r.id)}
                      onChange={() => toggleSelect(r.id)}
                      className="h-4 w-4 shrink-0"
                      aria-label={`Select ${r.title}`}
                    />
                    <span className="font-medium text-gray-800 min-w-0 truncate">{r.title}</span>
                  </span>
                  <span className="flex items-center gap-2 shrink-0">
                    <span className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-600 capitalize">{r.difficulty}</span>
                    <span className={`text-xs px-2 py-1 rounded-full font-semibold ${r.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-200 text-gray-600'}`}>
                      {r.is_active ? 'Live' : 'Draft'}
                    </span>
                    <button
                      onClick={() => toggleActive(r)}
                      className="text-sm font-semibold text-blue-600 hover:text-blue-800 px-2"
                    >
                      {r.is_active ? 'Unpublish' : 'Go live'}
                    </button>
                    <button
                      onClick={() => deleteScenario(r)}
                      className="text-sm font-semibold text-red-600 hover:text-red-800 px-2"
                    >
                      Delete
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
