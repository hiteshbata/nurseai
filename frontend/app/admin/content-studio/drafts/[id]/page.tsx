'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { useAdminUser } from '@/app/admin/AdminShell'
import { urlForImage } from '@/lib/sanity'

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking', reading: 'Reading', listening: 'Listening',
  writing: 'Writing', vocab: 'Vocabulary', grammar: 'Grammar', blog: 'Blog',
}

// Vocab has no production catalog table this sprint (vocab_cards is a
// per-user SRS deck); Grammar has no production table at all. Both are
// edit/review/archive only -- publish stays disabled with a fixed message.
// Blog publishes through Sanity (Module 1 Section 12+), not draft_publisher's
// Supabase table map, so it skips the generic Publish Preview dialog (the
// backend has no preview for a Sanity target) and Unpublish (Blog's backend
// has no unpublish path) -- see the draft.module === 'blog' checks below.
const PUBLISHABLE_MODULES = new Set(['speaking', 'writing', 'reading', 'listening', 'blog'])
const NOT_PUBLISHABLE_MESSAGES: Record<string, string> = {
  grammar: 'Grammar publishing unavailable until production schema exists.',
  vocab: 'Vocabulary publishing is not available in this release.',
}

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
interface AudioGateError {
  error: 'audio_missing' | 'audio_outdated' | 'audio_missing_and_outdated'
  part: string
  missing_audio_indexes: number[]
  outdated_audio_indexes: number[]
  message: string
}

