'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { useAdminUser } from '@/app/admin/AdminShell'
import { ValidationErrorPanel, extractValidationResult, type ValidationResult } from '@/app/admin/ValidationErrors'

// RC4.1: publishing/unpublishing a test cuts an immutable version -- owner-only (require_owner).
const ROLE_RANK: Record<string, number> = { user: 0, support: 1, analyst: 2, admin: 3, owner: 4 }

type QType = 'mcq' | 'short_answer'

interface QDraft {
  id?: number
  content: string
  type: QType
  options: string[]
  correctIndex: number   // when type === 'mcq'
  expectedAnswer: string // when type === 'short_answer'
}

interface SectionForm {
  id?: number
  title: string
  part: string
  difficulty: string
  body: string
  audio_url: string | null
  questions: QDraft[]
}

interface Turn { speaker: string; text: string }

interface TestRow {
  id: number
  title: string
  is_active: boolean
  section_count: number
  parts: string[]
  question_count: number
  missing_answers: number
  missing_audio: number
  current_version: number | null  // RC4.1: highest published version, null if never published
}

interface DetailQuestion { id: number; content: string; type: QType; options: string[]; correct_answer: string | null }
interface DetailSection {
  id: number; title: string; part: string; difficulty: string; is_active: boolean
  has_audio: boolean; audio_start: number | null; audio_end: number | null
  body: string | null; question_count: number; missing_answers: number
  questions: DetailQuestion[]
}
interface PartTime { start: number; end: number }
interface TestDetail {
  id: number; title: string; is_active: boolean
  part_audio: Record<string, string | null>
  part_audio_times: Record<string, PartTime | null>
  groups: { part: string; sections: DetailSection[] }[]
}

// RC4.3.2.2: Version History (read-only) shapes -- match GET .../versions and
// .../versions/{id} exactly as returned by assessment_versioning.py.
interface VersionSummary {
  id: number
  version: number
  published_at: string | null
  published_by: string | null
  // RC4.3.2.2: human-readable identity resolved server-side from the public.users
  // mirror (never the raw UUID above) -- null only when published_by itself is null.
  published_by_display: string | null
  is_current: boolean
}
interface ListeningSnapshotSection {
  section_id: number
  title: string
  part: string
  difficulty: string
  audio_url: string | null
  transcript: unknown // jsonb: speaker turns [{speaker, text}] or plain text, or null
  body: string | null
}
interface ListeningSnapshotQuestion {
  question_id: number
  section_id: number
  type: QType
  content: string
  options: string[]
  correct_answer: string | null
}
interface ListeningSnapshot {
  test_id: number
  title: string
  part_audio: Record<string, string | null>
  part_audio_times: Record<string, PartTime | null>
  sections: ListeningSnapshotSection[]
  questions: ListeningSnapshotQuestion[]
}
interface VersionDetail {
  id: number
  listening_test_id: number
  version: number
  snapshot: ListeningSnapshot
  published_by: string | null
  published_by_display: string | null
  published_at: string | null
}

// FastAPI 422 returns `detail` as an array of objects; collapse to a string so
// toast doesn't try to render objects as React children.
function errorMessage(e: any, fallback: string): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d?.msg || JSON.stringify(d)).join('; ')
  return fallback
}

/** "m:ss" / "mm:ss" / plain seconds -> seconds. Blank or unparseable -> null. */
function parseTime(v?: string): number | null {
  if (!v || !v.trim()) return null
  const t = v.trim()
  if (t.includes(':')) {
    const [m, s] = t.split(':')
    const mm = Number(m), ss = Number(s)
    if (isNaN(mm) || isNaN(ss)) return null
    return mm * 60 + ss
  }
  const n = Number(t)
  return isNaN(n) ? null : n
}

