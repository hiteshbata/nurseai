'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import api from '@/lib/api'
import toast from 'react-hot-toast'

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking',
  reading: 'Reading',
  listening: 'Listening',
  writing: 'Writing',
  vocab: 'Vocabulary',
  grammar: 'Grammar',
}

const DIFFICULTY_OPTIONS = ['beginner', 'intermediate', 'advanced']
const SPECIALTY_OPTIONS = ['general', 'surgical', 'paediatric', 'aged_care', 'mental_health', 'ICU', 'emergency', 'community']

interface DraftResult {
  success: boolean
  error?: string
  generated_content?: Record<string, any>
  metadata?: Record<string, any>
  prompt?: Record<string, any>
  validation_warnings?: string[]
  ai_title?: string | null
  model_used?: string | null
}

// Local-only state for each successful draft's preview card -- name is
// editable before saving (CTO review item 5), saved tracks whether this
// specific result has already been persisted so the button can't double-fire.
interface DraftCardState {
  draftName: string
  saving: boolean
  saved: boolean
  savedId?: number
}

export default function AiDraftGeneratorPage() {
  const [module, setModule] = useState('speaking')
  const [part, setPart] = useState('')
  const [difficulty, setDifficulty] = useState('intermediate')
  const [specialty, setSpecialty] = useState('general')
  const [topic, setTopic] = useState('')
  const [objectives, setObjectives] = useState('')
  const [instructions, setInstructions] = useState('')
  const [count, setCount] = useState(1)
  const [modelLabel, setModelLabel] = useState<string | null>(null)

  const [generating, setGenerating] = useState(false)
  const [results, setResults] = useState<DraftResult[]>([])
  const [cardState, setCardState] = useState<DraftCardState[]>([])

  useEffect(() => {
    api.get('/admin/ai-models/purposes')
      .then((res) => {
        const mapping = (res.data || []).find((p: any) => p.purpose === 'content_draft_generation')
        setModelLabel(mapping?.model?.display_name || null)
      })
      .catch(() => setModelLabel(null))
  }, [])

  const handleGenerate = async () => {
    if (generating) return // prevent duplicate submissions while a request is in flight
    if (!topic.trim()) {
      toast.error('Topic is required')
      return
    }
    setGenerating(true)
    try {
      const res = await api.post('/admin/content-studio/generate', {
        module, difficulty, specialty, topic: topic.trim(),
        objectives: objectives.trim() || undefined,
        instructions: instructions.trim() || undefined,
        count,
        part: module === 'reading' && part ? part : undefined,
      })
      const newResults: DraftResult[] = res.data.results
      setResults(newResults)
      setCardState(newResults.map((r) => ({
        draftName: r.ai_title || topic.trim(),
        saving: false,
        saved: false,
      })))
      const failures = newResults.filter((r) => !r.success).length
      if (failures > 0) {
        toast.error(`${failures} of ${newResults.length} draft(s) failed to generate`)
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Generation failed. Please try again.')
    } finally {
      setGenerating(false)
    }
  }

  const handleDiscard = () => {
    setResults([])
    setCardState([])
  }

  const handleSave = async (index: number) => {
    const result = results[index]
    const card = cardState[index]
    if (!result.success || !card || card.saving || card.saved) return
    if (!card.draftName.trim()) {
      toast.error('Draft name is required')
      return
    }

    setCardState((prev) => prev.map((c, i) => (i === index ? { ...c, saving: true } : c)))
    try {
      const res = await api.post('/admin/content-studio/drafts', {
        module,
        draft_name: card.draftName.trim(),
        ai_title: result.ai_title,
        metadata: result.metadata,
        prompt: result.prompt,
        generated_content: result.generated_content,
        validation_warnings: result.validation_warnings || [],
        model_used: result.model_used,
      })
      setCardState((prev) => prev.map((c, i) => (i === index ? { ...c, saving: false, saved: true, savedId: res.data.id } : c)))
      toast.success('Draft saved')
    } catch (err: any) {
      setCardState((prev) => prev.map((c, i) => (i === index ? { ...c, saving: false } : c)))
      toast.error(err?.response?.data?.detail || 'Could not save draft')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">AI Draft Generator</h1>
        <p className="text-sm text-gray-500 mb-8">
          Everything generated here is a Draft. Nothing is published or visible to learners.
        </p>

        {/* Generation Form */}
        <div className="bg-white rounded-lg shadow p-6 mb-8 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Module">
              <select value={module} onChange={(e) => setModule(e.target.value)} className="w-full px-3 py-2 border rounded-lg" data-testid="field-module">
                {Object.entries(MODULE_LABELS).map(([v, label]) => (
                  <option key={v} value={v}>{label}</option>
                ))}
              </select>
            </Field>
            {module === 'reading' && (
              <Field label="Part">
                <select value={part} onChange={(e) => setPart(e.target.value)} className="w-full px-3 py-2 border rounded-lg" data-testid="field-part">
                  <option value="">Default</option>
                  <option value="A">Part A</option>
                  <option value="B">Part B</option>
                  <option value="C">Part C</option>
                </select>
              </Field>
            )}
            <Field label="Difficulty">
              <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} className="w-full px-3 py-2 border rounded-lg" data-testid="field-difficulty">
                {DIFFICULTY_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Medical Specialty">
              <select value={specialty} onChange={(e) => setSpecialty(e.target.value)} className="w-full px-3 py-2 border rounded-lg" data-testid="field-specialty">
                {SPECIALTY_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Number of Drafts">
              <input
                type="number" min={1} max={3} value={count}
                onChange={(e) => setCount(Math.min(3, Math.max(1, Number(e.target.value) || 1)))}
                className="w-full px-3 py-2 border rounded-lg" data-testid="field-count"
              />
            </Field>
          </div>

          <Field label="Topic">
            <input
              type="text" value={topic} onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Post-operative pain management"
              className="w-full px-3 py-2 border rounded-lg" data-testid="field-topic"
            />
          </Field>

          <Field label="Learning Objectives (optional)">
            <textarea value={objectives} onChange={(e) => setObjectives(e.target.value)} rows={2} className="w-full px-3 py-2 border rounded-lg" data-testid="field-objectives" />
          </Field>

          <Field label="Additional Instructions (optional)">
            <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={2} className="w-full px-3 py-2 border rounded-lg" data-testid="field-instructions" />
          </Field>

          <div className="text-xs text-gray-500">
            Model: {modelLabel || 'Not configured -- set the "content_draft_generation" purpose in AI Models'}
          </div>

          <button
            onClick={handleGenerate}
            disabled={generating}
            data-testid="generate-button"
            className="px-5 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {generating && <Spinner />}
            {generating ? 'Generating...' : 'Generate'}
          </button>
        </div>

        {/* Draft Preview */}
        {results.length > 0 && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold">Preview</h2>
              <button onClick={handleDiscard} className="text-sm text-gray-500 hover:text-gray-700" data-testid="discard-button">
                Discard all
              </button>
            </div>

            {results.map((result, i) => (
              <DraftPreviewCard
                key={i}
                index={i}
                result={result}
                card={cardState[i]}
                onNameChange={(name) => setCardState((prev) => prev.map((c, idx) => (idx === i ? { ...c, draftName: name } : c)))}
                onSave={() => handleSave(i)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function DraftPreviewCard({
  result, card, onNameChange, onSave,
}: {
  index: number
  result: DraftResult
  card: DraftCardState
  onNameChange: (name: string) => void
  onSave: () => void
}) {
  if (!result.success) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg shadow p-6" data-testid="draft-error-card">
        <div className="text-sm font-semibold text-red-700 mb-1">Generation failed</div>
        <div className="text-sm text-gray-600">{result.error}</div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6" data-testid="draft-preview-card">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
        <div className="flex-1 min-w-[240px]">
          <label className="block text-sm text-gray-500 mb-1">Draft Name</label>
          <input
            type="text" value={card.draftName} onChange={(e) => onNameChange(e.target.value)}
            disabled={card.saved}
            className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-50"
            data-testid="draft-name-input"
          />
        </div>
        {card.saved && card.savedId ? (
          <Link
            href={`/admin/content-studio/drafts/${card.savedId}`}
            data-testid="edit-draft-link"
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700"
          >
            Edit & Review &rarr;
          </Link>
        ) : (
          <button
            onClick={onSave}
            disabled={card.saving}
            data-testid="save-draft-button"
            className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-semibold hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {card.saving && <Spinner />}
            {card.saving ? 'Saving...' : 'Save Draft'}
          </button>
        )}
      </div>

      {result.ai_title && (
        <div className="text-xs text-gray-400 mb-2">AI-generated title: {result.ai_title}</div>
      )}
      {result.model_used && (
        <div className="text-xs text-gray-400 mb-2">Model: {result.model_used}</div>
      )}

      {(result.validation_warnings || []).length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-4 text-sm text-yellow-800" data-testid="validation-warnings">
          {(result.validation_warnings || []).map((w, i) => <div key={i}>&#9888; {w}</div>)}
        </div>
      )}

      <pre className="bg-gray-50 rounded-lg p-4 text-xs overflow-x-auto max-h-96 overflow-y-auto" data-testid="draft-content">
        {JSON.stringify(result.generated_content, null, 2)}
      </pre>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm text-gray-500 mb-1">{label}</label>
      {children}
    </div>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" data-testid="spinner">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}
