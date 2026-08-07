'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import api from '@/lib/api'
import toast from 'react-hot-toast'

interface AiModel {
  id: number
  provider: string
  model_name: string
  display_name: string
  api_base: string | null
  enabled: boolean
  is_default: boolean
  priority: number
  fallback_model_id: number | null
  last_health_status: string | null
  last_health_latency_ms: number | null
  last_health_checked_at: string | null
  last_health_error: string | null
  purposes: string[]
}

interface PurposeMapping {
  purpose: string
  model_id: number
  updated_at: string
  model: AiModel | null
}

interface HistoryEntry {
  id: string
  admin_email: string
  action: string
  detail: { before: any; after: any } | null
  created_at: string
}

interface TestResult {
  status: 'healthy' | 'warning' | 'failed'
  latency_ms: number | null
  error: string | null
}

const KNOWN_PROVIDERS = ['openai', 'openrouter', 'google', 'deepgram']

const HEALTH_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  healthy: { bg: 'bg-green-100', text: 'text-green-800', label: 'Healthy' },
  warning: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Warning' },
  failed: { bg: 'bg-red-100', text: 'text-red-800', label: 'Failed' },
  // Realtime voice / TTS / STT models aren't chat-completion models, so the
  // Test button can't ping them the same way -- this is not a failure.
  not_testable: { bg: 'bg-gray-100', text: 'text-gray-600', label: 'Not testable' },
}

