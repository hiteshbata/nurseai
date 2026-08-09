'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { useAdminUser } from '@/app/admin/AdminShell'

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking', reading: 'Reading', listening: 'Listening',
  writing: 'Writing', vocab: 'Vocabulary', grammar: 'Grammar',
}

// Vocab has no production catalog table this sprint (vocab_cards is a
// per-user SRS deck); Grammar has no production table at all. Both are
// edit/review/archive only -- publish stays disabled with a fixed message.
const PUBLISHABLE_MODULES = new Set(['speaking', 'writing', 'reading', 'listening'])

const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  review: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-blue-100 text-blue-800',
  published: 'bg-green-100 text-green-800',
  archived: 'bg-red-100 text-red-700',
}

const ROLE_RANK: Record<string, number> = { user: 0, support: 1, analyst: 2, admin: 3, owner: 4 }

interface Draft {
  id: number
  module: string
  draft_name: string
  ai_title: string | null
  metadata: Record<string, any>
  generated_content: Record<string, any>
  validation_warnings: string[]
  status: string
  model_used: string | null
  created_at: string
  updated_at: string
  reviewed_by: string | null
  reviewed_at: string | null
  approved_by: string | null
  approved_at: string | null
  published_by: string | null
  published_at: string | null
}

interface PreviewRecord {
  table: string
  fields?: Record<string, any>
  count?: number
}
interface Preview {
  records: PreviewRecord[]
  warnings: string[]
}