export default function DraftEditorPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const draftId = params.id

  const [draft, setDraft] = useState<Draft | null>(null)
  const [content, setContent] = useState<Record<string, any>>({})
  const [draftName, setDraftName] = useState('')
  // Blog-only (Module 1 Section 10): slug/excerpt/cover_image_ref are
  // dedicated draft columns, not part of generated_content -- see
  // draft_store.py. Every other module leaves this at its empty default and
  // never sends it.
  const [blogMeta, setBlogMeta] = useState({ slug: '', excerpt: '', cover_image_ref: '' })
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
  const [audioGateError, setAudioGateError] = useState<AudioGateError | null>(null)
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
        setBlogMeta({
          slug: res.data.slug || '',
          excerpt: res.data.excerpt || '',
          cover_image_ref: res.data.cover_image_ref || '',
        })
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
    // Guard against React 18 Strict Mode double-invoking this effect in dev,
    // which consumes skipNextAutosave.current on the first invocation and lets
    // the second invocation schedule a save of the still-empty initial state
    // before load() has hydrated draft/content. Nothing may be scheduled
    // until draft is actually loaded.
    if (!draft) return
    if (skipNextAutosave.current) {
      skipNextAutosave.current = false
      return
    }
    if (saveTimer.current) clearTimeout(saveTimer.current)
    setSaveState('saving')
    saveTimer.current = setTimeout(() => {
      const body: Record<string, any> = { generated_content: content }
      // Blog dedicated fields ride the same autosave debounce as
      // generated_content (Step 9: no Blog-specific unsaved-changes
      // system). Only sent when non-empty -- the backend validator rejects
      // an empty string as a malformed slug/excerpt, whereas omitting the
      // key entirely means "no change" (see UpdateDraftRequest).
      if (draft?.module === 'blog') {
        if (blogMeta.slug.trim()) body.slug = blogMeta.slug.trim()
        if (blogMeta.excerpt.trim()) body.excerpt = blogMeta.excerpt.trim()
        // cover_image_ref always rides along, even empty -- "" is the clear
        // sentinel the backend needs to null the field out (Section 11 Step
        // 15); omitting the key entirely means "no change" instead.
        body.cover_image_ref = blogMeta.cover_image_ref.trim()
      }
      api.patch(`/admin/content-studio/drafts/${draftId}`, body)
        .then(() => setSaveState('saved'))
        .catch((err) => {
          setSaveState('idle')
          toast.error(err?.response?.data?.detail || 'Autosave failed')
        })
    }, 1000)
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, blogMeta, draft])

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
    setAudioGateError(null)
    try {
      const res = await api.get(`/admin/content-studio/drafts/${draftId}/publish-preview`)
      setPreview(res.data)
      setPreviewOpen(true)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      // Phase 7E: Listening Part A/B/C publish is blocked while any extract's
      // audio is missing or stale -- draft_publisher.AudioNotReadyError,
      // surfaced as a 409 with a structured detail (not a plain string).
      if (err?.response?.status === 409 && detail && typeof detail === 'object' && String(detail.error || '').startsWith('audio_')) {
        setAudioGateError(detail as AudioGateError)
      } else {
        toast.error((typeof detail === 'string' && detail) || detail?.message || 'Could not build publish preview')
      }
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

  // Blog publishes straight to Sanity, not a Supabase production table --
  // draft_publisher.build_preview (the Publish Preview dialog's data source)
  // has no dispatch branch for it, so Blog skips the dialog and calls the
  // same /publish endpoint directly instead of going through openPublishPreview.
  const publishBlog = async () => {
    try {
      await runAction('publish')
      toast.success('Published')
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

        {audioGateError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-800" data-testid="audio-gate-error">
            <div className="font-semibold">Publish blocked -- audio not ready (Part {audioGateError.part})</div>
            <div className="mt-1">{audioGateError.message}</div>
            {audioGateError.missing_audio_indexes.length > 0 && (
              <div className="mt-1" data-testid="audio-gate-missing-indexes">
                Missing audio: extract {audioGateError.missing_audio_indexes.map((i) => i + 1).join(', ')}
              </div>
            )}
            {audioGateError.outdated_audio_indexes.length > 0 && (
              <div className="mt-1" data-testid="audio-gate-outdated-indexes">
                Outdated audio: extract {audioGateError.outdated_audio_indexes.map((i) => i + 1).join(', ')}
              </div>
            )}
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
                <ActionButton disabled={busy || !canPublish} onClick={draft.module === 'blog' ? publishBlog : openPublishPreview} testId="publish-button" tone="blue">Publish</ActionButton>
              ) : (
                <span className="text-sm text-gray-500 italic" data-testid="publish-disabled-message">
                  {NOT_PUBLISHABLE_MESSAGES[draft.module] || 'Publishing is not available for this module.'}
                </span>
              )}
            </>
          )}
          {draft.status === 'published' && publishable && draft.module !== 'blog' && (
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
          <ModuleEditor
            module={draft.module} content={content} onChange={setContent} disabled={!canEdit}
            blogMeta={blogMeta} onBlogMetaChange={setBlogMeta} draftId={draftId}
            slugLocked={!!draft.published_at}
          />
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

function ModuleEditor({ module, content, onChange, disabled, blogMeta, onBlogMetaChange, draftId, slugLocked }: {
  module: string; content: Record<string, any>; onChange: (c: Record<string, any>) => void; disabled: boolean
  blogMeta: { slug: string; excerpt: string; cover_image_ref: string }
  onBlogMetaChange: (m: { slug: string; excerpt: string; cover_image_ref: string }) => void
  draftId: string
  slugLocked: boolean
}) {
  const set = (key: string, value: any) => onChange({ ...content, [key]: value })

  switch (module) {
    case 'speaking': return <SpeakingEditor content={content} set={set} disabled={disabled} />
    case 'writing': return <WritingEditor content={content} set={set} disabled={disabled} />
    case 'reading': return <ReadingEditor content={content} set={set} disabled={disabled} />
    case 'listening': return <ListeningEditor content={content} set={set} disabled={disabled} draftId={draftId} />
    case 'vocab': return <VocabEditor content={content} set={set} disabled={disabled} />
    case 'grammar': return <GrammarEditor content={content} set={set} disabled={disabled} />
    case 'blog': return <BlogEditor content={content} set={set} disabled={disabled} blogMeta={blogMeta} setBlogMeta={onBlogMetaChange} draftId={draftId} slugLocked={slugLocked} />
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

// Reading generated_content has three shapes depending on OET Part:
//   Part A (or legacy/default): flat { title, body, questions }
//   Part B: { part: "B", passages: ReadingPassage[] }  (6 passages)
//   Part C: { part: "C", texts: ReadingPassage[] }      (2 texts)
// draft_generator/draft_publisher persist and read these verbatim -- the
// editor below is the only place that needs to know about all three shapes.
interface ReadingQuestion {
  content?: string
  type?: string
  options?: string[]
  correct_answer?: string
}

interface ReadingPassage {
  title?: string
  body?: string
  questions?: ReadingQuestion[]
}

function ReadingEditor({ content, set, disabled }: { content: any; set: SetFn; disabled: boolean }) {
  if (content.part === 'B') {
    return (
      <ReadingPassageSetEditor
        label="Passage" items={content.passages || []}
        onChange={(v) => set('passages', v)} disabled={disabled}
      />
    )
  }
  if (content.part === 'C') {
    return (
      <ReadingPassageSetEditor
        label="Text" items={content.texts || []}
        onChange={(v) => set('texts', v)} disabled={disabled}
      />
    )
  }
  return (
    <div className="space-y-4">
      <TextInput label="Title" value={content.title || ''} onChange={(v) => set('title', v)} disabled={disabled} testId="reading-title" />
      <div className="grid grid-cols-2 gap-4">
        <SelectInput label="Part" value={content.part || 'C'} options={['A', 'B', 'C']} onChange={(v) => set('part', v)} disabled={disabled} />
        <SelectInput label="Difficulty" value={content.difficulty || 'intermediate'} options={['beginner', 'intermediate', 'advanced']} onChange={(v) => set('difficulty', v)} disabled={disabled} />
      </div>
      <TextArea label="Passage" value={content.body || ''} onChange={(v) => set('body', v)} disabled={disabled} rows={14} testId="reading-body" />
      <QuestionsEditor label="Questions" questions={content.questions || []} onChange={(v) => set('questions', v)} disabled={disabled} />
    </div>
  )
}

function ReadingPassageSetEditor({ label, items, onChange, disabled }: {
  label: string; items: ReadingPassage[]; onChange: (items: ReadingPassage[]) => void; disabled: boolean
}) {
  const updateItem = (i: number, patch: Partial<ReadingPassage>) => {
    const next = items.slice()
    next[i] = { ...next[i], ...patch }
    onChange(next)
  }
  return (
    <div className="space-y-6">
      {items.map((item, i) => (
        <div key={i} className="border rounded-lg p-4 space-y-4" data-testid={`reading-${label.toLowerCase()}-${i}`}>
          <SectionLabel>{label} {i + 1}</SectionLabel>
          <TextInput
            label="Title" value={item.title || ''} onChange={(v) => updateItem(i, { title: v })} disabled={disabled}
            testId={`reading-${label.toLowerCase()}-${i}-title`}
          />
          <TextArea
            label="Body" value={item.body || ''} onChange={(v) => updateItem(i, { body: v })} disabled={disabled} rows={10}
            testId={`reading-${label.toLowerCase()}-${i}-body`}
          />
          <QuestionsEditor
            label="Questions" questions={item.questions || []}
            onChange={(v) => updateItem(i, { questions: v })} disabled={disabled}
          />
        </div>
      ))}
    </div>
  )
}

// Listening generated_content shape (all Parts A/B/C, Phase 4C):
//   { part, prep_seconds, [audio_mode], extracts: ListeningExtract[] }
// audio_mode lives at the top level for Parts A/B (shared across extracts)
// but per-extract for Part C (dialogue/monologue can differ per extract) --
// draft_generator never emits both on the same draft. body only appears on
// Part A extracts (the short-answer notes-template text). Pre-extracts[]
// drafts (flat title/transcript/questions) fall through to the legacy branch
// below unchanged.
interface ListeningTurn { speaker?: string; text?: string }
interface ListeningExtract {
  title?: string
  body?: string
  audio_mode?: string
  transcript?: ListeningTurn[]
  questions?: any[]
  audio_url?: string
  audio_duration_seconds?: number
  audio_generated_at?: string
  audio_transcript_hash?: string
}

function ListeningEditor({ content, set, disabled, draftId }: { content: any; set: SetFn; disabled: boolean; draftId: string }) {
  if (Array.isArray(content.extracts)) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <SelectInput label="Part" value={content.part || 'A'} options={['A', 'B', 'C']} onChange={(v) => set('part', v)} disabled={disabled} testId="listening-part" />
          <NumberInput label="Prep Seconds" value={content.prep_seconds ?? 0} onChange={(v) => set('prep_seconds', v)} disabled={disabled} testId="listening-prep-seconds" />
        </div>
        {'audio_mode' in content && (
          <SelectInput label="Audio Mode" value={content.audio_mode || 'dialogue'} options={['dialogue', 'monologue']} onChange={(v) => set('audio_mode', v)} disabled={disabled} testId="listening-audio-mode" />
        )}
        <ListeningExtractSetEditor items={content.extracts} onChange={(v) => set('extracts', v)} disabled={disabled} draftId={draftId} part={content.part || 'A'} />
      </div>
    )
  }

  const transcript: ListeningTurn[] = content.transcript || []
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

interface BatchAudioResult {
  generated: number
  failed: number
  skipped: number
  failures: { index: number; title: string; error: string }[]
}

function ListeningExtractSetEditor({ items, onChange, disabled, draftId, part }: {
  items: ListeningExtract[]; onChange: (items: ListeningExtract[]) => void; disabled: boolean; draftId: string; part: string
}) {
  // Backend is the sole owner of audio_transcript_hash comparison (listening_audio.get_audio_status) --
  // the frontend never re-derives that hash. Instead it tracks "has this extract's
  // transcript been touched since its current audio_url was stamped" locally, which is
  // enough to show OUTDATED without duplicating the hashing algorithm.
  const [dirty, setDirty] = useState<Set<number>>(new Set())
  const [generating, setGenerating] = useState<Set<number>>(new Set())
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [batchRunning, setBatchRunning] = useState(false)
  const [batchResult, setBatchResult] = useState<BatchAudioResult | null>(null)

  const updateItem = (i: number, patch: Partial<ListeningExtract>) => {
    const next = items.slice()
    next[i] = { ...next[i], ...patch }
    onChange(next)
  }

  const requestAudio = (i: number) =>
    api.post(`/admin/content-studio/drafts/${draftId}/generate-audio`, { extract_index: i }).then((res) => res.data)

  const generateVoice = async (i: number) => {
    setGenerating((prev) => new Set(prev).add(i))
    try {
      const data = await requestAudio(i)
      updateItem(i, {
        audio_url: data.audio_url,
        audio_duration_seconds: data.duration_seconds,
        audio_generated_at: data.audio_generated_at,
        audio_transcript_hash: data.audio_transcript_hash,
      })
      setDirty((prev) => { const next = new Set(prev); next.delete(i); return next })
    } catch (err: any) {
      toast.error(err?.response?.data?.detail?.message || err?.response?.data?.detail || 'Voice generation failed')
    } finally {
      setGenerating((prev) => { const next = new Set(prev); next.delete(i); return next })
    }
  }

  // NEEDS_AUDIO = NOT_GENERATED + OUTDATED. READY extracts are never included --
  // this is the sole source of truth for what Generate All will call, and it's
  // recomputed every render so a transcript edit made mid-session is picked up.
  const needsAudioIndices = items.reduce<number[]>((acc, item, i) => {
    if (!item.audio_url || dirty.has(i)) acc.push(i)
    return acc
  }, [])
  const readyCount = items.length - needsAudioIndices.length

  const runGenerateAll = async (indices: number[]) => {
    setConfirmOpen(false)
    setBatchRunning(true)
    let current = items
    const failures: BatchAudioResult['failures'] = []
    let generated = 0
    for (const i of indices) {
      setGenerating((prev) => new Set(prev).add(i))
      try {
        const data = await requestAudio(i)
        current = current.map((it, idx) => idx === i
          ? { ...it, audio_url: data.audio_url, audio_duration_seconds: data.duration_seconds, audio_generated_at: data.audio_generated_at, audio_transcript_hash: data.audio_transcript_hash }
          : it)
        onChange(current)
        setDirty((prev) => { const next = new Set(prev); next.delete(i); return next })
        generated++
      } catch (err: any) {
        failures.push({
          index: i,
          title: current[i]?.title || `Extract ${i + 1}`,
          error: err?.response?.data?.detail?.message || err?.response?.data?.detail || 'Voice generation failed',
        })
      } finally {
        setGenerating((prev) => { const next = new Set(prev); next.delete(i); return next })
      }
    }
    setBatchRunning(false)
    setBatchResult({ generated, failed: failures.length, skipped: items.length - indices.length, failures })
  }

  return (
    <div className="space-y-6">
      <GenerateAllVoiceSection
        part={part} disabled={disabled} batchRunning={batchRunning}
        needsAudioIndices={needsAudioIndices} readyCount={readyCount} total={items.length}
        confirmOpen={confirmOpen} onOpenConfirm={() => setConfirmOpen(true)} onCancelConfirm={() => setConfirmOpen(false)}
        onConfirmRun={() => runGenerateAll(needsAudioIndices)}
        batchResult={batchResult}
      />
      {items.map((item, i) => {
        const transcript = item.transcript || []
        const updateTranscript = (next: ListeningTurn[]) => {
          updateItem(i, { transcript: next })
          if (item.audio_url) setDirty((prev) => new Set(prev).add(i))
        }
        const updateTurn = (j: number, patch: Partial<ListeningTurn>) => {
          const next = transcript.slice()
          next[j] = { ...next[j], ...patch }
          updateTranscript(next)
        }
        return (
          <div key={i} className="border rounded-lg p-4 space-y-4" data-testid={`listening-extract-${i}`}>
            <SectionLabel>Extract {i + 1}</SectionLabel>
            <TextInput
              label="Title" value={item.title || ''} onChange={(v) => updateItem(i, { title: v })} disabled={disabled}
              testId={`listening-extract-${i}-title`}
            />
            {'audio_mode' in item && (
              <SelectInput
                label="Audio Mode" value={item.audio_mode || 'dialogue'} options={['dialogue', 'monologue']}
                onChange={(v) => updateItem(i, { audio_mode: v })} disabled={disabled}
                testId={`listening-extract-${i}-audio-mode`}
              />
            )}
            {'body' in item && (
              <TextArea
                label="Body / Notes Template" value={item.body || ''} onChange={(v) => updateItem(i, { body: v })} disabled={disabled} rows={6}
                testId={`listening-extract-${i}-body`}
              />
            )}
            <SectionLabel>Transcript</SectionLabel>
            <div className="space-y-2" data-testid={`listening-extract-${i}-transcript`}>
              {transcript.map((turn, j) => (
                <div key={j} className="flex gap-2 items-start">
                  <input
                    value={turn.speaker || ''} disabled={disabled} onChange={(e) => updateTurn(j, { speaker: e.target.value })}
                    placeholder="Speaker" className="w-32 px-2 py-2 border rounded text-sm"
                    data-testid={`listening-extract-${i}-turn-${j}-speaker`}
                  />
                  <textarea
                    value={turn.text || ''} disabled={disabled} onChange={(e) => updateTurn(j, { text: e.target.value })} rows={2}
                    className="flex-1 px-2 py-2 border rounded text-sm"
                    data-testid={`listening-extract-${i}-turn-${j}-text`}
                  />
                  {!disabled && <button onClick={() => updateTranscript(transcript.filter((_, idx) => idx !== j))} className="text-red-500 text-sm px-2">✕</button>}
                </div>
              ))}
              {!disabled && (
                <button onClick={() => updateTranscript([...transcript, { speaker: '', text: '' }])} className="text-sm text-blue-600 hover:underline">+ Add turn</button>
              )}
            </div>
            <AudioSection
              extract={item} index={i} disabled={disabled}
              generating={generating.has(i)} outdated={dirty.has(i)}
              onGenerate={() => generateVoice(i)}
            />
            <QuestionsEditor
              label="Questions" questions={item.questions || []}
              onChange={(v) => updateItem(i, { questions: v })} disabled={disabled}
            />
          </div>
        )
      })}
    </div>
  )
}

function GenerateAllVoiceSection({ part, disabled, batchRunning, needsAudioIndices, readyCount, total, confirmOpen, onOpenConfirm, onCancelConfirm, onConfirmRun, batchResult }: {
  part: string; disabled: boolean; batchRunning: boolean
  needsAudioIndices: number[]; readyCount: number; total: number
  confirmOpen: boolean; onOpenConfirm: () => void; onCancelConfirm: () => void; onConfirmRun: () => void
  batchResult: BatchAudioResult | null
}) {
  const n = needsAudioIndices.length
  return (
    <div className="border rounded-lg p-4 space-y-3" data-testid="generate-all-voice-section">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={onOpenConfirm} disabled={disabled || batchRunning || n === 0}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-blue-700"
          data-testid="generate-all-voice-button"
        >
          {batchRunning ? 'Generating All...' : 'Generate All Voice'}
        </button>
        <span className="text-sm text-gray-600" data-testid="generate-all-voice-summary">
          Part {part}: {readyCount}/{total} ready
        </span>
        {n === 0 && <span className="text-sm text-gray-500" data-testid="generate-all-voice-all-ready">All audio is ready.</span>}
      </div>

      {batchResult && (
        <div className="text-sm bg-gray-50 border rounded-lg p-3 space-y-1" data-testid="generate-all-voice-result">
          <div className="font-semibold">Audio generation complete.</div>
          <div>Generated: {batchResult.generated}</div>
          <div>Failed: {batchResult.failed}</div>
          <div>Skipped (already ready): {batchResult.skipped}</div>
          {batchResult.failures.map((f) => (
            <div key={f.index} className="text-red-600" data-testid={`generate-all-voice-failure-${f.index}`}>
              Extract {f.index + 1} ({f.title}): {f.error}
            </div>
          ))}
        </div>
      )}

      {confirmOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50" data-testid="generate-all-voice-dialog">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h2 className="text-lg font-semibold mb-1">Generate All Voice</h2>
            <p className="text-sm text-gray-500 mb-3">Part {part}</p>
            <p className="text-sm text-gray-800 mb-1" data-testid="generate-all-voice-count">
              Generate audio for {n} extract{n === 1 ? '' : 's'}?
            </p>
            <p className="text-sm text-gray-500 mb-4">
              This will make {n} TTS request{n === 1 ? '' : 's'}.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={onCancelConfirm} className="px-4 py-2 rounded-lg text-sm font-semibold text-gray-600 hover:bg-gray-100" data-testid="generate-all-voice-cancel-button">Cancel</button>
              <button onClick={onConfirmRun} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700" data-testid="generate-all-voice-confirm-button">Confirm</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function AudioSection({ extract, index, disabled, generating, outdated, onGenerate }: {
  extract: ListeningExtract; index: number; disabled: boolean
  generating: boolean; outdated: boolean; onGenerate: () => void
}) {
  const status = generating ? 'GENERATING' : !extract.audio_url ? 'NOT_GENERATED' : outdated ? 'OUTDATED' : 'READY'
  const STATUS_TEXT: Record<string, string> = {
    NOT_GENERATED: 'Not generated', GENERATING: 'Generating...', READY: 'Ready', OUTDATED: 'Audio outdated',
  }
  return (
    <div className="space-y-2" data-testid={`listening-extract-${index}-audio`}>
      <SectionLabel>Audio</SectionLabel>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-gray-600" data-testid={`listening-extract-${index}-audio-status`}>{STATUS_TEXT[status]}</span>
        {typeof extract.audio_duration_seconds === 'number' && (status === 'READY' || status === 'OUTDATED') && (
          <span className="text-xs text-gray-400" data-testid={`listening-extract-${index}-audio-duration`}>{Math.round(extract.audio_duration_seconds)}s</span>
        )}
        {!disabled && (
          <button
            onClick={onGenerate} disabled={generating}
            className="text-sm text-blue-600 hover:underline disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid={`listening-extract-${index}-generate-audio`}
          >
            {status === 'NOT_GENERATED' ? 'Generate Voice' : 'Regenerate Voice'}
          </button>
        )}
      </div>
      {(status === 'READY' || status === 'OUTDATED') && extract.audio_url && (
        <audio controls src={extract.audio_url} className="w-full max-w-md" data-testid={`listening-extract-${index}-audio-player`} />
      )}
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

// Mirrors backend/app/routers/admin_content_studio.py's _SLUG_RE -- client
// side is a fast hint only, the backend stays the authority (Step 8).
const BLOG_SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

const COVER_IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp'

function BlogEditor({ content, set, disabled, blogMeta, setBlogMeta, draftId, slugLocked }: {
  content: any; set: SetFn; disabled: boolean
  blogMeta: { slug: string; excerpt: string; cover_image_ref: string }
  setBlogMeta: (m: { slug: string; excerpt: string; cover_image_ref: string }) => void
  draftId: string
  slugLocked: boolean
}) {
  const title: string = content.title || ''
  const setMeta = (patch: Partial<typeof blogMeta>) => setBlogMeta({ ...blogMeta, ...patch })
  const slugValid = !blogMeta.slug || (BLOG_SLUG_RE.test(blogMeta.slug) && blogMeta.slug.length <= 200)
  const [uploadingCover, setUploadingCover] = useState(false)

  const uploadCoverImage = async (file: File) => {
    setUploadingCover(true)
    try {
      const form = new FormData()
      form.append('image', file)
      const res = await api.post(`/admin/content-studio/drafts/${draftId}/cover-image`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setMeta({ cover_image_ref: res.data.cover_image_ref })
      toast.success('Cover image uploaded')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Cover image upload failed')
    } finally {
      setUploadingCover(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="flex justify-between">
          <label className="block text-sm text-gray-500 mb-1">Title</label>
          <span className="text-xs text-gray-400">{title.length}/300</span>
        </div>
        <input
          value={title} disabled={disabled} maxLength={300}
          onChange={(e) => set('title', e.target.value)}
          className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-50"
          data-testid="blog-title"
        />
        {!title.trim() && <div className="text-xs text-red-600 mt-1">Title is required before this draft can be submitted for review.</div>}
      </div>

      <div>
        <label className="block text-sm text-gray-500 mb-1">Slug</label>
        <input
          value={blogMeta.slug} disabled={disabled || slugLocked} maxLength={200}
          onChange={(e) => setMeta({ slug: e.target.value })}
          placeholder="post-title-goes-here"
          className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-50 font-mono text-sm"
          data-testid="blog-slug"
        />
        {slugLocked ? (
          <div className="text-xs text-gray-500 mt-1" data-testid="blog-slug-locked-message">
            Slug is locked after publication to protect existing links.
          </div>
        ) : !slugValid && (
          <div className="text-xs text-red-600 mt-1">Lowercase letters, numbers, and hyphens only -- no spaces, slashes, or leading/trailing hyphens.</div>
        )}
      </div>

      <div>
        <div className="flex justify-between">
          <label className="block text-sm text-gray-500 mb-1">Excerpt</label>
          <span className="text-xs text-gray-400">{blogMeta.excerpt.length}/200</span>
        </div>
        <textarea
          value={blogMeta.excerpt} disabled={disabled} maxLength={200} rows={3}
          onChange={(e) => setMeta({ excerpt: e.target.value })}
          className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-50"
          data-testid="blog-excerpt"
        />
      </div>

      <TextArea label="Body (Markdown)" value={content.body || ''} onChange={(v) => set('body', v)} disabled={disabled} rows={18} testId="blog-body" />

      <div>
        <label className="block text-sm text-gray-500 mb-1">Cover Image</label>
        {blogMeta.cover_image_ref && (
          <img
            src={urlForImage({ asset: { _ref: blogMeta.cover_image_ref, _type: 'reference' } }).width(480).url()}
            alt="Cover preview"
            className="w-full max-w-sm rounded-lg border mb-2"
            data-testid="blog-cover-image-preview"
          />
        )}
        <div className="flex items-center gap-3">
          <label className={`px-3 py-2 border rounded-lg text-sm font-semibold ${disabled || uploadingCover ? 'text-gray-400 bg-gray-50' : 'text-gray-700 hover:bg-gray-50 cursor-pointer'}`}>
            {uploadingCover ? 'Uploading...' : blogMeta.cover_image_ref ? 'Replace image' : 'Upload image'}
            <input
              type="file" accept={COVER_IMAGE_ACCEPT} className="hidden"
              disabled={disabled || uploadingCover}
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file) uploadCoverImage(file)
              }}
              data-testid="blog-cover-image-input"
            />
          </label>
          {blogMeta.cover_image_ref && (
            <button
              type="button" disabled={disabled || uploadingCover}
              onClick={() => setMeta({ cover_image_ref: '' })}
              className="px-3 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 rounded-lg disabled:opacity-50"
              data-testid="blog-cover-image-remove"
            >
              Remove cover image
            </button>
          )}
        </div>
        <div className="text-xs text-gray-400 mt-1">JPEG, PNG, or WebP, up to 5MB.</div>
      </div>
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

function TextInput({ label, value, onChange, disabled, testId }: { label: string; value: string; onChange: (v: string) => void; disabled: boolean; testId?: string }) {
  return (
    <div>
      <label className="block text-sm text-gray-500 mb-1">{label}</label>
      <input value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} data-testid={testId} className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-50" />
    </div>
  )
}

function TextArea({ label, value, onChange, disabled, rows = 3, mono, testId }: {
  label: string; value: string; onChange: (v: string) => void; disabled: boolean; rows?: number; mono?: boolean; testId?: string
}) {
  return (
    <div>
      <label className="block text-sm text-gray-500 mb-1">{label}</label>
      <textarea
        value={value} disabled={disabled} rows={rows} onChange={(e) => onChange(e.target.value)} data-testid={testId}
        className={`w-full px-3 py-2 border rounded-lg disabled:bg-gray-50 ${mono ? 'font-mono text-sm whitespace-pre-wrap' : ''}`}
      />
    </div>
  )
}

function SelectInput({ label, value, options, onChange, disabled, testId }: {
  label: string; value: string; options: string[]; onChange: (v: string) => void; disabled: boolean; testId?: string
}) {
  return (
    <div>
      <label className="block text-sm text-gray-500 mb-1">{label}</label>
      <select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} data-testid={testId} className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-50">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

function NumberInput({ label, value, onChange, disabled, testId }: {
  label: string; value: number; onChange: (v: number) => void; disabled: boolean; testId?: string
}) {
  return (
    <div>
      <label className="block text-sm text-gray-500 mb-1">{label}</label>
      <input
        type="number" value={value} disabled={disabled}
        onChange={(e) => onChange(e.target.value === '' ? 0 : Number(e.target.value))}
        data-testid={testId} className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-50"
      />
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-sm font-semibold text-gray-700 pt-2 border-t">{children}</div>
}
