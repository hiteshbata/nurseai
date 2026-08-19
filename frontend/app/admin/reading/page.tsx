'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { splitPartASectionsRaw, joinPartASections } from '@/lib/utils'
import { useAdminUser } from '@/app/admin/AdminShell'
import { ValidationErrorPanel, extractValidationResult, type ValidationResult } from '@/app/admin/ValidationErrors'

// RC4.1: publishing/unpublishing a test cuts an immutable version -- owner-only (require_owner).
const ROLE_RANK: Record<string, number> = { user: 0, support: 1, analyst: 2, admin: 3, owner: 4 }

type QuestionType = 'mcq' | 'short_answer'

interface DraftQuestion {
  content: string
  type: QuestionType
  options: string[]
  correctIndex: number   // used when type === 'mcq'
  expectedAnswer: string // used when type === 'short_answer'
}

interface Draft {
  title: string
  part: string
  difficulty: string
  body: string
  questions: DraftQuestion[]
}

interface EditQuestion extends DraftQuestion {
  id: number | null // existing DB id to update in place, or null for a newly-added question
}

interface EditPassage extends Omit<Draft, 'questions'> {
  id: number
  questions: EditQuestion[]
}

interface PassageRow {
  id: number
  title: string
  part: string
  difficulty: string
  is_active: boolean
  created_at: string
  test_id: number | null
  test_title: string | null
}

interface ReadingTest {
  id: number
  title: string
  is_active: boolean
  passage_count: number
  parts: string[]          // which of A/B/C have at least one active passage
  question_count: number
  missing_answers: number  // questions with no correct answer yet
  current_version: number | null  // RC4.1: highest published version, null if never published
}

// Drill-down (accordion) shapes returned by /admin/tests/{id}/detail.
interface DetailQuestion {
  id: number
  content: string
  type: QuestionType
  options: string[]
  correct_answer: string | null
}
interface DetailPassage {
  id: number
  title: string
  part: string
  difficulty: string
  is_active: boolean
  question_count: number
  missing_answers: number
  questions: DetailQuestion[]
}
interface TestDetail {
  id: number
  title: string
  is_active: boolean
  groups: { part: string; passages: DetailPassage[] }[]
}

// RC4.3.2.1: Version History (read-only) shapes -- match GET .../versions and
// .../versions/{id} exactly as returned by assessment_versioning.py.
interface VersionSummary {
  id: number
  version: number
  published_at: string | null
  published_by: string | null
  // RC4.3.2.1: human-readable identity resolved server-side from the public.users
  // mirror (never the raw UUID above) -- null only when published_by itself is null.
  published_by_display: string | null
  is_current: boolean
}
interface ReadingSnapshotPassage {
  passage_id: number
  title: string
  part: string
  difficulty: string
  body: string
}
interface ReadingSnapshotQuestion {
  question_id: number
  passage_id: number
  type: QuestionType
  content: string
  options: string[]
  correct_answer: string | null
}
interface ReadingSnapshot {
  test_id: number
  title: string
  passages: ReadingSnapshotPassage[]
  questions: ReadingSnapshotQuestion[]
}
interface VersionDetail {
  id: number
  reading_test_id: number
  version: number
  snapshot: ReadingSnapshot
  published_by: string | null
  published_by_display: string | null
  published_at: string | null
}

const ALL_PARTS = ['A', 'B', 'C'] as const

// Frontend origin for opening the student-facing preview in a new tab (this admin
// SPA and the student app share the same origin in every environment).
const previewUrl = (testId: number) => `/practice/reading/test/${testId}?preview=1`

// FastAPI validation errors (422) return `detail` as an array of
// {type, loc, msg, ...} objects, not a string -- toast.error() would try to
// render those objects as React children and crash. Collapse to one string.
function errorMessage(e: any, fallback: string): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d?.msg || JSON.stringify(d)).join('; ')
  return fallback
}

function mapExtractedQuestions(raw: any[]): DraftQuestion[] {
  return (raw || []).map((qq: any) => {
    const type: QuestionType = qq.type === 'short_answer' ? 'short_answer' : 'mcq'
    const options: string[] = type === 'mcq' ? (qq.options || []) : []
    const idx = options.indexOf(qq.correct_answer)
    return {
      content: qq.content || '',
      type,
      options,
      correctIndex: idx >= 0 ? idx : 0,
      expectedAnswer: type === 'short_answer' ? (qq.correct_answer || '') : '',
    }
  })
}