export default function DraftEditorPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const draftId = params.id

  const [draft, setDraft] = useState<Draft | null>(null)
  const [content, setContent] = useState<Record<string, any>>({})
  const [draftName, setDraftName] = useState('')
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  // AdminShell (the wrapping shell for every /admin/* page) already fetches
  // /auth/me to gate entry -- read its resolved role instead of fetching
  // /auth/me again here. UI convenience only: the save/publish endpoints
  // this page calls still enforce their own role checks server-side.
  const { role: roleFromShell } = useAdminUser()
  const role = roleFromShell || 'user'
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [revisions, setRevisions] = useState<any[]>([])

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const skipNextAutosave = useRef(true)

  const load = useCallback(() => {
    return api.get(`/admin/content-studio/drafts/${draftId}`)
      .then((res) => {
        skipNextAutosave.current = true
        setDraft(res.data)
        setContent(res.data.generated_content || {})
        setDraftName(res.data.draft_name || '')
      })
      .catch(() => setNotFound(true))
  }, [draftId])

  useEffect(() => {
    setLoading(true)
    load().finally(() => setLoading(false))
  }, [load])

  // Autosave: debounced PATCH whenever the edited content actually changes.
  // Skipped once right after every load()/reload so a fresh fetch never
  // fires a save-of-itself.
  useEffect(() => {
    if (skipNextAutosave.current) {
      skipNextAutosave.current = false
      return
    }
    if (saveTimer.current) clearTimeout(saveTimer.current)
    setSaveState('saving')
    saveTimer.current = setTimeout(() => {
      api.patch(`/admin/content-studio/drafts/${draftId}`, { generated_content: content })
        .then(() => setSaveState('saved'))
        .catch(() => { setSaveState('idle'); toast.error('Autosave failed') })
    }, 1000)
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content])

  const saveName = (name: string) => {
    setDraftName(name)
    api.patch(`/admin/content-studio/drafts/${draftId}`, { draft_name: name }).catch(() => toast.error('Could not rename draft'))
  }

  const runAction = async (action: string, method: 'post' | 'get' = 'post') => {
    setBusy(true)
    try {
      const res = await api[method](`/admin/content-studio/drafts/${draftId}/${action}`)
      await load()
      return res.data
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || `Could not ${action.replace('-', ' ')}`)
      throw err
    } finally {
      setBusy(false)
    }
  }

  const openPublishPreview = async () => {
    setBusy(true)
    try {
      const res = await api.get(`/admin/content-studio/drafts/${draftId}/publish-preview`)
      setPreview(res.data)
      setPreviewOpen(true)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Could not build publish preview')
    } finally {
      setBusy(false)
    }
  }

  const confirmPublish = async () => {
    try {
      await runAction('publish')
      toast.success('Published')
      setPreviewOpen(false)
    } catch {
      // toast already shown by runAction
    }
  }

  const loadHistory = async () => {
    setShowHistory((v) => !v)
    if (revisions.length === 0) {
      const res = await api.get(`/admin/content-studio/drafts/${draftId}/revisions`)
      setRevisions(res.data || [])
    }
  }

  if (loading) return <div className="min-h-screen bg-gray-50 py-12 px-4 text-gray-500">Loading...</div>
  if (notFound || !draft) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-3xl mx-auto text-center text-gray-500">
          Draft not found.
          <Link href="/admin/content-studio/drafts" className="block mx-auto mt-4 text-blue-600 hover:underline">Back to Drafts</Link>
        </div>
      </div>
    )
  }

  const rank = ROLE_RANK[role] || 0
  const canEdit = rank >= ROLE_RANK.analyst
  const canReview = rank >= ROLE_RANK.admin
  const canPublish = rank >= ROLE_RANK.owner
  const publishable = PUBLISHABLE_MODULES.has(draft.module)

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <Link href="/admin/content-studio/drafts" className="text-sm text-blue-600 hover:underline mb-4 inline-block">&larr; Back to Drafts</Link>

        <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
          <input
            value={draftName}
            disabled={!canEdit}
            onChange={(e) => saveName(e.target.value)}
            className="text-2xl font-bold border-b border-transparent hover:border-gray-300 focus:border-blue-400 focus:outline-none bg-transparent"
            data-testid="draft-name-input"
          />
          <span className={`px-3 py-1 rounded text-sm font-semibold capitalize ${STATUS_STYLES[draft.status]}`} data-testid="status-badge">
            {draft.status}
          </span>
        </div>
        <div className="text-sm text-gray-500 mb-6">
          {MODULE_LABELS[draft.module] || draft.module}
          {saveState === 'saving' && <span className="ml-2 text-gray-400">Saving...</span>}
          {saveState === 'saved' && <span className="ml-2 text-green-600">Saved</span>}
        </div>

        {(draft.validation_warnings || []).length > 0 && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-4 text-sm text-yellow-800">
            {draft.validation_warnings.map((w, i) => <div key={i}>&#9888; {w}</div>)}
          </div>
        )}

        {/* Workflow actions */}
        <div className="bg-white rounded-lg shadow p-4 mb-6 flex flex-wrap gap-2 items-center">
          {draft.status === 'draft' && (
            <ActionButton disabled={busy || !canEdit} onClick={() => runAction('submit-review')} testId="submit-review-button">Submit for Review</ActionButton>
          )}
          {draft.status === 'review' && (
            <>
              <ActionButton disabled={busy || !canReview} onClick={() => runAction('approve')} testId="approve-button" tone="green">Approve</ActionButton>
              <ActionButton disabled={busy || !canReview} onClick={() => runAction('reject')} testId="reject-button" tone="gray">Send Back</ActionButton>
            </>
          )}
          {draft.status === 'approved' && (
            <>
              <ActionButton disabled={busy || !canReview} onClick={() => runAction('reject')} testId="unapprove-button" tone="gray">Send Back to Review</ActionButton>
              {publishable ? (
                <ActionButton disabled={busy || !canPublish} onClick={openPublishPreview} testId="publish-button" tone="blue">Publish</ActionButton>
              ) : (
                <span className="text-sm text-gray-500 italic" data-testid="publish-disabled-message">
                  {draft.module === 'grammar'
                    ? 'Grammar publishing unavailable until production schema exists.'
                    : 'Vocabulary publishing is not available in this release.'}
                </span>
              )}
            </>
          )}
          {draft.status === 'published' && publishable && (
            <ActionButton disabled={busy || !canPublish} onClick={() => runAction('unpublish')} testId="unpublish-button" tone="gray">Unpublish</ActionButton>
          )}
          {['draft', 'review', 'approved'].includes(draft.status) && (
            <ActionButton disabled={busy || !canReview} onClick={() => runAction('archive')} testId="archive-button" tone="red">Archive</ActionButton>
          )}
          <button onClick={loadHistory} className="ml-auto text-sm text-gray-500 hover:text-gray-700" data-testid="history-toggle">
            {showHistory ? 'Hide History' : 'View History'}
          </button>
        </div>

        {showHistory && (
          <div className="bg-white rounded-lg shadow p-4 mb-6" data-testid="revision-history">
            {revisions.length === 0 && <div className="text-sm text-gray-500">No content revisions yet.</div>}
            {revisions.map((r) => (
              <details key={r.id} className="border-b last:border-0 py-2">
                <summary className="text-sm text-gray-600 cursor-pointer">{new Date(r.created_at).toLocaleString()}</summary>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <pre className="bg-gray-50 rounded p-2 text-xs overflow-x-auto max-h-64 overflow-y-auto">{JSON.stringify(r.before, null, 2)}</pre>
                  <pre className="bg-gray-50 rounded p-2 text-xs overflow-x-auto max-h-64 overflow-y-auto">{JSON.stringify(r.after, null, 2)}</pre>
                </div>
              </details>
            ))}
          </div>
        )}

        {/* Module-aware editor */}
        <div className="bg-white rounded-lg shadow p-6">
          <ModuleEditor module={draft.module} content={content} onChange={setContent} disabled={!canEdit} />
        </div>
      </div>

      {previewOpen && preview && (
        <PublishPreviewDialog
          preview={preview}
          busy={busy}
          onCancel={() => setPreviewOpen(false)}
          onConfirm={confirmPublish}
        />
      )}
    </div>
  )
}