function HealthPill({ status }: { status: string | null }) {
  if (!status) return <span className="text-xs text-gray-400">Not tested</span>
  const s = HEALTH_STYLE[status] || { bg: 'bg-gray-100', text: 'text-gray-600', label: status }
  return (
    <span className={`px-2 py-1 rounded text-xs font-semibold ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  )
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
}

// ── Model form (create/edit + Test Before Save) ──────────────────────

interface ModelFormState {
  provider: string
  model_name: string
  display_name: string
  api_base: string
  enabled: boolean
  is_default: boolean
  priority: number
  fallback_model_id: number | ''
}

const EMPTY_FORM: ModelFormState = {
  provider: 'openai',
  model_name: '',
  display_name: '',
  api_base: '',
  enabled: true,
  is_default: false,
  priority: 0,
  fallback_model_id: '',
}

function ModelFormModal({
  editing,
  models,
  onClose,
  onSaved,
}: {
  editing: AiModel | null
  models: AiModel[]
  onClose: () => void
  onSaved: () => void
}) {
  const [form, setForm] = useState<ModelFormState>(
    editing
      ? {
          provider: editing.provider,
          model_name: editing.model_name,
          display_name: editing.display_name,
          api_base: editing.api_base || '',
          enabled: editing.enabled,
          is_default: editing.is_default,
          priority: editing.priority,
          fallback_model_id: editing.fallback_model_id ?? '',
        }
      : EMPTY_FORM
  )
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)

  // Any change to what's actually being tested invalidates the last result --
  // the point of "Test Before Save" is testing what you're about to save.
  const updateForm = (patch: Partial<ModelFormState>) => {
    setForm((f) => ({ ...f, ...patch }))
    setTestResult(null)
  }

  const runTest = async () => {
    if (!form.provider || !form.model_name) {
      toast.error('Provider and model name are required to test')
      return
    }
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.post('/admin/ai-models/test-connection', {
        provider: form.provider,
        model_name: form.model_name,
        api_base: form.api_base || null,
      })
      setTestResult(res.data)
    } catch {
      setTestResult({ status: 'failed', latency_ms: null, error: 'Test request failed' })
    } finally {
      setTesting(false)
    }
  }

  const save = async () => {
    setSaving(true)
    const payload = {
      provider: form.provider,
      model_name: form.model_name,
      display_name: form.display_name || form.model_name,
      api_base: form.api_base || null,
      enabled: form.enabled,
      is_default: form.is_default,
      priority: Number(form.priority) || 0,
      fallback_model_id: form.fallback_model_id === '' ? null : Number(form.fallback_model_id),
    }
    try {
      if (editing) {
        await api.put(`/admin/ai-models/${editing.id}`, payload)
        toast.success('Model updated')
      } else {
        await api.post('/admin/ai-models', payload)
        toast.success('Model created')
      }
      onSaved()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Could not save model')
    } finally {
      setSaving(false)
    }
  }

  const otherModels = models.filter((m) => m.id !== editing?.id)

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-bold mb-4">{editing ? 'Edit Model' : 'Add Model'}</h2>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-semibold mb-1">Provider</label>
              <input
                list="known-providers"
                value={form.provider}
                onChange={(e) => updateForm({ provider: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg"
                placeholder="openai"
              />
              <datalist id="known-providers">
                {KNOWN_PROVIDERS.map((p) => <option key={p} value={p} />)}
              </datalist>
            </div>
            <div>
              <label className="block text-sm font-semibold mb-1">Model name</label>
              <input
                value={form.model_name}
                onChange={(e) => updateForm({ model_name: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg"
                placeholder="gemini-flash-latest"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-semibold mb-1">Display name</label>
            <input
              value={form.display_name}
              onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
              className="w-full px-3 py-2 border rounded-lg"
              placeholder="Gemini Flash Latest"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold mb-1">
              API base <span className="font-normal text-gray-400">(optional override)</span>
            </label>
            <input
              value={form.api_base}
              onChange={(e) => updateForm({ api_base: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg"
              placeholder="https://api.example.com/v1/chat/completions"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-semibold mb-1">Priority</label>
              <input
                type="number"
                value={form.priority}
                onChange={(e) => setForm((f) => ({ ...f, priority: Number(e.target.value) }))}
                className="w-full px-3 py-2 border rounded-lg"
              />
            </div>
            <div>
              <label className="block text-sm font-semibold mb-1">Fallback model</label>
              <select
                value={form.fallback_model_id}
                onChange={(e) => setForm((f) => ({ ...f, fallback_model_id: e.target.value === '' ? '' : Number(e.target.value) }))}
                className="w-full px-3 py-2 border rounded-lg"
              >
                <option value="">None</option>
                {otherModels.map((m) => (
                  <option key={m.id} value={m.id}>{m.display_name}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm font-semibold">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              />
              Enabled
            </label>
            <label className="flex items-center gap-2 text-sm font-semibold">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
              />
              Default
            </label>
          </div>

          {/* Test Before Save */}
          <div className="border rounded-lg p-4 bg-gray-50">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold">Provider: {form.provider || '—'}</span>
              <button
                onClick={runTest}
                disabled={testing}
                className="px-3 py-1.5 text-sm rounded-lg bg-slate-700 text-white hover:bg-slate-800 disabled:opacity-50"
              >
                {testing ? 'Testing…' : 'Test'}
              </button>
            </div>
            <p className="text-sm text-gray-500 mb-2">Model: {form.model_name || '—'}</p>
            {testResult && (
              <div className={`text-sm font-semibold ${
                testResult.status === 'healthy' ? 'text-green-700'
                  : testResult.status === 'warning' ? 'text-yellow-700' : 'text-red-700'
              }`}>
                {testResult.status === 'healthy' && '✓ Connection successful'}
                {testResult.status === 'warning' && `⚠ Connected, but slow (${testResult.latency_ms}ms)`}
                {testResult.status === 'failed' && `✗ ${testResult.error || 'Connection failed'}`}
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-gray-600 hover:bg-gray-100">
            Cancel
          </button>
          {testResult && testResult.status !== 'failed' ? (
            <button
              onClick={save}
              disabled={saving || !form.model_name}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          ) : (
            <button
              onClick={save}
              disabled={saving || !form.model_name}
              title="Test the connection first, or save anyway if you know what you're doing"
              className="px-4 py-2 rounded-lg border border-amber-400 text-amber-700 hover:bg-amber-50 disabled:opacity-50"
            >
              {saving ? 'Saving…' : testResult?.status === 'failed' ? 'Save anyway' : 'Save without testing'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── History panel (shared by models + purposes) ──────────────────────

function HistoryModal({
  title,
  fetchUrl,
  onClose,
  onRestored,
}: {
  title: string
  fetchUrl: string
  onClose: () => void
  onRestored: () => void
}) {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null)
  const [restoring, setRestoring] = useState<string | null>(null)

  useEffect(() => {
    api.get(fetchUrl).then((res) => setEntries(res.data)).catch(() => setEntries([]))
  }, [fetchUrl])

  const restore = async (id: string) => {
    setRestoring(id)
    try {
      await api.post(`/admin/ai-models/history/${id}/rollback`)
      toast.success('Restored')
      onRestored()
      onClose()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Could not restore')
    } finally {
      setRestoring(null)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-xl font-bold mb-4">History — {title}</h2>
        {entries === null && <p className="text-sm text-gray-400">Loading…</p>}
        {entries && entries.length === 0 && <p className="text-sm text-gray-400">No changes recorded yet.</p>}
        <div className="space-y-3">
          {entries?.map((e) => (
            <div key={e.id} className="border rounded-lg p-3 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-sm font-semibold capitalize">{e.action}</p>
                <p className="text-xs text-gray-500">{e.admin_email} · {formatTimestamp(e.created_at)}</p>
              </div>
              {e.action !== 'delete' && (
                <button
                  onClick={() => restore(e.id)}
                  disabled={restoring === e.id}
                  className="shrink-0 px-3 py-1.5 text-sm rounded-lg border border-blue-300 text-blue-700 hover:bg-blue-50 disabled:opacity-50"
                >
                  {restoring === e.id ? 'Restoring…' : 'Restore this version'}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────

export default function AiModelsPage() {
  const [models, setModels] = useState<AiModel[]>([])
  const [purposes, setPurposes] = useState<PurposeMapping[]>([])
  const [loading, setLoading] = useState(true)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [formOpen, setFormOpen] = useState<'new' | AiModel | null>(null)
  const [historyTarget, setHistoryTarget] = useState<{ title: string; url: string } | null>(null)
  const [newPurpose, setNewPurpose] = useState('')
  const [newPurposeModel, setNewPurposeModel] = useState<number | ''>('')

  const load = async () => {
    try {
      const [modelsRes, purposesRes] = await Promise.all([
        api.get('/admin/ai-models'),
        api.get('/admin/ai-models/purposes'),
      ])
      setModels(modelsRes.data)
      setPurposes(purposesRes.data)
    } catch {
      toast.error('Could not load AI models')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const toggleEnabled = async (m: AiModel) => {
    try {
      await api.put(`/admin/ai-models/${m.id}`, { enabled: !m.enabled })
      load()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Could not update model')
    }
  }

  const testModel = async (id: number) => {
    setTestingId(id)
    try {
      await api.post(`/admin/ai-models/${id}/test`)
      load()
    } catch {
      toast.error('Test failed to run')
    } finally {
      setTestingId(null)
    }
  }

  const deleteModel = async (m: AiModel) => {
    if (!confirm(`Delete "${m.display_name}"? This can't be undone from here.`)) return
    try {
      await api.delete(`/admin/ai-models/${m.id}`)
      toast.success('Model deleted')
      load()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Could not delete model')
    }
  }

  const savePurposeMapping = async (purpose: string, modelId: number) => {
    try {
      await api.put(`/admin/ai-models/purposes/${purpose}`, { model_id: modelId })
      toast.success(`${purpose} updated`)
      load()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Could not update mapping')
    }
  }

  const addPurpose = async () => {
    const key = newPurpose.trim()
    if (!key || newPurposeModel === '') {
      toast.error('Enter a purpose key and pick a model')
      return
    }
    await savePurposeMapping(key, Number(newPurposeModel))
    setNewPurpose('')
    setNewPurposeModel('')
  }

  const fallbackName = (id: number | null) => {
    if (id === null) return '—'
    return models.find((m) => m.id === id)?.display_name || `#${id}`
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading AI models…</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold">AI Models</h1>
            <p className="text-sm text-gray-500 mt-1">
              Which provider/model serves each feature — editable here, no deploy needed.{' '}
              <Link href="/admin/ai-costs" className="text-blue-600 hover:underline">View cost analytics →</Link>
            </p>
          </div>
          <button
            onClick={() => setFormOpen('new')}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          >
            + Add Model
          </button>
        </div>

        {/* Model registry */}
        <div className="bg-white rounded-lg shadow overflow-hidden mb-10">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-100">
                <tr>
                  <th className="text-left py-3 px-4">Provider</th>
                  <th className="text-left py-3 px-4">Model</th>
                  <th className="text-left py-3 px-4">Used by</th>
                  <th className="text-left py-3 px-4">Fallback</th>
                  <th className="text-left py-3 px-4">Priority</th>
                  <th className="text-left py-3 px-4">Enabled</th>
                  <th className="text-left py-3 px-4">Health</th>
                  <th className="text-left py-3 px-4">Actions</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.id} className="border-t">
                    <td className="py-3 px-4">
                      <span className="capitalize">{m.provider}</span>
                      {m.is_default && (
                        <span className="ml-2 px-1.5 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800">default</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <p className="font-semibold">{m.display_name}</p>
                      <p className="text-xs text-gray-400 font-mono">{m.model_name}</p>
                    </td>
                    <td className="py-3 px-4">
                      {m.purposes.length === 0
                        ? <span className="text-xs text-gray-400">unused</span>
                        : <span className="text-xs text-gray-500">{m.purposes.length} purpose{m.purposes.length > 1 ? 's' : ''}</span>}
                    </td>
                    <td className="py-3 px-4 text-xs text-gray-500">{fallbackName(m.fallback_model_id)}</td>
                    <td className="py-3 px-4">{m.priority}</td>
                    <td className="py-3 px-4">
                      <button
                        onClick={() => toggleEnabled(m)}
                        className={`px-3 py-1 rounded text-xs font-semibold ${
                          m.enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {m.enabled ? 'Enabled' : 'Disabled'}
                      </button>
                    </td>
                    <td className="py-3 px-4">
                      <HealthPill status={m.last_health_status} />
                      {m.last_health_checked_at && (
                        <p className="text-[10px] text-gray-400 mt-0.5">{formatTimestamp(m.last_health_checked_at)}</p>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex gap-2 flex-wrap">
                        <button
                          onClick={() => testModel(m.id)}
                          disabled={testingId === m.id}
                          className="px-2 py-1 text-xs rounded bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50"
                        >
                          {testingId === m.id ? 'Testing…' : 'Test'}
                        </button>
                        <button
                          onClick={() => setFormOpen(m)}
                          className="px-2 py-1 text-xs rounded bg-blue-100 text-blue-800 hover:bg-blue-200"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => setHistoryTarget({ title: m.display_name, url: `/admin/ai-models/${m.id}/history` })}
                          className="px-2 py-1 text-xs rounded bg-gray-100 text-gray-700 hover:bg-gray-200"
                        >
                          History
                        </button>
                        <button
                          onClick={() => deleteModel(m)}
                          className="px-2 py-1 text-xs rounded bg-red-100 text-red-800 hover:bg-red-200"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {models.length === 0 && (
                  <tr><td colSpan={8} className="py-8 text-center text-gray-400">No models configured yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Purpose mapping */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="p-5 pb-0">
            <p className="text-sm font-semibold text-slate-700">Purpose mapping</p>
            <p className="text-xs text-slate-400 mt-1">Which model serves each feature. Changes take effect within about a minute.</p>
          </div>
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-slate-500">
                  <th className="py-2 px-5">Purpose</th>
                  <th className="py-2 px-5">Model</th>
                  <th className="py-2 px-5">Updated</th>
                  <th className="py-2 px-5"></th>
                </tr>
              </thead>
              <tbody>
                {purposes.map((p) => (
                  <tr key={p.purpose} className="border-b last:border-0">
                    <td className="py-3 px-5 font-mono text-xs">{p.purpose}</td>
                    <td className="py-3 px-5">
                      <select
                        value={p.model_id}
                        onChange={(e) => savePurposeMapping(p.purpose, Number(e.target.value))}
                        className="px-2 py-1.5 border rounded-lg text-sm"
                      >
                        {models.map((m) => (
                          <option key={m.id} value={m.id} disabled={!m.enabled}>
                            {m.display_name}{!m.enabled ? ' (disabled)' : ''}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-3 px-5 text-xs text-gray-400">{formatTimestamp(p.updated_at)}</td>
                    <td className="py-3 px-5">
                      <button
                        onClick={() => setHistoryTarget({ title: p.purpose, url: `/admin/ai-models/purposes/${p.purpose}/history` })}
                        className="px-2 py-1 text-xs rounded bg-gray-100 text-gray-700 hover:bg-gray-200"
                      >
                        History
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Add a new purpose */}
          <div className="p-5 border-t flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-500">New purpose key</label>
              <input
                value={newPurpose}
                onChange={(e) => setNewPurpose(e.target.value)}
                placeholder="e.g. translation"
                className="px-3 py-2 border rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-500">Model</label>
              <select
                value={newPurposeModel}
                onChange={(e) => setNewPurposeModel(e.target.value === '' ? '' : Number(e.target.value))}
                className="px-3 py-2 border rounded-lg text-sm"
              >
                <option value="">Select a model</option>
                {models.filter((m) => m.enabled).map((m) => (
                  <option key={m.id} value={m.id}>{m.display_name}</option>
                ))}
              </select>
            </div>
            <button
              onClick={addPurpose}
              className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700"
            >
              + Add purpose
            </button>
          </div>
        </div>
      </div>

      {formOpen && (
        <ModelFormModal
          editing={formOpen === 'new' ? null : formOpen}
          models={models}
          onClose={() => setFormOpen(null)}
          onSaved={() => { setFormOpen(null); load() }}
        />
      )}
      {historyTarget && (
        <HistoryModal
          title={historyTarget.title}
          fetchUrl={historyTarget.url}
          onClose={() => setHistoryTarget(null)}
          onRestored={load}
        />
      )}
    </div>
  )
}