/** seconds -> "m:ss" for pre-filling the cut inputs. */
function fmtTime(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function mapQuestions(raw: any[]): QDraft[] {
  return (raw || []).map((qq: any) => {
    const type: QType = qq.type === 'short_answer' ? 'short_answer' : 'mcq'
    const options: string[] = type === 'mcq' ? (qq.options || []) : []
    const idx = options.indexOf(qq.correct_answer)
    return {
      id: qq.id,
      content: qq.content || '',
      type,
      options,
      correctIndex: idx >= 0 ? idx : 0,
      expectedAnswer: type === 'short_answer' ? (qq.correct_answer || '') : '',
    }
  })
}

function toSavePayload(f: SectionForm, testId: number | null) {
  return {
    title: f.title,
    part: f.part,
    difficulty: f.difficulty,
    body: f.body || null,
    audio_url: f.audio_url,
    test_id: testId,
    questions: f.questions.map((q) => ({
      content: q.content,
      type: q.type,
      options: q.type === 'mcq' ? q.options : [],
      correct_answer: q.type === 'mcq' ? (q.options[q.correctIndex] ?? '') : q.expectedAnswer,
    })),
  }
}

const emptyForm = (part = 'B'): SectionForm => ({
  title: '', part, difficulty: 'intermediate', body: '', audio_url: null,
  questions: [{ content: '', type: part === 'A' ? 'short_answer' : 'mcq', options: ['', '', ''], correctIndex: 0, expectedAnswer: '' }],
})

/** Shared field + question editor, used by both extract drafts and the
 * existing-section editor. Controlled: reflects `value`, reports via `onChange`. */
function SectionFields({ value, onChange }: { value: SectionForm; onChange: (next: SectionForm) => void }) {
  const update = (patch: Partial<SectionForm>) => onChange({ ...value, ...patch })
  const setQ = (qi: number, patch: Partial<QDraft>) =>
    update({ questions: value.questions.map((q, j) => (j === qi ? { ...q, ...patch } : q)) })
  const setOpt = (qi: number, oi: number, val: string) =>
    setQ(qi, { options: value.questions[qi].options.map((o, i) => (i === oi ? val : o)) })
  const toggleType = (qi: number) => {
    const q = value.questions[qi]
    if (q.type === 'mcq') setQ(qi, { type: 'short_answer', expectedAnswer: q.expectedAnswer || q.options[q.correctIndex] || '' })
    else setQ(qi, { type: 'mcq', options: q.options.length >= 2 ? q.options : [q.expectedAnswer || '', '', ''], correctIndex: 0 })
  }

  return (
    <div className="space-y-5">
      <div className="grid md:grid-cols-4 gap-4">
        <label className="md:col-span-2">
          <span className="block text-sm font-semibold mb-1">Title</span>
          <input value={value.title} onChange={(e) => update({ title: e.target.value })} className="w-full px-3 py-2 border rounded-lg" />
        </label>
        <label>
          <span className="block text-sm font-semibold mb-1">Part</span>
          <select value={value.part} onChange={(e) => update({ part: e.target.value })} className="w-full px-3 py-2 border rounded-lg">
            <option value="A">Part A</option>
            <option value="B">Part B</option>
            <option value="C">Part C</option>
          </select>
        </label>
        <label>
          <span className="block text-sm font-semibold mb-1">Difficulty</span>
          <select value={value.difficulty} onChange={(e) => update({ difficulty: e.target.value })} className="w-full px-3 py-2 border rounded-lg">
            <option value="beginner">Beginner</option>
            <option value="intermediate">Intermediate</option>
            <option value="advanced">Advanced</option>
          </select>
        </label>
      </div>

      {value.part === 'A' && (
        <label className="block">
          <span className="block text-sm font-semibold mb-1">Notes template (Part A)</span>
          <p className="text-xs text-gray-500 mb-1">The on-screen notes the student completes. Markdown: ## headings, - bullets, mark blanks like "(1) ______".</p>
          <textarea value={value.body} onChange={(e) => update({ body: e.target.value })} rows={8} className="w-full px-3 py-2 border rounded-lg font-mono text-sm" />
        </label>
      )}

      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <h3 className="font-bold">Questions ({value.questions.length})</h3>
          <button
            onClick={() => update({ questions: [...value.questions, { content: '', type: value.part === 'A' ? 'short_answer' : 'mcq', options: ['', '', ''], correctIndex: 0, expectedAnswer: '' }] })}
            className="text-sm text-blue-600 font-semibold"
          >+ Add question</button>
        </div>

        {value.questions.map((q, qi) => (
          <div key={qi} className="border rounded-lg p-4 space-y-3">
            <div className="flex items-start gap-2">
              <span className="font-bold text-muted-foreground mt-2">{qi + 1}.</span>
              <textarea value={q.content} onChange={(e) => setQ(qi, { content: e.target.value })} rows={2}
                placeholder="Question stem (or Part A blank label, e.g. '(1) lifting ___')" className="flex-1 px-3 py-2 border rounded-lg text-sm" />
              <button onClick={() => toggleType(qi)} className="text-xs font-semibold text-gray-500 hover:text-gray-700 border rounded-lg px-2 py-1.5 mt-1 shrink-0">
                {q.type === 'mcq' ? 'Multiple choice' : 'Gap fill'} ⇄
              </button>
              <button onClick={() => update({ questions: value.questions.filter((_, i) => i !== qi) })} className="text-red-400 hover:text-red-600 text-sm mt-2">Remove</button>
            </div>

            {q.type === 'mcq' ? (
              <>
                <p className="text-xs text-gray-500 ml-6">OET Listening MCQs have 3 options (A/B/C). Select the correct one.</p>
                {q.options.map((opt, oi) => (
                  <div key={oi} className="flex items-center gap-2 ml-6">
                    <input type="radio" name={`correct-${value.id ?? 'new'}-${qi}`} checked={q.correctIndex === oi} onChange={() => setQ(qi, { correctIndex: oi })} />
                    <input value={opt} onChange={(e) => setOpt(qi, oi, e.target.value)} placeholder={`Option ${String.fromCharCode(65 + oi)}`} className="flex-1 px-3 py-1.5 border rounded-lg text-sm" />
                    {q.options.length > 2 && (
                      <button onClick={() => setQ(qi, { options: q.options.filter((_, i) => i !== oi), correctIndex: q.correctIndex >= oi && q.correctIndex > 0 ? q.correctIndex - 1 : q.correctIndex })} className="text-red-400 hover:text-red-600 text-xs">✕</button>
                    )}
                  </div>
                ))}
                <button onClick={() => setQ(qi, { options: [...q.options, ''] })} className="text-xs text-blue-600 font-semibold ml-6">+ Add option</button>
              </>
            ) : (
              <div className="ml-6">
                <p className="text-xs text-gray-500 mb-1">Reference answer (AI grades the student's typed answer against this — wording needn't match exactly).</p>
                <input value={q.expectedAnswer} onChange={(e) => setQ(qi, { expectedAnswer: e.target.value })} placeholder="Expected word/phrase" className="w-full px-3 py-1.5 border rounded-lg text-sm" />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function AdminListeningPage() {
  const { role: viewerRole } = useAdminUser()
  const canPublish = (ROLE_RANK[viewerRole || 'user'] || 0) >= ROLE_RANK.owner
  const [tests, setTests] = useState<TestRow[]>([])
  const [newTitle, setNewTitle] = useState('')
  const [creating, setCreating] = useState(false)

  const [selectedTestIds, setSelectedTestIds] = useState<Set<number>>(new Set())
  const [bulkWorking, setBulkWorking] = useState(false)
  // RC4.2: structured 409 validation errors from a failed single-test publish, by test id.
  const [publishValidation, setPublishValidation] = useState<Record<number, ValidationResult>>({})

  const [activeTest, setActiveTest] = useState<TestRow | null>(null)
  const [detail, setDetail] = useState<TestDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  // extract / transcribe
  const [pdf, setPdf] = useState<File | null>(null)
  const [answerKey, setAnswerKey] = useState<File | null>(null)
  const [extracting, setExtracting] = useState(false)
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [transcribing, setTranscribing] = useState(false)
  const [drafts, setDrafts] = useState<SectionForm[]>([])
  const [savingDraft, setSavingDraft] = useState<number | null>(null)
  const [savingAll, setSavingAll] = useState(false)

  // section editor
  const [editor, setEditor] = useState<SectionForm | null>(null)
  const [savingEditor, setSavingEditor] = useState(false)
  const [attaching, setAttaching] = useState(false)

  // per-extract audio: one clip per section, or split one full recording into extracts
  const [rowAudioUploading, setRowAudioUploading] = useState<number | null>(null)
  const [fullAudio, setFullAudio] = useState<File | null>(null)
  const [fullAudioUrl, setFullAudioUrl] = useState<string | null>(null)
  const [segTimes, setSegTimes] = useState<Record<number, { start: string; end: string }>>({})
  const [partTimes, setPartTimes] = useState<Record<string, { start: string; end: string }>>({})
  const [detecting, setDetecting] = useState(false)
  const [cutting, setCutting] = useState(false)
  const [partUploading, setPartUploading] = useState<string | null>(null)

  // RC4.3.2.2: Version History modal -- read-only, no owner gate. historyTest
  // holds {id, title} for whichever test's modal is open (null = closed).
  const [historyTest, setHistoryTest] = useState<{ id: number; title: string } | null>(null)
  const [historyVersions, setHistoryVersions] = useState<VersionSummary[] | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  // Drilled-in snapshot view, or null when showing the list.
  const [viewingVersion, setViewingVersion] = useState<VersionDetail | null>(null)
  const [viewingLoading, setViewingLoading] = useState(false)
  const [viewingError, setViewingError] = useState<string | null>(null)
  // Request-identity refs: each open/view call stamps its own id here. A
  // response only applies its setState if its id is still the latest one --
  // a slower earlier request (switch tests/versions quickly, or close mid-flight)
  // resolving after a newer one must not clobber the newer state.
  const historyReqId = useRef(0)
  const viewReqId = useRef(0)

  const fetchTests = () => {
    api.get('/listening/admin/tests').then((res) => setTests(res.data || [])).catch(() => toast.error('Failed to load tests'))
  }
  useEffect(fetchTests, [])

  // RC4.2: also pulls /preview's `validation` field into the same
  // publishValidation state a failed publish attempt populates, so the panel
  // shows what's blocking publish as soon as an admin opens the test.
  const loadDetail = (id: number) => {
    setLoadingDetail(true)
    api.get(`/listening/admin/tests/${id}/detail`).then((res) => setDetail(res.data)).catch(() => toast.error('Failed to load test')).finally(() => setLoadingDetail(false))
    api.get(`/listening/admin/tests/${id}/preview`).then((res) => {
      if (res.data?.validation) setPublishValidation((p) => ({ ...p, [id]: res.data.validation }))
    }).catch(() => {})
  }

  const manage = (t: TestRow) => { setActiveTest(t); setDrafts([]); setEditor(null); loadDetail(t.id) }
  const backToTests = () => { setActiveTest(null); setDetail(null); setDrafts([]); setEditor(null); fetchTests() }

  const createTest = async () => {
    if (!newTitle.trim()) { toast.error('Enter a test title'); return }
    setCreating(true)
    try {
      const res = await api.post('/listening/admin/tests', { title: newTitle.trim() })
      setNewTitle('')
      fetchTests()
      manage({ ...res.data, section_count: 0, parts: [], question_count: 0, missing_answers: 0, missing_audio: 0, current_version: null })
    } catch (e: any) { toast.error(errorMessage(e, 'Create failed')) } finally { setCreating(false) }
  }

  const togglePublish = async (t: TestRow) => {
    try {
      await api.post(`/listening/admin/tests/${t.id}/active`, { is_active: !t.is_active })
      toast.success(!t.is_active ? 'Test is now live' : 'Test unpublished')
      setPublishValidation((p) => { const { [t.id]: _drop, ...rest } = p; return rest })
      fetchTests()
      if (activeTest?.id === t.id) loadDetail(t.id)
    } catch (e: any) {
      const validation = extractValidationResult(e)
      if (validation) {
        setPublishValidation((p) => ({ ...p, [t.id]: validation }))
      } else {
        toast.error(errorMessage(e, 'Failed'))
      }
    }
  }

  const toggleTestSelect = (id: number) =>
    setSelectedTestIds((s) => {
      const next = new Set(s)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  const toggleSelectAllTests = () =>
    setSelectedTestIds((s) => (s.size === tests.length ? new Set() : new Set(tests.map((t) => t.id))))

  const bulkSetPublish = async (goLive: boolean) => {
    const ids = [...selectedTestIds]
    if (ids.length === 0) return
    setBulkWorking(true)
    try {
      const results = await Promise.allSettled(
        ids.map((id) => api.post(`/listening/admin/tests/${id}/active`, { is_active: goLive }))
      )
      const failed = results.filter((r) => r.status === 'rejected').length
      if (failed) toast.error(`${failed} of ${ids.length} failed`)
      else toast.success(`${ids.length} test${ids.length > 1 ? 's' : ''} ${goLive ? 'published' : 'unpublished'}`)
      setSelectedTestIds(new Set())
      fetchTests()
    } finally {
      setBulkWorking(false)
    }
  }

  const deleteTest = async (t: TestRow) => {
    if (!confirm(`Delete test "${t.title}"? Its sections detach but are kept.`)) return
    try { await api.delete(`/listening/admin/tests/${t.id}`); fetchTests() }
    catch (e: any) { toast.error(errorMessage(e, 'Failed')) }
  }

  // ── Version History (RC4.3.2.2) -- read-only, additive only ──
  const openVersionHistory = (id: number, title: string) => {
    const reqId = ++historyReqId.current
    setHistoryTest({ id, title })
    setHistoryVersions(null)
    setHistoryError(null)
    setViewingVersion(null)
    setViewingError(null)
    setHistoryLoading(true)
    api.get(`/listening/admin/tests/${id}/versions`)
      .then((res) => { if (historyReqId.current === reqId) setHistoryVersions(res.data?.versions || []) })
      .catch((e) => { if (historyReqId.current === reqId) setHistoryError(errorMessage(e, 'Failed to load version history')) })
      .finally(() => { if (historyReqId.current === reqId) setHistoryLoading(false) })
  }

  const closeVersionHistory = () => {
    historyReqId.current++ // invalidate any outstanding history-list request
    viewReqId.current++    // invalidate any outstanding version-detail request
    setHistoryTest(null)
    setHistoryVersions(null)
    setHistoryError(null)
    setHistoryLoading(false)
    setViewingVersion(null)
    setViewingError(null)
    setViewingLoading(false)
  }

  const viewVersion = (versionId: number) => {
    if (!historyTest) return
    const reqId = ++viewReqId.current
    setViewingVersion(null)
    setViewingError(null)
    setViewingLoading(true)
    api.get(`/listening/admin/tests/${historyTest.id}/versions/${versionId}`)
      .then((res) => { if (viewReqId.current === reqId) setViewingVersion(res.data) })
      .catch((e) => { if (viewReqId.current === reqId) setViewingError(errorMessage(e, 'Failed to load this version')) })
      .finally(() => { if (viewReqId.current === reqId) setViewingLoading(false) })
  }

  const backToVersionList = () => {
    viewReqId.current++ // invalidate any outstanding version-detail request
    setViewingVersion(null)
    setViewingError(null)
    setViewingLoading(false)
  }

  const handleExtract = async () => {
    if (!pdf || !activeTest) return
    setExtracting(true)
    try {
      const form = new FormData()
      form.append('file', pdf)
      if (answerKey) form.append('answer_key', answerKey)
      const res = await api.post('/listening/admin/extract', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      if (res.data?.error) { toast.error(res.data.error); return }
      const secs: SectionForm[] = (res.data.sections || []).map((s: any) => ({
        title: s.title || '', part: ['A', 'B', 'C'].includes(s.part) ? s.part : 'B',
        difficulty: s.difficulty || 'intermediate', body: s.body || '', audio_url: null,
        questions: mapQuestions(s.questions),
      }))
      if (secs.length === 0) { toast.error('No sections found in that PDF'); return }
      setDrafts(secs)
      setPdf(null); setAnswerKey(null)
      toast.success(`${secs.length} section(s) drafted — review, then save each into the test`)
    } catch (e: any) { toast.error(errorMessage(e, 'Extraction failed')) } finally { setExtracting(false) }
  }

  const handleTranscribe = async () => {
    if (!audioFile || !activeTest) return
    setTranscribing(true)
    try {
      const form = new FormData()
      form.append('file', audioFile)
      const res = await api.post('/listening/admin/transcribe', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      if (res.data?.error) { toast.error(res.data.error); return }
      const d = res.data
      setDrafts((prev) => [...prev, {
        title: d.title || '', part: ['A', 'B', 'C'].includes(d.part) ? d.part : 'B',
        difficulty: d.difficulty || 'intermediate', body: d.body || '', audio_url: d.audio_url || null,
        questions: mapQuestions(d.questions),
      }])
      setAudioFile(null)
      toast.success('Transcribed — review the draft below, then save it into the test')
    } catch (e: any) { toast.error(errorMessage(e, 'Transcription failed')) } finally { setTranscribing(false) }
  }

  const saveDraft = async (i: number) => {
    if (!activeTest) return
    setSavingDraft(i)
    try {
      await api.post('/listening/admin/save', toSavePayload(drafts[i], activeTest.id))
      setDrafts((prev) => prev.filter((_, j) => j !== i))
      toast.success('Section saved into the test')
      loadDetail(activeTest.id)
    } catch (e: any) { toast.error(errorMessage(e, 'Save failed')) } finally { setSavingDraft(null) }
  }

  const saveAllDrafts = async () => {
    if (!activeTest || drafts.length === 0) return
    setSavingAll(true)
    let saved = 0
    const failed: SectionForm[] = []
    // Sequential, not Promise.all: keeps DB writes ordered and lets a partial
    // failure leave only the failed drafts on screen for retry.
    for (const d of drafts) {
      try {
        await api.post('/listening/admin/save', toSavePayload(d, activeTest.id))
        saved++
      } catch {
        failed.push(d)
      }
    }
    setDrafts(failed)
    if (saved) toast.success(`Saved ${saved} section${saved > 1 ? 's' : ''} into the test`)
    if (failed.length) toast.error(`${failed.length} draft${failed.length > 1 ? 's' : ''} failed — fix and retry`)
    loadDetail(activeTest.id)
    setSavingAll(false)
  }

  const openEditor = async (sectionId: number) => {
    try {
      const res = await api.get(`/listening/admin/sections/${sectionId}`)
      const s = res.data
      setEditor({ id: s.id, title: s.title, part: s.part, difficulty: s.difficulty, body: s.body || '', audio_url: s.audio_url, questions: mapQuestions(s.questions) })
    } catch (e: any) { toast.error(errorMessage(e, 'Failed to open section')) }
  }

  const newSection = (part: string) => setEditor(emptyForm(part))

  const saveEditor = async () => {
    if (!editor || !activeTest) return
    setSavingEditor(true)
    try {
      if (editor.id) {
        await api.put(`/listening/admin/sections/${editor.id}`, {
          title: editor.title, part: editor.part, difficulty: editor.difficulty, body: editor.body || null,
          questions: editor.questions.map((q) => ({ id: q.id, content: q.content, type: q.type, options: q.type === 'mcq' ? q.options : [], correct_answer: q.type === 'mcq' ? (q.options[q.correctIndex] ?? '') : q.expectedAnswer })),
        })
      } else {
        await api.post('/listening/admin/save', toSavePayload(editor, activeTest.id))
      }
      toast.success('Saved')
      setEditor(null)
      loadDetail(activeTest.id)
    } catch (e: any) { toast.error(errorMessage(e, 'Save failed')) } finally { setSavingEditor(false) }
  }

  const deleteSection = async (id: number) => {
    if (!activeTest || !confirm('Delete this section and its questions?')) return
    try { await api.delete(`/listening/admin/sections/${id}`); loadDetail(activeTest.id) }
    catch (e: any) { toast.error(errorMessage(e, 'Failed')) }
  }
  const toggleSectionActive = async (s: DetailSection) => {
    if (!activeTest) return
    try { await api.post(`/listening/admin/sections/${s.id}/active`, { is_active: !s.is_active }); loadDetail(activeTest.id) }
    catch (e: any) { toast.error(errorMessage(e, 'Failed')) }
  }

  const uploadRowAudio = async (sectionId: number, file: File | null) => {
    if (!file || !activeTest) return
    setRowAudioUploading(sectionId)
    try {
      const form = new FormData(); form.append('audio', file)
      await api.post(`/listening/admin/sections/${sectionId}/audio`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
      toast.success('Audio uploaded')
      loadDetail(activeTest.id)
    } catch (e: any) { toast.error(errorMessage(e, 'Upload failed')) } finally { setRowAudioUploading(null) }
  }

  const chooseFullAudio = (f: File | null) => {
    setFullAudio(f)
    setFullAudioUrl(f ? URL.createObjectURL(f) : null)
  }

  const handleCutAll = async () => {
    if (!fullAudio || !activeTest || !detail) return
    const extractSegs = detail.groups.flatMap((g) => g.sections)
      .map((s) => {
        const start = parseTime(segTimes[s.id]?.start)
        const end = parseTime(segTimes[s.id]?.end)
        return start != null && end != null && end > start ? { section_id: s.id, start, end } : null
      })
      .filter((x): x is { section_id: number; start: number; end: number } => x !== null)
    const introSegs = detail.groups
      .map((g) => {
        const start = parseTime(partTimes[g.part]?.start)
        const end = parseTime(partTimes[g.part]?.end)
        return start != null && end != null && end > start ? { part: g.part, start, end } : null
      })
      .filter((x): x is { part: string; start: number; end: number } => x !== null)
    if (extractSegs.length === 0 && introSegs.length === 0) { toast.error('Enter start & end times (mm:ss) for at least one row'); return }
    setCutting(true)
    try {
      let extracts = 0
      let intros = 0
      if (extractSegs.length) {
        const form = new FormData(); form.append('file', fullAudio); form.append('segments', JSON.stringify(extractSegs))
        const r = await api.post(`/listening/admin/tests/${activeTest.id}/split-audio`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
        extracts = r.data.attached?.length ?? 0
      }
      if (introSegs.length) {
        const form = new FormData(); form.append('file', fullAudio); form.append('segments', JSON.stringify(introSegs))
        const r = await api.post(`/listening/admin/tests/${activeTest.id}/split-parts`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
        intros = r.data.attached?.length ?? 0
      }
      toast.success(`Attached ${extracts} extract${extracts !== 1 ? 's' : ''} + ${intros} part intro${intros !== 1 ? 's' : ''}`)
      loadDetail(activeTest.id)
    } catch (e: any) { toast.error(errorMessage(e, 'Cut failed')) } finally { setCutting(false) }
  }

  const uploadPartAudio = async (part: string, file: File | null) => {
    if (!file || !activeTest) return
    setPartUploading(part)
    try {
      const form = new FormData(); form.append('audio', file)
      await api.post(`/listening/admin/tests/${activeTest.id}/parts/${part}/audio`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
      toast.success(`Part ${part} intro audio uploaded`)
      loadDetail(activeTest.id)
    } catch (e: any) { toast.error(errorMessage(e, 'Upload failed')) } finally { setPartUploading(null) }
  }

  const handleDetect = async () => {
    if (!fullAudio || !activeTest) return
    setDetecting(true)
    try {
      const form = new FormData(); form.append('file', fullAudio)
      const res = await api.post(`/listening/admin/tests/${activeTest.id}/detect-audio-cuts`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
      const cuts = res.data.cuts || []
      const intros = res.data.intros || []
      const nextSeg: Record<number, { start: string; end: string }> = {}
      for (const c of cuts) nextSeg[c.section_id] = { start: fmtTime(c.start), end: fmtTime(c.end) }
      const nextPart: Record<string, { start: string; end: string }> = {}
      for (const c of intros) nextPart[c.part] = { start: fmtTime(c.start), end: fmtTime(c.end) }
      setSegTimes(nextSeg)
      setPartTimes(nextPart)
      toast.success(`AI proposed ${cuts.length} extract${cuts.length !== 1 ? 's' : ''} + ${intros.length} intro${intros.length !== 1 ? 's' : ''} — review, then Cut & attach`)
    } catch (e: any) { toast.error(errorMessage(e, 'Auto-detect failed')) } finally { setDetecting(false) }
  }

  const attachAnswers = async (url: string, file: File | null, reload: () => void) => {
    if (!file) return
    setAttaching(true)
    try {
      const form = new FormData(); form.append('answer_key', file)
      const res = await api.post(url, form, { headers: { 'Content-Type': 'multipart/form-data' } })
      toast.success(`Matched ${res.data.matched} of ${res.data.total} answers`)
      reload()
    } catch (e: any) { toast.error(errorMessage(e, 'Matching failed')) } finally { setAttaching(false) }
  }

  // ── SECTION EDITOR ──
  if (editor && activeTest) {
    return (
      <div className="max-w-4xl mx-auto py-10 px-4">
        <button onClick={() => setEditor(null)} className="text-sm text-gray-500 hover:text-gray-700 mb-4">← Back to {activeTest.title}</button>
        <h1 className="text-2xl font-bold mb-6">{editor.id ? 'Edit section' : 'New section'}</h1>

        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <SectionFields value={editor} onChange={setEditor} />
        </div>

        {editor.id ? (
          <div className="bg-white rounded-lg shadow p-6 mb-6">
            <h3 className="font-bold mb-1">Attach answers (this section)</h3>
            <p className="text-xs text-gray-500 mb-2">Upload an answer-key PDF; AI fills the correct answers for this section's questions.</p>
            <input type="file" accept="application/pdf" onChange={(e) => attachAnswers(`/listening/admin/sections/${editor.id}/attach-answers`, e.target.files?.[0] ?? null, () => openEditor(editor.id!))} disabled={attaching} className="text-sm" />
            {attaching && <p className="text-xs text-muted-foreground mt-1">Matching…</p>}
            <p className="text-xs text-muted-foreground mt-3">Attach this extract's audio with the “Upload audio” button on its row in the Sections list.</p>
          </div>
        ) : (
          <p className="text-sm text-gray-500 mb-6">Save this section first, then reopen it to attach answers.</p>
        )}

        <button onClick={saveEditor} disabled={savingEditor} className="w-full py-3 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-700 disabled:opacity-50">
          {savingEditor ? 'Saving…' : editor.id ? 'Save changes' : 'Save section into test'}
        </button>
      </div>
    )
  }

  // ── TEST DETAIL (manage one test) ──
  if (activeTest) {
    return (
      <div className="max-w-4xl mx-auto py-10 px-4">
        <button onClick={backToTests} className="text-sm text-gray-500 hover:text-gray-700 mb-4">← All tests</button>
        <div className="flex items-center justify-between gap-4 flex-wrap mb-6">
          <h1 className="text-2xl font-bold">{detail?.title || activeTest.title}</h1>
          <div className="flex gap-2">
            <a href={`/practice/listening/test/${activeTest.id}?preview=1`} target="_blank" rel="noreferrer" className="px-3 py-1.5 border rounded-lg text-sm font-semibold hover:bg-gray-50">👁 Preview</a>
            <button onClick={() => togglePublish(detail ? { ...activeTest, is_active: detail.is_active } : activeTest)} disabled={!canPublish} title={canPublish ? '' : 'Owner role required'} className="px-3 py-1.5 border rounded-lg text-sm font-semibold hover:bg-gray-50 disabled:opacity-40">
              {detail?.is_active ? 'Unpublish' : 'Publish'}
            </button>
          </div>
        </div>

        {publishValidation[activeTest.id] && (
          <div className="mb-6">
            <ValidationErrorPanel
              result={publishValidation[activeTest.id]}
              onDismiss={() => setPublishValidation((p) => { const { [activeTest.id]: _drop, ...rest } = p; return rest })}
            />
          </div>
        )}

        {/* Add content */}
        <div className="bg-white rounded-lg shadow p-6 mb-6 space-y-6">
          <div>
            <h3 className="font-bold mb-1">Add from a question-paper PDF</h3>
            <p className="text-xs text-gray-500 mb-2">AI drafts sections + questions. Optionally add an answer-key PDF to fill answers.</p>
            <div className="flex flex-wrap items-center gap-3">
              <label className="text-sm">PDF: <input type="file" accept="application/pdf" onChange={(e) => setPdf(e.target.files?.[0] ?? null)} className="text-sm" /></label>
              <label className="text-sm">Answer key (optional): <input type="file" accept="application/pdf" onChange={(e) => setAnswerKey(e.target.files?.[0] ?? null)} className="text-sm" /></label>
              <button onClick={handleExtract} disabled={extracting || !pdf} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50">
                {extracting ? 'Extracting…' : 'Extract'}
              </button>
            </div>
          </div>
          <div className="border-t pt-4">
            <h3 className="font-bold mb-1">Or transcribe a real audio extract</h3>
            <p className="text-xs text-gray-500 mb-2">Only if you have audio but NO question paper — AI writes the questions from the audio. Already have the questions (from the PDF)? Skip this: save your sections, then hit <strong>Upload audio</strong> on each one below.</p>
            <div className="flex flex-wrap items-center gap-3">
              <input type="file" accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a" onChange={(e) => setAudioFile(e.target.files?.[0] ?? null)} className="text-sm" />
              <button onClick={handleTranscribe} disabled={transcribing || !audioFile} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50">
                {transcribing ? 'Transcribing…' : 'Transcribe'}
              </button>
            </div>
          </div>
          <div className="border-t pt-4 flex flex-wrap gap-2">
            {(['A', 'B', 'C'] as const).map((p) => (
              <button key={p} onClick={() => newSection(p)} className="px-3 py-1.5 border rounded-lg text-sm font-semibold hover:bg-gray-50">+ Manual Part {p} section</button>
            ))}
          </div>
        </div>

        {/* Whole-test attach answers */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h3 className="font-bold mb-1">Attach answers to the whole test</h3>
          <p className="text-xs text-gray-500 mb-2">One answer-key PDF fills answers across every section (Part A→B→C order).</p>
          <input type="file" accept="application/pdf" onChange={(e) => attachAnswers(`/listening/admin/tests/${activeTest.id}/attach-answers`, e.target.files?.[0] ?? null, () => loadDetail(activeTest.id))} disabled={attaching} className="text-sm" />
          {attaching && <p className="text-xs text-muted-foreground mt-1">Matching…</p>}
        </div>

        {/* Drafts pending save */}
        {drafts.length > 0 && (
          <div className="flex items-center justify-between gap-3 bg-white rounded-lg shadow px-6 py-4 mb-4">
            <p className="text-sm font-semibold text-gray-700">{drafts.length} draft section{drafts.length > 1 ? 's' : ''} ready to save</p>
            <button onClick={saveAllDrafts} disabled={savingAll} className="px-5 py-2 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50">
              {savingAll ? 'Saving all…' : `Save all ${drafts.length} into test`}
            </button>
          </div>
        )}
        {drafts.map((d, i) => (
          <div key={i} className="bg-amber-50 border border-amber-200 rounded-lg p-6 mb-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-amber-800">Draft section {i + 1} — not saved yet</h3>
              <button onClick={() => setDrafts((prev) => prev.filter((_, j) => j !== i))} className="text-sm text-muted-foreground hover:text-gray-600">Discard</button>
            </div>
            <SectionFields value={d} onChange={(next) => setDrafts((prev) => prev.map((x, j) => (j === i ? next : x)))} />
            <button onClick={() => saveDraft(i)} disabled={savingDraft === i} className="px-5 py-2 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50">
              {savingDraft === i ? 'Saving…' : 'Save into test'}
            </button>
          </div>
        ))}

        {/* Audio — cut every clip (part intros + extracts) from one recording, in order */}
        {detail && detail.groups.length > 0 && (
          <div className="bg-white rounded-lg shadow p-6 mb-6">
            <h3 className="font-bold mb-1">Audio</h3>
            <p className="text-xs text-gray-500 mb-1">Upload your full recording and cut every clip from it in one go — each part's intro ("In this part…") and each extract. Or upload a clip directly to any single row.</p>
            <p className="text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2 my-2">Include the narrator in each clip. Part intro = "Part A. In this part…"; extract = "Extract one. You hear a…" / "You hear a nurse…".</p>
            <input type="file" accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a" onChange={(e) => chooseFullAudio(e.target.files?.[0] ?? null)} className="text-sm" />
            {fullAudioUrl && <audio src={fullAudioUrl} controls className="w-full my-3" />}
            {fullAudio && (
              <div className="mt-3">
                <button onClick={handleDetect} disabled={detecting} className="px-4 py-2 border border-primary text-primary rounded-lg text-sm font-semibold hover:bg-primary/5 disabled:opacity-50">
                  {detecting ? 'Detecting…' : '✨ Auto-detect cuts with AI'}
                </button>
                <p className="text-[11px] text-muted-foreground mt-1">Transcribes with Deepgram and fills every time below (intros + extracts). Review before cutting.</p>
              </div>
            )}

            <div className="mt-4 space-y-3">
              {detail.groups.map((g) => (
                <div key={g.part}>
                  <p className="text-xs font-bold text-muted-foreground uppercase tracking-wide mb-1">Part {g.part}</p>
                  {/* part intro row */}
                  <div className="flex items-center gap-2 text-sm py-1">
                    <span className="flex-1 min-w-0 truncate italic text-gray-600">Part {g.part} — instructions
                      {detail.part_audio?.[g.part] && <span className="not-italic text-emerald-600"> ✓ {detail.part_audio_times?.[g.part] ? `${fmtTime(detail.part_audio_times[g.part]!.start)}–${fmtTime(detail.part_audio_times[g.part]!.end)}` : 'set'}</span>}
                    </span>
                    <input placeholder="start" value={partTimes[g.part]?.start ?? ''} onChange={(e) => setPartTimes((p) => ({ ...p, [g.part]: { start: e.target.value, end: p[g.part]?.end ?? '' } }))} className="w-20 px-2 py-1 border rounded-lg" />
                    <input placeholder="end" value={partTimes[g.part]?.end ?? ''} onChange={(e) => setPartTimes((p) => ({ ...p, [g.part]: { start: p[g.part]?.start ?? '', end: e.target.value } }))} className="w-20 px-2 py-1 border rounded-lg" />
                    <label className="text-blue-600 font-semibold cursor-pointer shrink-0 w-14 text-right">
                      {partUploading === g.part ? '…' : detail.part_audio?.[g.part] ? 'Replace' : 'Upload'}
                      <input type="file" accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a" className="hidden" disabled={partUploading === g.part} onChange={(e) => uploadPartAudio(g.part, e.target.files?.[0] ?? null)} />
                    </label>
                  </div>
                  {/* extract rows */}
                  {g.sections.map((s) => (
                    <div key={s.id} className="flex items-center gap-2 text-sm py-1">
                      <span className="flex-1 min-w-0 truncate">{s.title || '(untitled)'}
                        {s.has_audio && <span className="text-emerald-600"> ✓ {s.audio_start != null && s.audio_end != null ? `${fmtTime(s.audio_start)}–${fmtTime(s.audio_end)}` : 'set'}</span>}
                      </span>
                      <input placeholder="start" value={segTimes[s.id]?.start ?? ''} onChange={(e) => setSegTimes((p) => ({ ...p, [s.id]: { start: e.target.value, end: p[s.id]?.end ?? '' } }))} className="w-20 px-2 py-1 border rounded-lg" />
                      <input placeholder="end" value={segTimes[s.id]?.end ?? ''} onChange={(e) => setSegTimes((p) => ({ ...p, [s.id]: { start: p[s.id]?.start ?? '', end: e.target.value } }))} className="w-20 px-2 py-1 border rounded-lg" />
                      <label className="text-blue-600 font-semibold cursor-pointer shrink-0 w-14 text-right">
                        {rowAudioUploading === s.id ? '…' : s.has_audio ? 'Replace' : 'Upload'}
                        <input type="file" accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a" className="hidden" disabled={rowAudioUploading === s.id} onChange={(e) => uploadRowAudio(s.id, e.target.files?.[0] ?? null)} />
                      </label>
                    </div>
                  ))}
                </div>
              ))}
            </div>

            {fullAudio && (
              <button onClick={handleCutAll} disabled={cutting} className="mt-4 px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50">
                {cutting ? 'Cutting…' : 'Cut & attach all'}
              </button>
            )}
          </div>
        )}

        {/* Existing sections */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="font-bold mb-4">Sections</h3>
          {loadingDetail ? <p className="text-muted-foreground text-sm">Loading…</p>
            : !detail || detail.groups.length === 0 ? <p className="text-muted-foreground text-sm">No sections yet. Add some above.</p>
            : detail.groups.map((g) => (
              <div key={g.part} className="mb-5">
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-wide mb-2">Part {g.part}</p>
                <div className="space-y-2">
                  {g.sections.map((s) => (
                    <div key={s.id} className="flex items-center justify-between gap-3 border rounded-lg px-3 py-2">
                      <div className="min-w-0">
                        <p className="font-medium truncate">{s.title || '(untitled)'}</p>
                        <p className="text-xs text-gray-500">
                          {s.question_count} Q
                          {s.missing_answers > 0 && <span className="text-red-500"> · {s.missing_answers} missing answers</span>}
                          {s.has_audio
                            ? <span className="text-emerald-600"> · 🔊 {s.audio_start != null && s.audio_end != null ? `${fmtTime(s.audio_start)}–${fmtTime(s.audio_end)}` : 'audio set'}</span>
                            : <span className="text-amber-600"> · no audio</span>}
                          {!s.is_active && <span className="text-muted-foreground"> · hidden</span>}
                        </p>
                      </div>
                      <div className="flex gap-3 shrink-0 text-sm items-center">
                        <button onClick={() => openEditor(s.id)} className="text-blue-600 font-semibold">Edit</button>
                        <button onClick={() => toggleSectionActive(s)} className="text-gray-500">{s.is_active ? 'Hide' : 'Show'}</button>
                        <button onClick={() => deleteSection(s.id)} className="text-red-400 hover:text-red-600">Delete</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
        </div>
      </div>
    )
  }

  // ── TESTS LIST ──
  return (
    <div className="max-w-4xl mx-auto py-10 px-4">
      <h1 className="text-3xl font-bold mb-2">Listening Tests</h1>
      <p className="text-gray-500 mb-8">Build a full OET Listening paper — sections across Part A, B and C, each with its own audio.</p>

      <div className="bg-white rounded-lg shadow p-6 mb-8 flex flex-wrap items-end gap-3">
        <label className="flex-1 min-w-[200px]">
          <span className="block text-sm font-semibold mb-1">New test title</span>
          <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="e.g. OET Listening — Practice Test 1" className="w-full px-3 py-2 border rounded-lg" />
        </label>
        <button onClick={createTest} disabled={creating} className="px-5 py-2 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-700 disabled:opacity-50">
          {creating ? 'Creating…' : 'Create test'}
        </button>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
          <h2 className="font-bold">All tests ({tests.length})</h2>
          {selectedTestIds.size > 0 && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500">{selectedTestIds.size} selected</span>
              <button onClick={() => bulkSetPublish(true)} disabled={bulkWorking || !canPublish} title={canPublish ? '' : 'Owner role required to publish'} className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50">
                {bulkWorking ? 'Working…' : 'Publish selected'}
              </button>
              <button onClick={() => bulkSetPublish(false)} disabled={bulkWorking || !canPublish} title={canPublish ? '' : 'Owner role required to unpublish'} className="px-3 py-1.5 bg-gray-200 text-gray-700 rounded-lg text-xs font-semibold hover:bg-gray-300 disabled:opacity-50">
                Unpublish selected
              </button>
              <button onClick={() => setSelectedTestIds(new Set())} className="text-xs text-gray-500 hover:text-gray-700">Clear</button>
            </div>
          )}
        </div>
        {tests.length === 0 ? <p className="text-muted-foreground text-sm">None yet — create one above.</p> : (
          <div className="space-y-2">
            {tests.length > 1 && (
              <label className="flex items-center gap-2 text-xs text-gray-500 px-1">
                <input type="checkbox" checked={selectedTestIds.size === tests.length} onChange={toggleSelectAllTests} />
                Select all
              </label>
            )}
            {tests.map((t) => (
              <div key={t.id} className="space-y-2">
              <div className={`flex items-center justify-between gap-3 border rounded-lg px-4 py-3 ${selectedTestIds.has(t.id) ? 'bg-blue-50' : ''}`}>
                <div className="flex items-center gap-3 min-w-0">
                  <input type="checkbox" checked={selectedTestIds.has(t.id)} onChange={() => toggleTestSelect(t.id)} aria-label={`Select ${t.title}`} />
                  <div className="min-w-0">
                    <p className="font-semibold truncate">
                      {t.title} {t.is_active ? <span className="text-xs text-emerald-600">● live</span> : <span className="text-xs text-muted-foreground">draft</span>}
                      {t.current_version != null && (
                        <span title="Published version -- learners who already started an attempt keep this exact content forever" className="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-semibold ml-1">
                          v{t.current_version}
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-gray-500">
                      {t.section_count} sections · Parts {t.parts.join('/') || '—'} · {t.question_count} Q
                      {t.missing_answers > 0 && <span className="text-red-500"> · {t.missing_answers} missing answers</span>}
                      {t.missing_audio > 0 && <span className="text-amber-600"> · {t.missing_audio} missing audio</span>}
                    </p>
                  </div>
                </div>
                <div className="flex gap-3 shrink-0 text-sm">
                  <button onClick={() => manage(t)} className="text-blue-600 font-semibold">Manage</button>
                  <button onClick={() => openVersionHistory(t.id, t.title)} className="text-gray-600 font-semibold">Version History</button>
                  <button onClick={() => togglePublish(t)} disabled={!canPublish} title={canPublish ? '' : 'Owner role required'} className="text-gray-600 disabled:opacity-40">{t.is_active ? 'Unpublish' : 'Publish'}</button>
                  <button onClick={() => deleteTest(t)} className="text-red-400 hover:text-red-600">Delete</button>
                </div>
              </div>
              {publishValidation[t.id] && (
                <ValidationErrorPanel
                  result={publishValidation[t.id]}
                  onDismiss={() => setPublishValidation((p) => { const { [t.id]: _drop, ...rest } = p; return rest })}
                />
              )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* RC4.3.2.2: Version History modal -- strictly read-only, additive only.
          List view when viewingVersion is null, drilled-in snapshot view otherwise. */}
      {historyTest && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={closeVersionHistory}>
          <div
            className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {viewingVersion || viewingLoading || viewingError ? (
              <ListeningVersionSnapshotView
                testTitle={historyTest.title}
                detail={viewingVersion}
                loading={viewingLoading}
                error={viewingError}
                onBack={backToVersionList}
                onClose={closeVersionHistory}
              />
            ) : (
              <ListeningVersionHistoryList
                testTitle={historyTest.title}
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
function ListeningVersionHistoryList({
  testTitle, versions, loading, error, onView, onClose,
}: {
  testTitle: string
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
      <p className="text-sm text-gray-500 mb-4 truncate">{testTitle}</p>

      {loading && <p className="text-muted-foreground text-sm py-4">Loading version history…</p>}

      {!loading && error && (
        <p className="text-red-600 text-sm py-4">{error}</p>
      )}

      {!loading && !error && versions && versions.length === 0 && (
        <p className="text-muted-foreground text-sm py-4">No published versions yet — this test has never been made live.</p>
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
// Listening-specific: sections (not passages), grouped by part, each carrying
// its own audio_url/transcript/body -- cannot reuse Reading's renderer.
function ListeningVersionSnapshotView({
  testTitle, detail, loading, error, onBack, onClose,
}: {
  testTitle: string
  detail: VersionDetail | null
  loading: boolean
  error: string | null
  onBack: () => void
  onClose: () => void
}) {
  const groups = useMemo(() => {
    const snap = detail?.snapshot
    if (!snap || !Array.isArray(snap.sections)) return []
    const qBySection: Record<number, ListeningSnapshotQuestion[]> = {}
    for (const q of snap.questions || []) {
      (qBySection[q.section_id] ||= []).push(q)
    }
    const byPart: Record<string, ListeningSnapshotSection[]> = {}
    for (const s of snap.sections) (byPart[s.part] ||= []).push(s)
    const order: string[] = [
      'A', 'B', 'C',
      ...Object.keys(byPart).filter((p) => !['A', 'B', 'C'].includes(p)),
    ]
    return order
      .filter((part) => byPart[part]?.length)
      .map((part) => ({
        part,
        sections: byPart[part].map((s) => ({ ...s, questions: qBySection[s.section_id] || [] })),
      }))
  }, [detail])

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
      <p className="text-sm text-gray-500 mb-4 truncate">{testTitle}</p>

      {loading && <p className="text-muted-foreground text-sm py-4">Loading version…</p>}
      {!loading && error && <p className="text-red-600 text-sm py-4">{error}</p>}

      {!loading && !error && detail && (
        <>
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs font-semibold">
            🔒 Historical snapshot — read-only and cannot be edited, saved, or published.
          </div>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm mb-4">
            <dt className="text-gray-500">Test title</dt>
            <dd className="font-medium truncate">{detail.snapshot?.title ?? '—'}</dd>
            <dt className="text-gray-500">Version</dt>
            <dd className="font-medium">v{detail.version}</dd>
            <dt className="text-gray-500">Published</dt>
            <dd className="font-medium">{detail.published_at ? new Date(detail.published_at).toLocaleString() : '—'}</dd>
            <dt className="text-gray-500">Published by</dt>
            <dd className="font-medium">{detail.published_by_display || '—'}</dd>
          </dl>

          {groups.length === 0 ? (
            <p className="text-muted-foreground text-sm py-2">This snapshot has no sections recorded.</p>
          ) : (
            groups.map((g) => (
              <div key={g.part} className="mb-4 last:mb-0">
                <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">
                  Part {g.part} · {g.sections.length} section{g.sections.length === 1 ? '' : 's'}
                </p>
                <div className="space-y-2">
                  {g.sections.map((s) => (
                    <div key={s.section_id} className="border rounded-lg p-3 bg-gray-50">
                      <p className="font-medium">{s.title || '(untitled)'}</p>
                      <p className="text-xs text-gray-500 mb-2">Difficulty: {s.difficulty || '—'}</p>

                      {s.audio_url ? (
                        <audio src={s.audio_url} controls controlsList="nodownload noplaybackrate" className="w-full mb-3" />
                      ) : (
                        <p className="text-xs text-amber-600 mb-3">No audio recorded in this snapshot.</p>
                      )}

                      {s.body && (
                        <p className="text-xs whitespace-pre-wrap text-gray-700 mb-3 max-h-40 overflow-y-auto border rounded bg-white p-2">
                          {s.body}
                        </p>
                      )}

                      {s.transcript != null && (
                        <details className="mb-3 text-xs">
                          <summary className="cursor-pointer text-gray-600 font-semibold">Transcript</summary>
                          <div className="mt-1 max-h-40 overflow-y-auto border rounded bg-white p-2 text-gray-700">
                            {Array.isArray(s.transcript)
                              ? (s.transcript as { speaker?: string; text?: string }[]).map((turn, ti) => (
                                <p key={ti}><span className="font-semibold">{turn.speaker || 'Speaker'}:</span> {turn.text}</p>
                              ))
                              : <p className="whitespace-pre-wrap">{String(s.transcript)}</p>}
                          </div>
                        </details>
                      )}

                      {s.questions.length === 0 ? (
                        <p className="text-muted-foreground text-xs">No questions.</p>
                      ) : (
                        <div className="space-y-2">
                          {s.questions.map((q, qi) => (
                            <div key={q.question_id} className="text-xs">
                              <p className="font-medium text-gray-800">{qi + 1}. {q.content || '(no stem)'}</p>
                              {q.type === 'mcq' ? (
                                <ul className="ml-4 mt-0.5">
                                  {(q.options || []).map((opt, oi) => {
                                    const correct = !!q.correct_answer && opt === q.correct_answer
                                    return (
                                      <li key={oi} className={correct ? 'text-emerald-700 font-semibold' : 'text-gray-600'}>
                                        {correct ? '✓ ' : '• '}{opt}
                                      </li>
                                    )
                                  })}
                                </ul>
                              ) : (
                                <p className="ml-4 mt-0.5 text-gray-600">
                                  Answer: {q.correct_answer
                                    ? <span className="text-emerald-700 font-semibold">{q.correct_answer}</span>
                                    : <span className="text-amber-600">—</span>}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </>
      )}
    </div>
  )
}