function ActionButton({ children, onClick, disabled, testId, tone = 'blue' }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean; testId: string; tone?: 'blue' | 'green' | 'gray' | 'red'
}) {
  const tones: Record<string, string> = {
    blue: 'bg-blue-600 hover:bg-blue-700', green: 'bg-green-600 hover:bg-green-700',
    gray: 'bg-gray-500 hover:bg-gray-600', red: 'bg-red-600 hover:bg-red-700',
  }
  return (
    <button
      onClick={onClick} disabled={disabled} data-testid={testId}
      className={`px-4 py-2 text-white rounded-lg text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed ${tones[tone]}`}
    >
      {children}
    </button>
  )
}

function PublishPreviewDialog({ preview, busy, onCancel, onConfirm }: {
  preview: Preview; busy: boolean; onCancel: () => void; onConfirm: () => void
}) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50" data-testid="publish-preview-dialog">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto p-6">
        <h2 className="text-lg font-semibold mb-1">Confirm Publish</h2>
        <p className="text-sm text-gray-500 mb-4">This will create the following production record(s). The draft is copied, not moved.</p>

        {preview.warnings.length > 0 && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-4 text-sm text-yellow-800" data-testid="publish-preview-warnings">
            {preview.warnings.map((w, i) => <div key={i}>&#9888; {w}</div>)}
          </div>
        )}

        <div className="space-y-3 mb-6">
          {preview.records.map((r, i) => (
            <div key={i} className="border rounded-lg p-3" data-testid="publish-preview-record">
              <div className="text-sm font-semibold text-gray-700 mb-1">{r.table}</div>
              {r.fields ? (
                <pre className="bg-gray-50 rounded p-2 text-xs overflow-x-auto max-h-64 overflow-y-auto">{JSON.stringify(r.fields, null, 2)}</pre>
              ) : (
                <div className="text-xs text-gray-500">{r.count} row(s) will be created</div>
              )}
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onCancel} disabled={busy} className="px-4 py-2 rounded-lg text-sm font-semibold text-gray-600 hover:bg-gray-100">Cancel</button>
          <button onClick={onConfirm} disabled={busy} data-testid="confirm-publish-button" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50">
            {busy ? 'Publishing...' : 'Confirm Publish'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Module-aware editors (no code editor -- plain forms over the same
// JSON shape draft_generator/prompt_builder already produce) ──────────

function ModuleEditor({ module, content, onChange, disabled }: {
  module: string; content: Record<string, any>; onChange: (c: Record<string, any>) => void; disabled: boolean
}) {
  const set = (key: string, value: any) => onChange({ ...content, [key]: value })

  switch (module) {
    case 'speaking': return <SpeakingEditor content={content} set={set} disabled={disabled} />
    case 'writing': return <WritingEditor content={content} set={set} disabled={disabled} />
    case 'reading': return <ReadingEditor content={content} set={set} disabled={disabled} />
    case 'listening': return <ListeningEditor content={content} set={set} disabled={disabled} />
    case 'vocab': return <VocabEditor content={content} set={set} disabled={disabled} />
    case 'grammar': return <GrammarEditor content={content} set={set} disabled={disabled} />
    default: return <div className="text-gray-500">Unknown module.</div>
  }
}

type SetFn = (key: string, value: any) => void

function SpeakingEditor({ content, set, disabled }: { content: any; set: SetFn; disabled: boolean }) {
  const nurse = content.nurse_card || {}
  const interlocutor = content.interlocutor_card || {}
  const setNurse = (patch: any) => set('nurse_card', { ...nurse, ...patch })
  const setInterlocutor = (patch: any) => set('interlocutor_card', { ...interlocutor, ...patch })

  return (
    <div className="space-y-4">
      <TextInput label="Title" value={content.title || ''} onChange={(v) => set('title', v)} disabled={disabled} />
      <TextArea label="Setting" value={content.setting || ''} onChange={(v) => set('setting', v)} disabled={disabled} rows={3} />
      <div className="grid grid-cols-2 gap-4">
        <SelectInput label="Difficulty" value={content.difficulty || 'intermediate'} options={['beginner', 'intermediate', 'advanced']} onChange={(v) => set('difficulty', v)} disabled={disabled} />
        <TextInput label="Specialty" value={content.specialty || ''} onChange={(v) => set('specialty', v)} disabled={disabled} />
      </div>
      <SectionLabel>Nurse Card</SectionLabel>
      <TextInput label="Role" value={nurse.role || ''} onChange={(v) => setNurse({ role: v })} disabled={disabled} />
      <StringListEditor label="Tasks" items={nurse.tasks || []} onChange={(v) => setNurse({ tasks: v })} disabled={disabled} />
      <SectionLabel>Interlocutor Card</SectionLabel>
      <TextArea label="Persona" value={interlocutor.persona || ''} onChange={(v) => setInterlocutor({ persona: v })} disabled={disabled} rows={3} />
      <StringListEditor label="Emotional Triggers" items={interlocutor.emotional_triggers || []} onChange={(v) => setInterlocutor({ emotional_triggers: v })} disabled={disabled} />
      <StringListEditor label="Questions to Ask" items={interlocutor.questions_to_ask || []} onChange={(v) => setInterlocutor({ questions_to_ask: v })} disabled={disabled} />
      <StringListEditor label="Information to Withhold" items={interlocutor.information_to_withhold || []} onChange={(v) => setInterlocutor({ information_to_withhold: v })} disabled={disabled} />
    </div>
  )
}

function WritingEditor({ content, set, disabled }: { content: any; set: SetFn; disabled: boolean }) {
  return (
    <div className="space-y-4">
      <TextInput label="Title" value={content.title || ''} onChange={(v) => set('title', v)} disabled={disabled} />
      <SelectInput label="Difficulty" value={content.difficulty || 'medium'} options={['easy', 'medium', 'hard']} onChange={(v) => set('difficulty', v)} disabled={disabled} />
      <TextArea label="Case Notes" value={content.case_notes || ''} onChange={(v) => set('case_notes', v)} disabled={disabled} rows={10} mono />
      <TextArea label="Task" value={content.task || ''} onChange={(v) => set('task', v)} disabled={disabled} rows={3} />
      <StringListEditor label="Key Points (used for scoring)" items={content.key_points || []} onChange={(v) => set('key_points', v)} disabled={disabled} />
    </div>
  )
}

function ReadingEditor({ content, set, disabled }: { content: any; set: SetFn; disabled: boolean }) {
  return (
    <div className="space-y-4">
      <TextInput label="Title" value={content.title || ''} onChange={(v) => set('title', v)} disabled={disabled} />
      <div className="grid grid-cols-2 gap-4">
        <SelectInput label="Part" value={content.part || 'C'} options={['A', 'B', 'C']} onChange={(v) => set('part', v)} disabled={disabled} />
        <SelectInput label="Difficulty" value={content.difficulty || 'intermediate'} options={['beginner', 'intermediate', 'advanced']} onChange={(v) => set('difficulty', v)} disabled={disabled} />
      </div>
      <TextArea label="Passage" value={content.body || ''} onChange={(v) => set('body', v)} disabled={disabled} rows={14} />
      <QuestionsEditor label="Questions" questions={content.questions || []} onChange={(v) => set('questions', v)} disabled={disabled} />
    </div>
  )
}

function ListeningEditor({ content, set, disabled }: { content: any; set: SetFn; disabled: boolean }) {
  const transcript: { speaker: string; text: string }[] = content.transcript || []
  const updateTurn = (i: number, patch: any) => {
    const next = transcript.slice()
    next[i] = { ...next[i], ...patch }
    set('transcript', next)
  }
  return (
    <div className="space-y-4">
      <TextInput label="Title" value={content.title || ''} onChange={(v) => set('title', v)} disabled={disabled} />
      <div className="grid grid-cols-2 gap-4">
        <SelectInput label="Part" value={content.part || 'B'} options={['A', 'B', 'C']} onChange={(v) => set('part', v)} disabled={disabled} />
        <SelectInput label="Difficulty" value={content.difficulty || 'intermediate'} options={['beginner', 'intermediate', 'advanced']} onChange={(v) => set('difficulty', v)} disabled={disabled} />
      </div>
      <SectionLabel>Transcript</SectionLabel>
      <div className="space-y-2">
        {transcript.map((turn, i) => (
          <div key={i} className="flex gap-2 items-start">
            <input value={turn.speaker || ''} disabled={disabled} onChange={(e) => updateTurn(i, { speaker: e.target.value })} placeholder="Speaker" className="w-32 px-2 py-2 border rounded text-sm" />
            <textarea value={turn.text || ''} disabled={disabled} onChange={(e) => updateTurn(i, { text: e.target.value })} rows={2} className="flex-1 px-2 py-2 border rounded text-sm" />
            {!disabled && <button onClick={() => set('transcript', transcript.filter((_, idx) => idx !== i))} className="text-red-500 text-sm px-2">✕</button>}
          </div>
        ))}
        {!disabled && (
          <button onClick={() => set('transcript', [...transcript, { speaker: '', text: '' }])} className="text-sm text-blue-600 hover:underline">+ Add turn</button>
        )}
      </div>
      <QuestionsEditor label="Questions" questions={content.questions || []} onChange={(v) => set('questions', v)} disabled={disabled} />
    </div>
  )
}

function VocabEditor({ content, set, disabled }: { content: any; set: SetFn; disabled: boolean }) {
  const items: any[] = content.items || []
  const updateItem = (i: number, patch: any) => {
    const next = items.slice()
    next[i] = { ...next[i], ...patch }
    set('items', next)
  }
  return (
    <div className="space-y-4">
      <TextInput label="Topic" value={content.topic || ''} onChange={(v) => set('topic', v)} disabled={disabled} />
      <SelectInput label="Difficulty" value={content.difficulty || 'intermediate'} options={['beginner', 'intermediate', 'advanced']} onChange={(v) => set('difficulty', v)} disabled={disabled} />
      <SectionLabel>Items</SectionLabel>
      <div className="space-y-4">
        {items.map((item, i) => (
          <div key={i} className="border rounded-lg p-3 space-y-2">
            <div className="flex justify-between">
              <span className="text-xs font-semibold text-gray-500">Item {i + 1}</span>
              {!disabled && <button onClick={() => set('items', items.filter((_, idx) => idx !== i))} className="text-red-500 text-xs">Remove</button>}
            </div>
            <TextInput label="Term" value={item.term || ''} onChange={(v) => updateItem(i, { term: v })} disabled={disabled} />
            <TextArea label="Definition" value={item.definition || ''} onChange={(v) => updateItem(i, { definition: v })} disabled={disabled} rows={2} />
            <TextArea label="Example Sentence" value={item.example_sentence || ''} onChange={(v) => updateItem(i, { example_sentence: v })} disabled={disabled} rows={2} />
            <TextInput label="Clinical Context" value={item.clinical_context || ''} onChange={(v) => updateItem(i, { clinical_context: v })} disabled={disabled} />
          </div>
        ))}
        {!disabled && (
          <button onClick={() => set('items', [...items, { term: '', definition: '', example_sentence: '', clinical_context: '' }])} className="text-sm text-blue-600 hover:underline">+ Add item</button>
        )}
      </div>
    </div>
  )
}

function GrammarEditor({ content, set, disabled }: { content: any; set: SetFn; disabled: boolean }) {
  return (
    <div className="space-y-4">
      <TextInput label="Topic" value={content.topic || ''} onChange={(v) => set('topic', v)} disabled={disabled} />
      <SelectInput label="Difficulty" value={content.difficulty || 'intermediate'} options={['beginner', 'intermediate', 'advanced']} onChange={(v) => set('difficulty', v)} disabled={disabled} />
      <TextArea label="Explanation" value={content.explanation || ''} onChange={(v) => set('explanation', v)} disabled={disabled} rows={6} />
      <QuestionsEditor label="Practice Questions" questions={content.practice_questions || []} onChange={(v) => set('practice_questions', v)} disabled={disabled} withExplanation />
    </div>
  )
}

function QuestionsEditor({ label, questions, onChange, disabled, withExplanation }: {
  label: string; questions: any[]; onChange: (q: any[]) => void; disabled: boolean; withExplanation?: boolean
}) {
  const update = (i: number, patch: any) => {
    const next = questions.slice()
    next[i] = { ...next[i], ...patch }
    onChange(next)
  }
  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      <div className="space-y-4">
        {questions.map((q, i) => (
          <div key={i} className="border rounded-lg p-3 space-y-2">
            <div className="flex justify-between">
              <span className="text-xs font-semibold text-gray-500">Question {i + 1}</span>
              {!disabled && <button onClick={() => onChange(questions.filter((_, idx) => idx !== i))} className="text-red-500 text-xs">Remove</button>}
            </div>
            <TextArea label="Content" value={q.content || ''} onChange={(v) => update(i, { content: v })} disabled={disabled} rows={2} />
            <SelectInput label="Type" value={q.type || 'mcq'} options={['mcq', 'short_answer']} onChange={(v) => update(i, { type: v })} disabled={disabled} />
            {q.type !== 'short_answer' && (
              <StringListEditor label="Options" items={q.options || []} onChange={(v) => update(i, { options: v })} disabled={disabled} />
            )}
            <TextInput label="Correct Answer" value={q.correct_answer || ''} onChange={(v) => update(i, { correct_answer: v })} disabled={disabled} />
            {withExplanation && (
              <TextArea label="Explanation" value={q.explanation || ''} onChange={(v) => update(i, { explanation: v })} disabled={disabled} rows={2} />
            )}
          </div>
        ))}
        {!disabled && (
          <button onClick={() => onChange([...questions, { content: '', type: 'mcq', options: [], correct_answer: '' }])} className="text-sm text-blue-600 hover:underline">+ Add question</button>
        )}
      </div>
    </div>
  )
}

function StringListEditor({ label, items, onChange, disabled }: {
  label: string; items: string[]; onChange: (items: string[]) => void; disabled: boolean
}) {
  return (
    <div>
      <label className="block text-sm text-gray-500 mb-1">{label}</label>
      <div className="space-y-1">
        {items.map((v, i) => (
          <div key={i} className="flex gap-2">
            <input
              value={v} disabled={disabled}
              onChange={(e) => { const next = items.slice(); next[i] = e.target.value; onChange(next) }}
              className="flex-1 px-2 py-1.5 border rounded text-sm"
            />
            {!disabled && <button onClick={() => onChange(items.filter((_, idx) => idx !== i))} className="text-red-500 text-sm px-2">✕</button>}
          </div>
        ))}
        {!disabled && (
          <button onClick={() => onChange([...items, ''])} className="text-sm text-blue-600 hover:underline">+ Add</button>
        )}
      </div>
    </div>
  )
}

function TextInput({ label, value, onChange, disabled }: { label: string; value: string; onChange: (v: string) => void; disabled: boolean }) {
  return (
    <div>
      <label className="block text-sm text-gray-500 mb-1">{label}</label>
      <input value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-50" />
    </div>
  )
}

function TextArea({ label, value, onChange, disabled, rows = 3, mono }: {
  label: string; value: string; onChange: (v: string) => void; disabled: boolean; rows?: number; mono?: boolean
}) {
  return (
    <div>
      <label className="block text-sm text-gray-500 mb-1">{label}</label>
      <textarea
        value={value} disabled={disabled} rows={rows} onChange={(e) => onChange(e.target.value)}
        className={`w-full px-3 py-2 border rounded-lg disabled:bg-gray-50 ${mono ? 'font-mono text-sm whitespace-pre-wrap' : ''}`}
      />
    </div>
  )
}

function SelectInput({ label, value, options, onChange, disabled }: {
  label: string; value: string; options: string[]; onChange: (v: string) => void; disabled: boolean
}) {
  return (
    <div>
      <label className="block text-sm text-gray-500 mb-1">{label}</label>
      <select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-50">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-sm font-semibold text-gray-700 pt-2 border-t">{children}</div>
}