export default function AdminReadingPage() {
  const [rows, setRows] = useState<PassageRow[]>([])
  // Multiple paper PDFs (e.g. Part A in one file, Part B/C in another) get
  // extracted one at a time and merged -- the OS file picker just needs `multiple`
  // to let the admin select them all in one go.
  const [files, setFiles] = useState<File[]>([])
  // Optional -- if given alongside the paper PDF(s), the same extraction call(s)
  // read both and fill correct_answer directly, skipping the separate match-answers step.
  const [extractAnswerKeyFile, setExtractAnswerKeyFile] = useState<File | null>(null)
  const [extracting, setExtracting] = useState(false)
  const [extractProgress, setExtractProgress] = useState<{ done: number; total: number } | null>(null)
  const [savingIdx, setSavingIdx] = useState<Set<number>>(new Set())
  const [savingAll, setSavingAll] = useState(false)
  // A real OET paper's Part A/B/C each contribute multiple passages -- one
  // PDF upload commonly yields several, each reviewed and saved independently.
  const [drafts, setDrafts] = useState<Draft[]>([])

  // Editing an already-saved passage (separate from the create-flow drafts above).
  const [editingPassage, setEditingPassage] = useState<EditPassage | null>(null)
  const [loadingEditId, setLoadingEditId] = useState<number | null>(null)
  const [savingEdit, setSavingEdit] = useState(false)
  const [uploadingImage, setUploadingImage] = useState(false)
  // Per-text (A-D) "what should change" prompts + which one is currently regenerating.
  const [regenInstruction, setRegenInstruction] = useState<Record<string, string>>({})
  const [regeneratingLabel, setRegeneratingLabel] = useState<string | null>(null)

  // Bulk-select delete for the existing-passages table.
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  // Inline "attach answer key" upload, one row open at a time.
  const [attachOpenId, setAttachOpenId] = useState<number | null>(null)
  const [attachFile, setAttachFile] = useState<File | null>(null)
  const [attaching, setAttaching] = useState(false)

  // Whole-test answer key: one PDF fills answers across all the test's passages.
  const [attachTestFile, setAttachTestFile] = useState<File | null>(null)
  const [attachingTestId, setAttachingTestId] = useState<number | null>(null)
  // Last match result, kept visible after the run so you can see it worked.
  const [attachTestResult, setAttachTestResult] = useState<{ testId: number; matched: number; total: number } | null>(null)

  // Bulk-select publish/unpublish for the tests list.
  const [selectedTestIds, setSelectedTestIds] = useState<Set<number>>(new Set())
  const [bulkTestWorking, setBulkTestWorking] = useState(false)
  // RC4.2: structured 409 validation errors from a failed single-test publish, by test id.
  const [publishValidation, setPublishValidation] = useState<Record<number, ValidationResult>>({})

  // Tests: a test groups a paper's passages into one student session.
  const [tests, setTests] = useState<ReadingTest[]>([])
  const [newTestTitle, setNewTestTitle] = useState('')
  const [creatingTest, setCreatingTest] = useState(false)
  // Accordion drill-down: one open test at a time, its contents cached by id.
  const [expandedTestId, setExpandedTestId] = useState<number | null>(null)
  const [expandedPassageId, setExpandedPassageId] = useState<number | null>(null)
  const [testDetail, setTestDetail] = useState<Record<number, TestDetail>>({})
  const [loadingDetailId, setLoadingDetailId] = useState<number | null>(null)
  // Which test newly-extracted passages get saved into (applies to all draft cards).
  const [draftTestId, setDraftTestId] = useState<number | null>(null)

  // RC4.3.2.1: Version History modal -- read-only, no owner gate. historyTest
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

  const fetchRows = () => {
    api.get('/reading/admin/passages')
      .then((res) => setRows(res.data || []))
      .catch(() => toast.error('Failed to load passages'))
  }

  const fetchTests = () => {
    api.get('/reading/admin/tests')
      .then((res) => {
        const data: ReadingTest[] = res.data || []
        setTests(data)
        // Any content mutation calls this, so drop the drill-down cache here -- the
        // open accordion then refetches fresh detail (counts, missing answers).
        setTestDetail({})
        // Prefill the next test's title with a numbered default so multiple sample
        // tests from multiple PDFs get consistent names -- only when the field is
        // untouched, so it never clobbers what you're typing.
        setNewTestTitle((cur) => cur || `Sample Test ${data.length + 1}`)
      })
      .catch(() => toast.error('Failed to load tests'))
  }

  const toggleTestSelect = (id: number) =>
    setSelectedTestIds((s) => {
      const next = new Set(s)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  const toggleSelectAllTests = () =>
    setSelectedTestIds((s) => (s.size === tests.length ? new Set() : new Set(tests.map((t) => t.id))))

  const bulkSetTestPublish = async (goLive: boolean) => {
    const ids = [...selectedTestIds]
    if (ids.length === 0) return
    setBulkTestWorking(true)
    try {
      const results = await Promise.allSettled(
        ids.map((id) => api.post(`/reading/admin/tests/${id}/active`, { is_active: goLive }))
      )
      const failed = results.filter((r) => r.status === 'rejected').length
      if (failed) toast.error(`${failed} of ${ids.length} failed`)
      else toast.success(`${ids.length} test${ids.length > 1 ? 's' : ''} ${goLive ? 'published' : 'unpublished'}`)
      setSelectedTestIds(new Set())
      fetchTests()
    } finally {
      setBulkTestWorking(false)
    }
  }

  const toggleTestActive = async (t: ReadingTest) => {
    // RC4.2: the backend now hard-blocks an incomplete publish (409 with
    // structured field-level errors) -- no more "publish anyway?" confirm().
    try {
      await api.post(`/reading/admin/tests/${t.id}/active`, { is_active: !t.is_active })
      toast.success(t.is_active ? 'Test unpublished' : 'Test is now live')
      setPublishValidation((p) => { const { [t.id]: _drop, ...rest } = p; return rest })
      fetchTests()
    } catch (e: any) {
      const validation = extractValidationResult(e)
      if (validation) {
        setPublishValidation((p) => ({ ...p, [t.id]: validation }))
      } else {
        toast.error(errorMessage(e, 'Failed to update test'))
      }
    }
  }

  const togglePassageActive = async (r: { id: number; is_active: boolean }) => {
    try {
      await api.post(`/reading/admin/passages/${r.id}/active`, { is_active: !r.is_active })
      fetchRows()
      fetchTests()
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to update passage'))
    }
  }

  const deleteTest = async (t: ReadingTest) => {
    if (!confirm(`Delete "${t.title}"?\n\nIts ${t.passage_count} passage${t.passage_count === 1 ? '' : 's'} are kept as standalone passages (you can delete those separately below).`)) return
    try {
      await api.delete(`/reading/admin/tests/${t.id}`)
      toast.success('Test deleted')
      fetchTests()
      fetchRows()
    } catch (e: any) {
      toast.error(errorMessage(e, 'Delete failed'))
    }
  }

  const deletePassage = async (r: { id: number; title: string }) => {
    if (!confirm(`Delete passage "${r.title}" and its questions? This cannot be undone.`)) return
    try {
      await api.delete(`/reading/admin/passages/${r.id}`)
      toast.success('Passage deleted')
      if (editingPassage?.id === r.id) setEditingPassage(null)
      fetchRows()
      fetchTests()
    } catch (e: any) {
      toast.error(errorMessage(e, 'Delete failed'))
    }
  }

  // ── bulk-select delete (passages) ──
  const toggleSelect = (id: number) =>
    setSelectedIds((s) => {
      const next = new Set(s)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  const toggleSelectAll = () => {
    const ids = rows.filter((r) => r.test_id == null).map((r) => r.id)
    setSelectedIds((s) => (s.size === ids.length ? new Set() : new Set(ids)))
  }

  const deleteSelected = async () => {
    const ids = [...selectedIds]
    if (ids.length === 0) return
    if (!confirm(`Delete ${ids.length} passage${ids.length === 1 ? '' : 's'} and their questions? This cannot be undone.`)) return
    setBulkDeleting(true)
    try {
      const results = await Promise.allSettled(ids.map((id) => api.delete(`/reading/admin/passages/${id}`)))
      const failed = results.filter((r) => r.status === 'rejected').length
      if (failed) toast.error(`${failed} of ${ids.length} couldn't be deleted`)
      else toast.success(`Deleted ${ids.length} passage${ids.length === 1 ? '' : 's'}`)
      if (editingPassage && selectedIds.has(editingPassage.id)) setEditingPassage(null)
      setSelectedIds(new Set())
      fetchRows()
      fetchTests()
    } finally {
      setBulkDeleting(false)
    }
  }

  useEffect(() => {
    fetchRows()
    fetchTests()
  }, [])

  // ── accordion drill-down ──
  const toggleExpand = (id: number) => setExpandedTestId((cur) => (cur === id ? null : id))

  // Extract a PDF straight into a specific test: aim the "save into" target at this
  // test, then run the same extraction. The drafts that appear then Save into it.
  const extractIntoTest = (testId: number) => {
    setDraftTestId(testId)
    handleExtract()
  }

  const handleAttachTestAnswers = async (testId: number) => {
    if (!attachTestFile) {
      toast.error('Choose the answer key PDF first')
      return
    }
    setAttachingTestId(testId)
    try {
      const form = new FormData()
      form.append('answer_key', attachTestFile)
      const res = await api.post(`/reading/admin/tests/${testId}/attach-answers`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const { matched, total } = res.data
      setAttachTestResult({ testId, matched, total })
      if (matched === 0) toast.error('No answers matched — check you uploaded the right answer-key PDF.')
      else toast.success(`Matched ${matched} of ${total} answers`)
      setAttachTestFile(null)
      fetchTests() // refresh missing-answer counts + reload the open drill-down
    } catch (e: any) {
      toast.error(errorMessage(e, 'Matching failed'))
    } finally {
      setAttachingTestId(null)
    }
  }

  // Load the open test's contents when expanded and not already cached. Cache is
  // cleared on every mutation (fetchTests), so this refetches fresh detail after edits.
  // RC4.2: also pulls /preview's `validation` field, so the panel shows what's
  // blocking publish as soon as an admin opens the test -- not just after a
  // failed publish attempt (same ValidationErrorPanel/publishValidation state
  // as toggleTestActive's catch below, so it's a no-op when the test is valid).
  useEffect(() => {
    const id = expandedTestId
    if (id == null || testDetail[id]) return
    let cancelled = false
    setLoadingDetailId(id)
    Promise.all([
      api.get(`/reading/admin/tests/${id}/detail`),
      api.get(`/reading/admin/tests/${id}/preview`),
    ])
      .then(([detailRes, previewRes]) => {
        if (cancelled) return
        setTestDetail((d) => ({ ...d, [id]: detailRes.data }))
        if (previewRes.data?.validation) {
          setPublishValidation((p) => ({ ...p, [id]: previewRes.data.validation }))
        }
      })
      .catch(() => { if (!cancelled) toast.error('Failed to load test contents') })
      .finally(() => { if (!cancelled) setLoadingDetailId(null) })
    return () => { cancelled = true }
  }, [expandedTestId, testDetail])

  // ── Version History (RC4.3.2.1) -- read-only, additive only ──
  const openVersionHistory = (id: number, title: string) => {
    const reqId = ++historyReqId.current
    setHistoryTest({ id, title })
    setHistoryVersions(null)
    setHistoryError(null)
    setViewingVersion(null)
    setViewingError(null)
    setHistoryLoading(true)
    api.get(`/reading/admin/tests/${id}/versions`)
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
    api.get(`/reading/admin/tests/${historyTest.id}/versions/${versionId}`)
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

  const createTest = async () => {
    if (!newTestTitle.trim()) {
      toast.error('Enter a test title')
      return
    }
    setCreatingTest(true)
    try {
      const res = await api.post('/reading/admin/tests', { title: newTestTitle.trim() })
      toast.success('Test created')
      setNewTestTitle('')
      setDraftTestId(res.data.id) // new extractions default into the test you just made
      fetchTests()
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to create test'))
    } finally {
      setCreatingTest(false)
    }
  }

  const assignPassage = async (passageId: number, testId: number | null) => {
    try {
      await api.post(`/reading/admin/passages/${passageId}/assign`, { test_id: testId })
      fetchRows()
      fetchTests()
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to assign'))
    }
  }

  // Detach = assignPassage(id, null) with a confirm() gate -- same endpoint the
  // "No test (standalone)" dropdown option already calls, just from inside the
  // test drill-down. Only test_id changes; is_active/questions/body untouched.
  const detachPassage = (p: { id: number; is_active: boolean }) => {
    const warning = p.is_active
      ? "This passage is currently active. Detaching it removes it from the test's live composition. Existing published test versions are not modified."
      : 'This will remove the passage from this test but will not delete the passage or its questions.'
    if (!confirm(`Detach passage from test?\n\n${warning}`)) return
    assignPassage(p.id, null)
  }

  const handleExtract = async () => {
    if (files.length === 0) {
      toast.error('Choose at least one PDF first')
      return
    }
    setExtracting(true)
    setExtractProgress({ done: 0, total: files.length })
    try {
      // One extraction call per file, run in sequence -- each PDF gets its own
      // OpenRouter call, and running them concurrently would just race the same
      // rate limiter. Results merge into one draft list.
      const allPassages: any[] = []
      const failed: string[] = []
      for (let i = 0; i < files.length; i++) {
        const f = files[i]
        try {
          const form = new FormData()
          form.append('file', f)
          if (extractAnswerKeyFile) form.append('answer_key', extractAnswerKeyFile)
          const res = await api.post('/reading/admin/extract', form, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
          if (res.data?.error) failed.push(`${f.name}: ${res.data.error}`)
          else allPassages.push(...(res.data.passages || []))
        } catch (e: any) {
          failed.push(`${f.name}: ${errorMessage(e, 'extraction failed')}`)
        }
        setExtractProgress({ done: i + 1, total: files.length })
      }

      if (allPassages.length === 0) {
        toast.error(failed[0] || 'No extractable passages found')
        return
      }
      const mapped: Draft[] = allPassages.map((p) => ({
        title: p.title || '',
        part: p.part === 'A' ? 'A' : p.part === 'B' ? 'B' : 'C',
        difficulty: p.difficulty || 'intermediate',
        body: p.body || '',
        questions: mapExtractedQuestions(p.questions),
      }))
      setDrafts(mapped)
      setFiles([])
      setExtractAnswerKeyFile(null)
      if (failed.length) toast.error(`${failed.length} of ${files.length} file(s) failed: ${failed.join('; ')}`)
      toast.success(`Extracted ${mapped.length} passage${mapped.length === 1 ? '' : 's'} — review each before saving`)
      // Drafts render lower on the page; jump to them so they aren't missed
      // (especially when extraction was kicked off from inside a test panel).
      setTimeout(() => document.getElementById('draft-review')?.scrollIntoView({ behavior: 'smooth' }), 100)
    } finally {
      setExtracting(false)
      setExtractProgress(null)
    }
  }

  const saveDraftPayload = (draft: Draft) => ({
    title: draft.title,
    part: draft.part,
    difficulty: draft.difficulty,
    body: draft.body,
    test_id: draftTestId,
    questions: draft.questions.map((q) => ({
      content: q.content,
      type: q.type,
      options: q.type === 'mcq' ? q.options : [],
      correct_answer: q.type === 'mcq' ? (q.options[q.correctIndex] ?? '') : q.expectedAnswer,
    })),
  })

  const handleSave = async (pi: number) => {
    setSavingIdx((s) => new Set(s).add(pi))
    try {
      await api.post('/reading/admin/save', saveDraftPayload(drafts[pi]))
      toast.success('Passage saved')
      setDrafts((ds) => ds.filter((_, i) => i !== pi))
      fetchRows()
      fetchTests()
    } catch (e: any) {
      toast.error(errorMessage(e, 'Save failed'))
    } finally {
      setSavingIdx((s) => {
        const next = new Set(s)
        next.delete(pi)
        return next
      })
    }
  }

  const saveAll = async () => {
    if (drafts.length === 0) return
    setSavingAll(true)
    // Sequential: a validation error names the exact passage, and the good ones still
    // persist. Keep only the failures so they can be fixed and retried.
    const remaining: Draft[] = []
    let saved = 0
    for (let i = 0; i < drafts.length; i++) {
      try {
        await api.post('/reading/admin/save', saveDraftPayload(drafts[i]))
        saved++
      } catch (e: any) {
        remaining.push(drafts[i])
        toast.error(`"${drafts[i].title || `Passage ${i + 1}`}": ${errorMessage(e, 'save failed')}`)
      }
    }
    setDrafts(remaining)
    if (saved > 0) toast.success(`Saved ${saved} passage${saved === 1 ? '' : 's'}`)
    fetchRows()
    fetchTests()
    setSavingAll(false)
  }

  const discard = (pi: number) => setDrafts((ds) => ds.filter((_, i) => i !== pi))

  // ── per-passage draft field helpers (create flow) ──
  const updateDraft = (pi: number, patch: Partial<Draft>) =>
    setDrafts((ds) => ds.map((d, i) => (i === pi ? { ...d, ...patch } : d)))
  const setQ = (pi: number, qi: number, patch: Partial<DraftQuestion>) =>
    setDrafts((ds) => ds.map((d, i) =>
      i === pi ? { ...d, questions: d.questions.map((q, j) => (j === qi ? { ...q, ...patch } : q)) } : d
    ))
  const setOpt = (pi: number, qi: number, oi: number, val: string) =>
    setQ(pi, qi, { options: drafts[pi].questions[qi].options.map((o, i) => (i === oi ? val : o)) })
  const toggleQType = (pi: number, qi: number) => {
    const q = drafts[pi].questions[qi]
    const nextType: QuestionType = q.type === 'mcq' ? 'short_answer' : 'mcq'
    if (nextType === 'short_answer') {
      // Carry the currently-selected MCQ answer over instead of losing it --
      // switching type shouldn't throw away an answer AI already extracted.
      setQ(pi, qi, { type: nextType, expectedAnswer: q.expectedAnswer || q.options[q.correctIndex] || '' })
    } else {
      const options = q.options.length >= 2 ? q.options : [q.expectedAnswer || '', '']
      setQ(pi, qi, { type: nextType, options, correctIndex: 0 })
    }
  }

  // ── edit-existing-passage flow ──
  const openEdit = async (id: number) => {
    setLoadingEditId(id)
    try {
      const res = await api.get(`/reading/admin/passages/${id}`)
      const p = res.data
      setEditingPassage({
        id: p.id,
        title: p.title || '',
        part: p.part === 'A' ? 'A' : p.part === 'B' ? 'B' : 'C',
        difficulty: p.difficulty || 'intermediate',
        body: p.body || '',
        questions: (p.questions || []).map((qq: any) => {
          const type: QuestionType = qq.type === 'short_answer' ? 'short_answer' : 'mcq'
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
        }),
      })
      // The editor panel sits in a fixed spot on the page, often off-screen from
      // whichever list the Edit click came from — scroll to it so it's visible.
      setTimeout(() => document.getElementById('passage-editor')?.scrollIntoView({ behavior: 'smooth' }), 150)
    } catch {
      toast.error('Failed to load passage')
    } finally {
      setLoadingEditId(null)
    }
  }

  const closeEdit = () => setEditingPassage(null)

  // Deep link from the preview tab: /admin/reading?edit=<passageId> opens that
  // passage's editor straight away, so an issue spotted while previewing is one
  // click from being fixed.
  useEffect(() => {
    const editId = new URLSearchParams(window.location.search).get('edit')
    if (editId) {
      openEdit(Number(editId))
    }
  }, [])

  const updateEdit = (patch: Partial<Omit<EditPassage, 'id' | 'questions'>>) =>
    setEditingPassage((p) => (p ? { ...p, ...patch } : p))
  const setEditQ = (qi: number, patch: Partial<EditQuestion>) =>
    setEditingPassage((p) => (p ? { ...p, questions: p.questions.map((q, i) => (i === qi ? { ...q, ...patch } : q)) } : p))
  const setEditOpt = (qi: number, oi: number, val: string) => {
    if (!editingPassage) return
    setEditQ(qi, { options: editingPassage.questions[qi].options.map((o, i) => (i === oi ? val : o)) })
  }
  const toggleEditQType = (qi: number) => {
    if (!editingPassage) return
    const q = editingPassage.questions[qi]
    const nextType: QuestionType = q.type === 'mcq' ? 'short_answer' : 'mcq'
    if (nextType === 'short_answer') {
      setEditQ(qi, { type: nextType, expectedAnswer: q.expectedAnswer || q.options[q.correctIndex] || '' })
    } else {
      const options = q.options.length >= 2 ? q.options : [q.expectedAnswer || '', '']
      setEditQ(qi, { type: nextType, options, correctIndex: 0 })
    }
  }

  const handleUploadImage = async (file: File | null) => {
    if (!file || !editingPassage) return
    setUploadingImage(true)
    try {
      const form = new FormData()
      form.append('image', file)
      const res = await api.post(`/reading/admin/passages/${editingPassage.id}/images`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      // Drop a markdown image at the end of the body; admin moves the line to where the
      // figure belongs, then Saves. Rendered inline as a real <img> for students.
      setEditingPassage((p) => (p ? { ...p, body: `${p.body}\n\n![figure](${res.data.url})\n` } : p))
      toast.success('Image added to the body — position the ![figure] line, then Save')
    } catch (e: any) {
      toast.error(errorMessage(e, 'Image upload failed'))
    } finally {
      setUploadingImage(false)
    }
  }

  const handleSaveEdit = async () => {
    if (!editingPassage) return
    setSavingEdit(true)
    try {
      const res = await api.put(`/reading/admin/passages/${editingPassage.id}`, {
        title: editingPassage.title,
        part: editingPassage.part,
        difficulty: editingPassage.difficulty,
        body: editingPassage.body,
        questions: editingPassage.questions.map((q) => ({
          id: q.id,
          content: q.content,
          type: q.type,
          options: q.type === 'mcq' ? q.options : [],
          correct_answer: q.type === 'mcq' ? (q.options[q.correctIndex] ?? '') : q.expectedAnswer,
        })),
      })
      toast.success(`Saved (${res.data.updated} updated, ${res.data.inserted} new)`)
      setEditingPassage(null)
      fetchRows()
      fetchTests()
    } catch (e: any) {
      toast.error(errorMessage(e, 'Save failed'))
    } finally {
      setSavingEdit(false)
    }
  }

  // Rewrite just one Text (A-D) within a Part A passage via AI, leaving the rest
  // of the body untouched. Sends the in-progress editor body, not the saved DB
  // copy, so unsaved edits to other texts survive.
  const regenerateText = async (label: string) => {
    if (!editingPassage) return
    const instruction = (regenInstruction[label] || '').trim()
    if (!instruction) { toast.error('Say what should change first'); return }
    setRegeneratingLabel(label)
    try {
      const res = await api.post('/reading/admin/regenerate-text', { body: editingPassage.body, label, instruction })
      updateEdit({ body: res.data.body })
      setRegenInstruction((r) => ({ ...r, [label]: '' }))
      toast.success(`Text ${label} regenerated — review before saving`)
    } catch (e: any) {
      toast.error(errorMessage(e, 'Regeneration failed'))
    } finally {
      setRegeneratingLabel(null)
    }
  }

  // ── attach answer key to an already-saved passage ──
  const handleAttachAnswers = async (id: number) => {
    if (!attachFile) {
      toast.error('Choose the answer key PDF first')
      return
    }
    setAttaching(true)
    try {
      const form = new FormData()
      form.append('answer_key', attachFile)
      const res = await api.post(`/reading/admin/passages/${id}/attach-answers`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      toast.success(`Matched ${res.data.matched} of ${res.data.total} answers`)
      setAttachOpenId(null)
      setAttachFile(null)
      fetchTests() // refresh readiness / missing-answer counts in the accordion
      if (editingPassage?.id === id) openEdit(id) // refresh the open editor with the new answers
    } catch (e: any) {
      toast.error(errorMessage(e, 'Matching failed'))
    } finally {
      setAttaching(false)
    }
  }

  // Passages already grouped into a test are managed in the test drill-down above.
  // The bottom list is just the "inbox" of passages that belong to no test yet.
  const unassignedRows = rows.filter((r) => r.test_id == null)

  // Part A bundles four source texts (A-D) into one body -- split so each gets its
  // own textarea + regenerate button. Falls back to a single box if no headers found.
  const partASections = useMemo(
    () => (editingPassage?.part === 'A' ? splitPartASectionsRaw(editingPassage.body) : []),
    [editingPassage?.part, editingPassage?.body]
  )

  const { role: viewerRole } = useAdminUser()
  const canPublish = (ROLE_RANK[viewerRole || 'user'] || 0) >= ROLE_RANK.owner

  return (
    <div className="max-w-4xl mx-auto py-10 px-4">
      <h1 className="text-3xl font-bold mb-2">Reading Passages</h1>
      <p className="text-gray-500 mb-8">Upload an OET reading PDF — AI extracts each passage and its questions for you to review before saving. Group a paper's passages into a Test so students take the whole Part A→B→C session at once.</p>

      {/* Tests */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-1">
          <h2 className="font-bold">Tests (full papers)</h2>
          {selectedTestIds.size > 0 && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500">{selectedTestIds.size} selected</span>
              <button onClick={() => bulkSetTestPublish(true)} disabled={bulkTestWorking || !canPublish} title={canPublish ? '' : 'Owner role required to publish'} className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50">
                {bulkTestWorking ? 'Working…' : 'Publish selected'}
              </button>
              <button onClick={() => bulkSetTestPublish(false)} disabled={bulkTestWorking || !canPublish} title={canPublish ? '' : 'Owner role required to unpublish'} className="px-3 py-1.5 bg-gray-200 text-gray-700 rounded-lg text-xs font-semibold hover:bg-gray-300 disabled:opacity-50">
                Unpublish selected
              </button>
              <button onClick={() => setSelectedTestIds(new Set())} className="text-xs text-gray-500 hover:text-gray-700">Clear</button>
            </div>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-4">A test = one OET paper. Assign each of its passages (Part A, the 6 Part B extracts, the 2 Part C texts) to the same test, then <strong>Preview</strong> it exactly as students see it. New tests start as a <strong>Draft</strong> (hidden); hit <strong>Make live</strong> when it's ready. Students take a live test as one full timed reading session.</p>
        {tests.length > 1 && (
          <label className="flex items-center gap-2 text-xs text-gray-500 mb-2">
            <input type="checkbox" checked={selectedTestIds.size === tests.length} onChange={toggleSelectAllTests} />
            Select all
          </label>
        )}
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <input
            value={newTestTitle}
            onChange={(e) => setNewTestTitle(e.target.value)}
            placeholder="New test title, e.g. Sample Test 2"
            className="flex-1 min-w-[200px] px-3 py-2 border rounded-lg text-sm"
          />
          <button onClick={createTest} disabled={creatingTest}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50">
            {creatingTest ? 'Creating…' : '+ Create test'}
          </button>
        </div>
        {tests.length === 0 ? (
          <p className="text-muted-foreground text-sm">No tests yet.</p>
        ) : (
          <div className="space-y-3">
            {tests.map((t) => {
              const expanded = expandedTestId === t.id
              const ready = t.passage_count > 0 && t.missing_answers === 0 && ALL_PARTS.every((p) => t.parts.includes(p))
              return (
                <div key={t.id} className={`border rounded-lg overflow-hidden ${selectedTestIds.has(t.id) ? 'ring-2 ring-blue-200' : ''}`}>
                  {/* Collapsed header row */}
                  <div className="flex items-center justify-between gap-3 p-3 flex-wrap">
                    <input type="checkbox" checked={selectedTestIds.has(t.id)} onChange={() => toggleTestSelect(t.id)} aria-label={`Select ${t.title}`} className="shrink-0" />
                    <button onClick={() => toggleExpand(t.id)} className="flex items-center gap-2 min-w-0 text-left flex-1">
                      <span className="text-gray-400 w-3 shrink-0">{expanded ? '▾' : '▸'}</span>
                      <span className="font-semibold truncate">{t.title}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-semibold shrink-0 ${t.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-200 text-gray-600'}`}>
                        {t.is_active ? 'Live' : 'Draft'}
                      </span>
                      {t.current_version != null && (
                        <span title="Published version -- learners who already started an attempt keep this exact content forever" className="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-semibold shrink-0">
                          v{t.current_version}
                        </span>
                      )}
                      <span className="flex gap-1 shrink-0">
                        {ALL_PARTS.map((p) => (
                          <span key={p} title={t.parts.includes(p) ? `Part ${p} present` : `No Part ${p} yet`}
                            className={`text-[10px] font-bold w-4 h-4 flex items-center justify-center rounded ${t.parts.includes(p) ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-200 text-muted-foreground'}`}>
                            {p}
                          </span>
                        ))}
                      </span>
                      <span className="text-muted-foreground text-xs shrink-0">{t.passage_count}p · {t.question_count}Q</span>
                      {t.question_count > 0 && (
                        <span className={`text-xs font-semibold shrink-0 ${t.missing_answers === 0 ? 'text-emerald-600' : 'text-amber-600'}`}>
                          {t.missing_answers === 0 ? '✓' : '⚠'} answers {t.question_count - t.missing_answers}/{t.question_count}
                        </span>
                      )}
                      {ready && <span className="text-emerald-600 text-xs font-semibold shrink-0">✓ ready</span>}
                    </button>
                    <div className="flex items-center gap-3 shrink-0">
                      {t.passage_count > 0 && (
                        <a href={previewUrl(t.id)} target="_blank" rel="noopener noreferrer"
                          className="text-blue-600 font-semibold text-xs hover:underline">Preview</a>
                      )}
                      <button onClick={() => openVersionHistory(t.id, t.title)}
                        className="text-gray-600 font-semibold text-xs hover:underline">
                        Version History
                      </button>
                      <button
                        onClick={() => toggleTestActive(t)}
                        disabled={!canPublish || (!t.is_active && t.passage_count === 0)}
                        title={!canPublish ? 'Owner role required to publish' : (!t.is_active && t.passage_count === 0 ? 'Add at least one passage before going live' : '')}
                        className={`text-xs font-semibold px-3 py-1 rounded-lg ${t.is_active ? 'bg-gray-100 text-gray-700 hover:bg-gray-200' : 'bg-emerald-600 text-white hover:bg-emerald-700'} disabled:opacity-40`}
                      >
                        {t.is_active ? 'Unpublish' : 'Make live'}
                      </button>
                      <button onClick={() => deleteTest(t)} className="text-red-500 hover:text-red-700 font-semibold text-xs">Delete</button>
                    </div>
                  </div>

                  {publishValidation[t.id] && (
                    <div className="px-3 pb-3">
                      <ValidationErrorPanel
                        result={publishValidation[t.id]}
                        onDismiss={() => setPublishValidation((p) => { const { [t.id]: _drop, ...rest } = p; return rest })}
                      />
                    </div>
                  )}

                  {/* Expanded drill-down: Part A/B/C -> passages -> questions */}
                  {expanded && (
                    <div className="border-t bg-gray-50 p-3 text-sm">
                      {/* Add a PDF straight into this test — extract + save land here */}
                      <div className="mb-3 p-2 bg-white border rounded-lg flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-semibold">Add PDF(s) to this test:</span>
                        <input type="file" accept="application/pdf" multiple
                          onChange={(e) => setFiles(Array.from(e.target.files ?? []))} className="text-xs" />
                        <span className="text-xs text-gray-500">+ answer key (optional):</span>
                        <input type="file" accept="application/pdf"
                          onChange={(e) => setExtractAnswerKeyFile(e.target.files?.[0] ?? null)} className="text-xs" />
                        <button onClick={() => extractIntoTest(t.id)} disabled={extracting || files.length === 0}
                          className="px-3 py-1 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-700 disabled:opacity-50">
                          {extracting
                            ? `Extracting…${extractProgress ? ` (${extractProgress.done}/${extractProgress.total})` : ''}`
                            : files.length > 1 ? `Extract ${files.length} PDFs into this test` : 'Extract into this test'}
                        </button>
                        <span className="text-[11px] text-muted-foreground">
                          {files.length > 1 ? `${files.length} files selected — ` : ''}Passages appear below to review, then Save.
                        </span>
                      </div>
                      {/* Whole-paper answer key: one PDF fills answers across every passage */}
                      <div className="mb-3 p-2 bg-white border rounded-lg flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-semibold">Answer key for whole paper:</span>
                        <input type="file" accept="application/pdf"
                          onChange={(e) => setAttachTestFile(e.target.files?.[0] ?? null)} className="text-xs" />
                        <button onClick={() => handleAttachTestAnswers(t.id)} disabled={attachingTestId === t.id}
                          className="px-3 py-1 bg-emerald-600 text-white rounded-lg text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50">
                          {attachingTestId === t.id ? 'Matching…' : 'Match answers'}
                        </button>
                        {!(attachTestResult && attachTestResult.testId === t.id) && (
                          <span className="text-[11px] text-muted-foreground">Fills every blank answer in this test at once.</span>
                        )}
                        {attachTestResult && attachTestResult.testId === t.id && (
                          <span className={`text-xs font-semibold ${attachTestResult.matched > 0 ? 'text-emerald-700' : 'text-amber-600'}`}>
                            {attachTestResult.matched > 0 ? '✓' : '⚠'} Matched {attachTestResult.matched} of {attachTestResult.total}
                            {attachTestResult.total - attachTestResult.matched > 0
                              ? ` · ${attachTestResult.total - attachTestResult.matched} still need an answer — open a passage below to fill them`
                              : ' — all answers set 🎉'}
                          </span>
                        )}
                        {!(attachTestResult && attachTestResult.testId === t.id) && t.missing_answers > 0 && (
                          <span className="text-amber-600 text-xs font-semibold">⚠ {t.missing_answers} still missing</span>
                        )}
                      </div>
                      {loadingDetailId === t.id && !testDetail[t.id] ? (
                        <p className="text-muted-foreground text-xs py-2">Loading contents…</p>
                      ) : !testDetail[t.id] || testDetail[t.id].groups.length === 0 ? (
                        <p className="text-muted-foreground text-xs py-2">No passages assigned yet. Extract a PDF into this test, or assign existing passages below.</p>
                      ) : (
                        testDetail[t.id].groups.map((g) => (
                          <div key={g.part} className="mb-3 last:mb-0">
                            <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Part {g.part} · {g.passages.length} passage{g.passages.length === 1 ? '' : 's'}</p>
                            <div className="space-y-1">
                              {g.passages.map((p) => {
                                const pExpanded = expandedPassageId === p.id
                                return (
                                  <div key={p.id} className="bg-white border rounded-lg">
                                    <div className="flex items-center justify-between gap-2 p-2 flex-wrap">
                                      <button onClick={() => setExpandedPassageId((cur) => (cur === p.id ? null : p.id))}
                                        className="flex items-center gap-2 min-w-0 text-left flex-1">
                                        <span className="text-gray-400 w-3 shrink-0">{pExpanded ? '▾' : '▸'}</span>
                                        <span className="font-medium truncate">{p.title || '(untitled)'}</span>
                                        {!p.is_active && <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 text-gray-500 shrink-0">Hidden</span>}
                                        <span className="text-muted-foreground text-xs shrink-0">{p.question_count}Q</span>
                                        {p.question_count > 0 && (p.missing_answers > 0
                                          ? <span className="text-amber-600 text-xs font-semibold shrink-0">⚠ {p.missing_answers} no answer</span>
                                          : <span className="text-emerald-600 text-xs font-semibold shrink-0">✓ answers</span>)}
                                      </button>
                                      <div className="flex items-center gap-2 shrink-0 text-xs font-semibold">
                                        <button onClick={() => openEdit(p.id)} className="text-blue-600 hover:underline">Edit</button>
                                        <button onClick={() => togglePassageActive(p)} className="text-gray-500 hover:text-gray-700">{p.is_active ? 'Hide' : 'Show'}</button>
                                        <button onClick={() => detachPassage(p)} className="text-amber-600 hover:text-amber-800">Detach</button>
                                        <button onClick={() => deletePassage(p)} className="text-red-500 hover:text-red-700">Delete</button>
                                      </div>
                                    </div>
                                    {pExpanded && (
                                      <div className="border-t px-3 py-2 space-y-2">
                                        {p.questions.length === 0 ? (
                                          <p className="text-muted-foreground text-xs">No questions.</p>
                                        ) : p.questions.map((q, qi) => {
                                          const noAnswer = !(q.correct_answer || '').trim()
                                          return (
                                            <div key={q.id} className="text-xs">
                                              <p className="font-medium text-gray-800">
                                                {qi + 1}. {q.content || '(no stem)'}
                                                {noAnswer && <span className="text-amber-600 font-semibold ml-1">⚠ no answer</span>}
                                              </p>
                                              {q.type === 'mcq' ? (
                                                <ul className="ml-4 mt-0.5">
                                                  {q.options.map((opt, oi) => {
                                                    const correct = !noAnswer && opt === q.correct_answer
                                                    return (
                                                      <li key={oi} className={correct ? 'text-emerald-700 font-semibold' : 'text-gray-600'}>
                                                        {correct ? '✓ ' : '• '}{opt}
                                                      </li>
                                                    )
                                                  })}
                                                </ul>
                                              ) : (
                                                <p className="ml-4 mt-0.5 text-gray-600">
                                                  Answer: {noAnswer ? <span className="text-amber-600">—</span> : <span className="text-emerald-700 font-semibold">{q.correct_answer}</span>}
                                                </p>
                                              )}
                                            </div>
                                          )
                                        })}
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
        {drafts.length > 0 && (
          <div className="mt-4 pt-4 border-t flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">Save extracted passages into:</span>
            <select
              value={draftTestId ?? ''}
              onChange={(e) => setDraftTestId(e.target.value ? Number(e.target.value) : null)}
              className="px-3 py-2 border rounded-lg text-sm"
            >
              <option value="">No test (standalone)</option>
              {tests.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
            </select>
          </div>
        )}
      </div>

      {/* Review / edit drafts (create flow) */}
      <div id="draft-review" />
      {drafts.length > 1 && (
        <div className="bg-white rounded-lg shadow p-4 mb-4 flex items-center justify-between gap-3 flex-wrap sticky top-2 z-10 border-2 border-emerald-200">
          <span className="text-sm font-semibold">{drafts.length} passages extracted — review each, then save them all at once.</span>
          <button onClick={saveAll} disabled={savingAll || savingIdx.size > 0}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50">
            {savingAll ? 'Saving all…' : `Save all ${drafts.length}`}
          </button>
        </div>
      )}
      {drafts.map((draft, pi) => (
        <div key={pi} className="bg-white rounded-lg shadow p-6 mb-8 space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="font-bold text-lg">Review & Edit ({pi + 1} of {drafts.length})</h2>
            <button onClick={() => discard(pi)} className="text-sm text-muted-foreground hover:text-gray-600">Discard</button>
          </div>

          <div className="grid md:grid-cols-3 gap-4">
            <label className="md:col-span-1">
              <span className="block text-sm font-semibold mb-1">Title</span>
              <input value={draft.title} onChange={(e) => updateDraft(pi, { title: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg" />
            </label>
            <label>
              <span className="block text-sm font-semibold mb-1">Part</span>
              <select value={draft.part} onChange={(e) => updateDraft(pi, { part: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg">
                <option value="A">Part A</option>
                <option value="B">Part B</option>
                <option value="C">Part C</option>
              </select>
            </label>
            <label>
              <span className="block text-sm font-semibold mb-1">Difficulty</span>
              <select value={draft.difficulty} onChange={(e) => updateDraft(pi, { difficulty: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg">
                <option value="beginner">Beginner</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </select>
            </label>
          </div>

          <label className="block">
            <span className="block text-sm font-semibold mb-1">Passage Body</span>
            <textarea value={draft.body} onChange={(e) => updateDraft(pi, { body: e.target.value })}
              rows={8} className="w-full px-3 py-2 border rounded-lg font-mono text-sm" />
          </label>

          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="font-bold">Questions ({draft.questions.length})</h3>
              <button
                onClick={() => updateDraft(pi, { questions: [...draft.questions, { content: '', type: 'mcq', options: ['', ''], correctIndex: 0, expectedAnswer: '' }] })}
                className="text-sm text-blue-600 font-semibold"
              >
                + Add question
              </button>
            </div>

            {draft.questions.map((q, qi) => (
              <div key={qi} className="border rounded-lg p-4 space-y-3">
                <div className="flex items-start gap-2">
                  <span className="font-bold text-muted-foreground mt-2">{qi + 1}.</span>
                  <textarea value={q.content} onChange={(e) => setQ(pi, qi, { content: e.target.value })}
                    rows={2} placeholder="Question stem" className="flex-1 px-3 py-2 border rounded-lg text-sm" />
                  <button onClick={() => toggleQType(pi, qi)}
                    className="text-xs font-semibold text-gray-500 hover:text-gray-700 border rounded-lg px-2 py-1.5 mt-1 shrink-0">
                    {q.type === 'mcq' ? 'Multiple choice' : 'Short answer'} ⇄
                  </button>
                  <button onClick={() => updateDraft(pi, { questions: draft.questions.filter((_, i) => i !== qi) })}
                    className="text-red-400 hover:text-red-600 text-sm mt-2">Remove</button>
                </div>

                {q.type === 'mcq' ? (
                  <>
                    <p className="text-xs text-gray-500 ml-6">Select the radio for the correct answer.</p>
                    {q.options.map((opt, oi) => (
                      <div key={oi} className="flex items-center gap-2 ml-6">
                        <input type="radio" name={`correct-${pi}-${qi}`} checked={q.correctIndex === oi}
                          onChange={() => setQ(pi, qi, { correctIndex: oi })} />
                        <input value={opt} onChange={(e) => setOpt(pi, qi, oi, e.target.value)}
                          placeholder={`Option ${oi + 1}`} className="flex-1 px-3 py-1.5 border rounded-lg text-sm" />
                        {q.options.length > 2 && (
                          <button
                            onClick={() => setQ(pi, qi, {
                              options: q.options.filter((_, i) => i !== oi),
                              correctIndex: q.correctIndex >= oi && q.correctIndex > 0 ? q.correctIndex - 1 : q.correctIndex,
                            })}
                            className="text-red-400 hover:text-red-600 text-xs"
                          >✕</button>
                        )}
                      </div>
                    ))}
                    <button onClick={() => setQ(pi, qi, { options: [...q.options, ''] })}
                      className="text-xs text-blue-600 font-semibold ml-6">+ Add option</button>
                  </>
                ) : (
                  <div className="ml-6">
                    <p className="text-xs text-gray-500 mb-1">Reference answer (AI grades the student's typed answer against this — wording doesn't need to match exactly).</p>
                    <input value={q.expectedAnswer} onChange={(e) => setQ(pi, qi, { expectedAnswer: e.target.value })}
                      placeholder="Expected answer" className="w-full px-3 py-1.5 border rounded-lg text-sm" />
                  </div>
                )}
              </div>
            ))}
          </div>

          <button onClick={() => handleSave(pi)} disabled={savingIdx.has(pi)}
            className="w-full py-3 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-700 disabled:opacity-50">
            {savingIdx.has(pi) ? 'Saving…' : 'Save Passage'}
          </button>
        </div>
      ))}

      {/* Edit an already-saved passage */}
      {editingPassage && (
        <div id="passage-editor" className="bg-white rounded-lg shadow p-6 mb-8 space-y-6 border-2 border-blue-200">
          <div className="flex items-center justify-between">
            <h2 className="font-bold text-lg">Editing: {editingPassage.title}</h2>
            <button onClick={closeEdit} className="text-sm text-muted-foreground hover:text-gray-600">Close</button>
          </div>

          <div className="grid md:grid-cols-3 gap-4">
            <label className="md:col-span-1">
              <span className="block text-sm font-semibold mb-1">Title</span>
              <input value={editingPassage.title} onChange={(e) => updateEdit({ title: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg" />
            </label>
            <label>
              <span className="block text-sm font-semibold mb-1">Part</span>
              <select value={editingPassage.part} onChange={(e) => updateEdit({ part: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg">
                <option value="A">Part A</option>
                <option value="B">Part B</option>
                <option value="C">Part C</option>
              </select>
            </label>
            <label>
              <span className="block text-sm font-semibold mb-1">Difficulty</span>
              <select value={editingPassage.difficulty} onChange={(e) => updateEdit({ difficulty: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg">
                <option value="beginner">Beginner</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </select>
            </label>
          </div>

          <div className="block">
            <span className="block text-sm font-semibold mb-1">Passage Body</span>
            {partASections.length > 1 ? (
              <div className="space-y-3">
                {partASections.map((s, si) => (
                  <div key={s.label} className="border rounded-lg p-3">
                    <span className="block text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Text {s.label}</span>
                    <textarea
                      value={s.lines.join('\n')}
                      onChange={(e) => {
                        const next = partASections.map((sec, i) => (i === si ? { ...sec, lines: e.target.value.split('\n') } : sec))
                        updateEdit({ body: joinPartASections(next) })
                      }}
                      rows={5} className="w-full px-3 py-2 border rounded-lg font-mono text-sm"
                    />
                    <div className="flex items-center gap-2 mt-2">
                      <input
                        value={regenInstruction[s.label] || ''}
                        onChange={(e) => setRegenInstruction((r) => ({ ...r, [s.label]: e.target.value }))}
                        placeholder='What should change? e.g. "make it about wound infection instead"'
                        className="flex-1 px-2 py-1 border rounded text-xs"
                      />
                      <button onClick={() => regenerateText(s.label)} disabled={regeneratingLabel === s.label}
                        className="text-xs font-semibold text-blue-600 hover:underline disabled:opacity-50 shrink-0">
                        {regeneratingLabel === s.label ? 'Regenerating…' : '✨ Regenerate'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <textarea value={editingPassage.body} onChange={(e) => updateEdit({ body: e.target.value })}
                rows={8} className="w-full px-3 py-2 border rounded-lg font-mono text-sm" />
            )}
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <label className={`text-xs font-semibold cursor-pointer ${uploadingImage ? 'text-gray-400' : 'text-blue-600 hover:underline'}`}>
                {uploadingImage ? 'Uploading…' : '+ Add image (figure / table snapshot)'}
                <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden"
                  disabled={uploadingImage}
                  onChange={(e) => { handleUploadImage(e.target.files?.[0] ?? null); e.target.value = '' }} />
              </label>
              <span className="text-[11px] text-muted-foreground">Inserts an <code>![figure](…)</code> line at the end — move it to where the figure should sit. Shows as a real image to students. Also renders tables written as Markdown pipe tables.</span>
            </div>
          </div>

          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="font-bold">Questions ({editingPassage.questions.length})</h3>
              <button
                onClick={() => setEditingPassage((p) => p && {
                  ...p,
                  questions: [...p.questions, { id: null, content: '', type: 'mcq', options: ['', ''], correctIndex: 0, expectedAnswer: '' }],
                })}
                className="text-sm text-blue-600 font-semibold"
              >
                + Add question
              </button>
            </div>

            {editingPassage.questions.map((q, qi) => (
              <div key={q.id ?? `new-${qi}`} className="border rounded-lg p-4 space-y-3">
                <div className="flex items-start gap-2">
                  <span className="font-bold text-muted-foreground mt-2">{qi + 1}.</span>
                  <textarea value={q.content} onChange={(e) => setEditQ(qi, { content: e.target.value })}
                    rows={2} placeholder="Question stem" className="flex-1 px-3 py-2 border rounded-lg text-sm" />
                  <button onClick={() => toggleEditQType(qi)}
                    className="text-xs font-semibold text-gray-500 hover:text-gray-700 border rounded-lg px-2 py-1.5 mt-1 shrink-0">
                    {q.type === 'mcq' ? 'Multiple choice' : 'Short answer'} ⇄
                  </button>
                </div>

                {(q.type === 'mcq' ? !q.options[q.correctIndex] : !q.expectedAnswer) && (
                  <p className="text-xs text-amber-600 ml-6 font-semibold">⚠ No answer yet</p>
                )}

                {q.type === 'mcq' ? (
                  <>
                    <p className="text-xs text-gray-500 ml-6">Select the radio for the correct answer.</p>
                    {q.options.map((opt, oi) => (
                      <div key={oi} className="flex items-center gap-2 ml-6">
                        <input type="radio" name={`edit-correct-${qi}`} checked={q.correctIndex === oi}
                          onChange={() => setEditQ(qi, { correctIndex: oi })} />
                        <input value={opt} onChange={(e) => setEditOpt(qi, oi, e.target.value)}
                          placeholder={`Option ${oi + 1}`} className="flex-1 px-3 py-1.5 border rounded-lg text-sm" />
                        {q.options.length > 2 && (
                          <button
                            onClick={() => setEditQ(qi, {
                              options: q.options.filter((_, i) => i !== oi),
                              correctIndex: q.correctIndex >= oi && q.correctIndex > 0 ? q.correctIndex - 1 : q.correctIndex,
                            })}
                            className="text-red-400 hover:text-red-600 text-xs"
                          >✕</button>
                        )}
                      </div>
                    ))}
                    <button onClick={() => setEditQ(qi, { options: [...q.options, ''] })}
                      className="text-xs text-blue-600 font-semibold ml-6">+ Add option</button>
                  </>
                ) : (
                  <div className="ml-6">
                    <p className="text-xs text-gray-500 mb-1">Reference answer (AI grades the student's typed answer against this).</p>
                    <input value={q.expectedAnswer} onChange={(e) => setEditQ(qi, { expectedAnswer: e.target.value })}
                      placeholder="Expected answer" className="w-full px-3 py-1.5 border rounded-lg text-sm" />
                  </div>
                )}
              </div>
            ))}
          </div>

          <button onClick={handleSaveEdit} disabled={savingEdit}
            className="w-full py-3 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-700 disabled:opacity-50">
            {savingEdit ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      )}

      {/* Passages not in any test — the "inbox": assign into a test, or delete */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between gap-3 mb-1 flex-wrap">
          <h2 className="font-bold">Passages not in any test ({unassignedRows.length})</h2>
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500">{selectedIds.size} selected</span>
              <button onClick={() => setSelectedIds(new Set())} className="text-xs text-gray-500 hover:text-gray-700">Clear</button>
              <button onClick={deleteSelected} disabled={bulkDeleting}
                className="px-3 py-1.5 bg-red-600 text-white rounded-lg text-xs font-semibold hover:bg-red-700 disabled:opacity-50">
                {bulkDeleting ? 'Deleting…' : `Delete ${selectedIds.size} selected`}
              </button>
            </div>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-4">These belong to no test yet — assign each into a test (so students get it), or delete it. Passages already in a test are managed in the drill-down above.</p>
        {unassignedRows.length === 0 ? (
          <p className="text-muted-foreground text-sm">Nothing here — every passage is in a test. 🎉</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-2 w-8">
                  <input type="checkbox"
                    checked={unassignedRows.length > 0 && selectedIds.size === unassignedRows.length}
                    ref={(el) => { if (el) el.indeterminate = selectedIds.size > 0 && selectedIds.size < unassignedRows.length }}
                    onChange={toggleSelectAll}
                    aria-label="Select all passages" />
                </th>
                <th className="py-2">Title</th>
                <th className="py-2">Part</th>
                <th className="py-2">Test</th>
                <th className="py-2">Active</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {unassignedRows.map((r) => (
                <tr key={r.id} className={`border-b last:border-0 ${selectedIds.has(r.id) ? 'bg-blue-50' : ''}`}>
                  <td className="py-2">
                    <input type="checkbox" checked={selectedIds.has(r.id)}
                      onChange={() => toggleSelect(r.id)} aria-label={`Select ${r.title}`} />
                  </td>
                  <td className="py-2 font-medium">{r.title}</td>
                  <td className="py-2">{r.part}</td>
                  <td className="py-2">
                    <select
                      value={r.test_id ?? ''}
                      onChange={(e) => assignPassage(r.id, e.target.value ? Number(e.target.value) : null)}
                      className="px-2 py-1 border rounded text-xs max-w-[160px]"
                    >
                      <option value="">— none —</option>
                      {tests.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
                    </select>
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => togglePassageActive(r)}
                      className={`text-xs font-semibold px-2 py-1 rounded ${r.is_active ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'}`}
                      title="Click to toggle whether students can see this passage"
                    >
                      {r.is_active ? 'Live' : 'Hidden'}
                    </button>
                  </td>
                  <td className="py-2">
                    <div className="flex items-center gap-3 justify-end">
                      <button onClick={() => openEdit(r.id)} disabled={loadingEditId === r.id}
                        className="text-blue-600 font-semibold text-xs hover:underline disabled:opacity-50">
                        {loadingEditId === r.id ? 'Loading…' : 'Edit'}
                      </button>
                      <button
                        onClick={() => setAttachOpenId(attachOpenId === r.id ? null : r.id)}
                        className="text-emerald-600 font-semibold text-xs hover:underline"
                      >
                        Attach Answers
                      </button>
                      <button onClick={() => deletePassage(r)}
                        className="text-red-500 hover:text-red-700 font-semibold text-xs">
                        Delete
                      </button>
                    </div>
                    {attachOpenId === r.id && (
                      <div className="mt-2 flex items-center gap-2 justify-end">
                        <input
                          type="file"
                          accept="application/pdf"
                          onChange={(e) => setAttachFile(e.target.files?.[0] ?? null)}
                          className="text-xs"
                        />
                        <button
                          onClick={() => handleAttachAnswers(r.id)}
                          disabled={attaching}
                          className="px-3 py-1 bg-emerald-600 text-white rounded-lg text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50"
                        >
                          {attaching ? 'Matching…' : 'Upload'}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* RC4.3.2.1: Version History modal -- strictly read-only, additive only.
          List view when viewingVersion is null, drilled-in snapshot view otherwise. */}
      {historyTest && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={closeVersionHistory}>
          <div
            className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {viewingVersion || viewingLoading || viewingError ? (
              <VersionSnapshotView
                testTitle={historyTest.title}
                detail={viewingVersion}
                loading={viewingLoading}
                error={viewingError}
                onBack={backToVersionList}
                onClose={closeVersionHistory}
              />
            ) : (
              <VersionHistoryList
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
function VersionHistoryList({
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
                  {v.published_by_display ? ` · by ${v.published_by_display}` : ''}
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
function VersionSnapshotView({
  testTitle, detail, loading, error, onBack, onClose,
}: {
  testTitle: string
  detail: VersionDetail | null
  loading: boolean
  error: string | null
  onBack: () => void
  onClose: () => void
}) {
  // Group passages by part (A/B/C) the same way the live detail drill-down does,
  // with their questions attached, so a historical snapshot reads the same way
  // an admin already reads the live test.
  const groups = useMemo(() => {
    const snap = detail?.snapshot
    if (!snap || !Array.isArray(snap.passages)) return []
    const qByPassage: Record<number, ReadingSnapshotQuestion[]> = {}
    for (const q of snap.questions || []) {
      (qByPassage[q.passage_id] ||= []).push(q)
    }
    const byPart: Record<string, ReadingSnapshotPassage[]> = {}
    for (const p of snap.passages) (byPart[p.part] ||= []).push(p)
    const order: string[] = [
      ...ALL_PARTS,
      ...Object.keys(byPart).filter((p) => !(ALL_PARTS as readonly string[]).includes(p)),
    ]
    return order
      .filter((part) => byPart[part]?.length)
      .map((part) => ({
        part,
        passages: byPart[part].map((p) => ({ ...p, questions: qByPassage[p.passage_id] || [] })),
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
            <p className="text-muted-foreground text-sm py-2">This snapshot has no passages recorded.</p>
          ) : (
            groups.map((g) => (
              <div key={g.part} className="mb-4 last:mb-0">
                <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">
                  Part {g.part} · {g.passages.length} passage{g.passages.length === 1 ? '' : 's'}
                </p>
                <div className="space-y-2">
                  {g.passages.map((p) => (
                    <div key={p.passage_id} className="border rounded-lg p-3 bg-gray-50">
                      <p className="font-medium">{p.title || '(untitled)'}</p>
                      <p className="text-xs text-gray-500 mb-2">Difficulty: {p.difficulty || '—'}</p>
                      <p className="text-xs whitespace-pre-wrap text-gray-700 mb-3 max-h-40 overflow-y-auto border rounded bg-white p-2">
                        {p.body || '(no body)'}
                      </p>
                      {p.questions.length === 0 ? (
                        <p className="text-muted-foreground text-xs">No questions.</p>
                      ) : (
                        <div className="space-y-2">
                          {p.questions.map((q, qi) => (
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
