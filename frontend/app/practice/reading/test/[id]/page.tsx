'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useSupabaseSession } from '@/lib/supabase'
import api, { isUpgradeRequiredError } from '@/lib/api'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { UpgradeRequired } from '@/components/UpgradeRequired'
import { stripLeadingQuestionNumber, partASubgroup, PART_A_SUBGROUP_LABEL, splitPartATexts } from '@/lib/utils'
import { getMockId, finishMockSection } from '@/lib/mock'
import AnswerExplanation from '@/components/reading/AnswerExplanation'

interface Question {
  id: number
  content: string
  type: 'mcq' | 'short_answer'
  options: string[]
}

interface Passage {
  id: number
  title: string
  part: string
  body: string
  questions: Question[]
}

interface TestDetail {
  id: number
  title: string
  passages: Passage[]
}

interface QuestionResult {
  questionId: number
  selected: string | null
  correct_answer: string
  is_correct: boolean
  feedback?: string
}

interface SubmitResult {
  score: number
  correct: number
  total: number
  results: QuestionResult[]
  per_part: Record<string, number>
}

// Standard OET part instructions — identical on every paper, so hardcoded rather
// than stored per passage.
const PART_INTRO: Record<string, string> = {
  A: 'Look at the four texts, A–D. For questions that ask "which text", decide which text (A, B, C or D) the information comes from. For the others, answer with a word or short phrase from the texts. Time: 15 minutes.',
  B: 'There are six short extracts relating to the work of health professionals. For each question, choose the answer (A, B or C) which you think fits best according to the text.',
  C: 'There are longer texts about different aspects of healthcare. For each question, choose the answer (A, B, C or D) which you think fits best according to the text.',
}

const PART_SECONDS: Record<string, number> = { A: 15 * 60, BC: 45 * 60 }

function fmt(sec: number) {
  const m = Math.floor(Math.max(0, sec) / 60)
  const s = Math.max(0, sec) % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

const PARTS = ['A', 'B', 'C'] as const

// A Markdown separator row like `| --- | :--: |` — dashes/pipes/colons/space only.
const isTableSeparator = (l: string) => l.includes('-') && /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(l)
const splitCells = (l: string) => l.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((c) => c.trim())
const startsTable = (lines: string[], i: number) =>
  i + 1 < lines.length && lines[i].includes('|') && isTableSeparator(lines[i + 1])
// A markdown image on its own line: ![alt](url) -> the url, else null.
const imageLineUrl = (l: string): string | null => {
  const m = l.trim().match(/^!\[[^\]]*\]\((.+?)\)$/)
  return m ? m[1] : null
}
// A markdown heading line: "## Burn depth" -> {level, text}, else null.
const headingLine = (l: string): { level: number; text: string } | null => {
  const m = l.match(/^\s*(#{1,6})\s+(.*\S)\s*$/)
  return m ? { level: m[1].length, text: m[2] } : null
}
// Inline **bold** -> <strong>; newlines in plain segments are preserved by the
// parent's whitespace-pre-line. Keeps raw ** from ever showing to students.
function renderInline(text: string, keyPrefix: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) => {
    const m = part.match(/^\*\*([^*]+)\*\*$/)
    return m
      ? <strong key={`${keyPrefix}-${i}`} className="font-semibold text-gray-900">{m[1]}</strong>
      : <span key={`${keyPrefix}-${i}`}>{part}</span>
  })
}

/** Render passage body text: GitHub-style pipe tables become real <table>s, markdown
 * headings/bold render styled (never as raw ## / **), inline images show as <img>,
 * and everything else stays paragraphs with line breaks preserved. OET bodies are
 * short, so a line scan is plenty. */
function PassageBody({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: JSX.Element[] = []
  let i = 0
  let key = 0
  while (i < lines.length) {
    const heading = headingLine(lines[i])
    if (startsTable(lines, i)) {
      const header = splitCells(lines[i])
      i += 2 // skip header + separator
      const rows: string[][] = []
      while (i < lines.length && lines[i].includes('|') && !isTableSeparator(lines[i]) && lines[i].trim() !== '') {
        rows.push(splitCells(lines[i]))
        i++
      }
      blocks.push(
        <div key={key++} className="overflow-x-auto my-3">
          <table className="text-sm border border-gray-300 border-collapse">
            <thead>
              <tr>{header.map((h, hi) => <th key={hi} className="border border-gray-300 bg-gray-50 px-2 py-1 text-left font-semibold text-gray-800">{h}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>{header.map((_, ci) => <td key={ci} className="border border-gray-300 px-2 py-1 align-top text-gray-700">{r[ci] ?? ''}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    } else if (imageLineUrl(lines[i])) {
      // eslint-disable-next-line @next/next/no-img-element -- user-supplied Supabase URL, not a local asset
      blocks.push(<img key={key++} src={imageLineUrl(lines[i])!} alt="figure" className="max-w-full h-auto rounded border my-2" />)
      i++
    } else if (heading) {
      const cls = heading.level <= 2 ? 'font-bold text-gray-900 text-base mt-3' : 'font-semibold text-gray-800 mt-2'
      blocks.push(<p key={key++} className={cls}>{renderInline(heading.text, `h${key}`)}</p>)
      i++
    } else {
      const para: string[] = []
      while (i < lines.length && !startsTable(lines, i) && !imageLineUrl(lines[i]) && !headingLine(lines[i])) { para.push(lines[i]); i++ }
      const content = para.join('\n')
      if (content.trim() !== '') blocks.push(<p key={key++} className="whitespace-pre-line">{renderInline(content, `p${key}`)}</p>)
    }
  }
  return <div className="text-gray-700 text-sm leading-relaxed space-y-1">{blocks}</div>
}

/** A source text rendered like the real paper: an optional navy label bar
 * ("TEXT A", "TEXT 1"), a bold title, then the body. Shared by all three parts.
 * In admin preview, editId adds an "Edit" deep link into that passage's admin editor. */
function TextCard({ label, title, body, editId }: { label?: string; title?: string; body: string; editId?: number }) {
  const editLink = editId != null && (
    <a href={`/admin/reading?edit=${editId}`} className="text-xs font-normal underline shrink-0">✏ Edit</a>
  )
  return (
    <Card className="p-0 overflow-hidden">
      {label && (
        <div className="bg-[#0F2356] text-white px-4 py-2 text-sm font-bold tracking-wide flex items-center justify-between gap-2">
          <span>{label}</span>
          {editLink}
        </div>
      )}
      <div className="p-5">
        {(title || (!label && editId != null)) && (
          <div className="flex items-start justify-between gap-2 mb-2">
            {title && <h3 className="font-bold text-gray-900">{title}</h3>}
            {!label && <span className="text-blue-600">{editLink}</span>}
          </div>
        )}
        <PassageBody text={body} />
      </div>
    </Card>
  )
}

export default function ReadingTestSessionPage() {
  const { id } = useParams<{ id: string }>()
  const { status } = useSupabaseSession()
  const router = useRouter()

  const [test, setTest] = useState<TestDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [stepIdx, setStepIdx] = useState(0) // index into PARTS present in this test
  const [result, setResult] = useState<SubmitResult | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [upgradeRequired, setUpgradeRequired] = useState(false)
  // Admin preview (?preview=1): load the test via the admin preview endpoint so it
  // renders even while it's still a draft. Read-only — submitting is disabled.
  const [isPreview, setIsPreview] = useState(false)
  // Full Mock Test mode (?mock=<id>): timers turn strict (Part A locks at 15 min,
  // B&C auto-submits at 0), the result screen is skipped, and the section is
  // reported to the mock orchestrator which routes to the next section.
  const [mockId, setMockId] = useState<string | null>(null)
  const autoSubmitted = useRef(false)

  const startedAt = useRef<number>(Date.now())
  const [aLeft, setALeft] = useState(PART_SECONDS.A)
  const [bcLeft, setBcLeft] = useState(PART_SECONDS.BC)
  const bcStarted = useRef(false)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      // Read the flag off the URL directly (not useSearchParams) to avoid Next's
      // Suspense-boundary requirement on this already client-only page.
      const preview = new URLSearchParams(window.location.search).get('preview') === '1'
      setIsPreview(preview)
      setMockId(getMockId())
      const url = preview ? `/reading/admin/tests/${id}/preview` : `/reading/tests/${id}`
      api.get(url)
        .then((res) => setTest(res.data))
        .catch((error) => {
          if (isUpgradeRequiredError(error)) setUpgradeRequired(true)
          else toast.error(preview ? 'Preview failed — admin access required' : 'Failed to load test')
        })
        .finally(() => setIsLoading(false))
    }
  }, [status, id])

  // Which parts this test actually contains, in order.
  const presentParts = useMemo(() => {
    if (!test) return []
    return PARTS.filter((p) => test.passages.some((pg) => pg.part === p))
  }, [test])

  const currentPart = presentParts[stepIdx]

  // Part A countdown runs while on Part A. Part B&C share one countdown that
  // starts the moment the student first leaves Part A. Soft: hits 0, warns, never locks.
  useEffect(() => {
    if (result) return
    const t = setInterval(() => {
      if (currentPart === 'A') {
        setALeft((s) => s - 1)
      } else if (currentPart) {
        bcStarted.current = true
        setBcLeft((s) => s - 1)
      }
    }, 1000)
    return () => clearInterval(t)
  }, [currentPart, result])

  const passagesFor = (part: string) => (test?.passages || []).filter((p) => p.part === part)

  const allQuestions = useMemo(() => (test?.passages || []).flatMap((p) => p.questions), [test])
  const answeredCount = allQuestions.filter((q) => (answers[q.id] ?? '').trim() !== '').length

  // Real-paper numbering mirrors the two answer booklets: Part A is its own
  // booklet (Q1-20), while Parts B & C share the second booklet numbered
  // continuously (B = 1-6, C = 7-22). So restart the count at the A->B
  // boundary rather than running one sequence across the whole test.
  const questionNumberById = useMemo(() => {
    const map = new Map<number, number>()
    let aNum = 0
    let bcNum = 0
    for (const pg of test?.passages || []) {
      for (const q of pg.questions) {
        if (pg.part === 'A') map.set(q.id, ++aNum)
        else map.set(q.id, ++bcNum)
      }
    }
    return map
  }, [test])

  const handleSubmit = async () => {
    if (!test) return
    setIsSubmitting(true)
    try {
      const res = await api.post(`/reading/tests/${test.id}/submit`, {
        answers: allQuestions.map((q) => ({ questionId: q.id, selectedOption: answers[q.id] ?? null })),
        elapsed_seconds: Math.round((Date.now() - startedAt.current) / 1000),
      })
      if (mockId) {
        // In a mock the score stays hidden — report the section and move on.
        await finishMockSection(mockId, 'reading', { band: res.data.score, correct: res.data.correct, total: res.data.total })
        router.replace('/practice/mock')
        return
      }
      setResult(res.data)
      window.scrollTo(0, 0)
    } catch (error) {
      if (!isUpgradeRequiredError(error)) toast.error('Failed to submit test')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Strict mock timing. Part A locks and auto-advances at 15 min; the shared B&C
  // clock auto-submits at 0 (it governs both parts). Normal practice stays soft.
  // ponytail: reading's own A/BC client timers are the authority here, not the
  // server deadline — a mid-section refresh resets them. Acceptable for self-
  // practice; wire to the mock deadline if refresh-cheating ever matters.
  useEffect(() => {
    if (!mockId || result || !currentPart) return
    const onLast = stepIdx === presentParts.length - 1
    const remaining = currentPart === 'A' ? aLeft : bcLeft
    if (remaining > 0) return
    if (!onLast && currentPart === 'A') {
      setStepIdx((s) => Math.min(presentParts.length - 1, s + 1))
      window.scrollTo(0, 0)
    } else if (!autoSubmitted.current) {
      autoSubmitted.current = true
      handleSubmit()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mockId, aLeft, bcLeft, currentPart, result, stepIdx, presentParts.length])

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading test…</div>
      </div>
    )
  }

  if (upgradeRequired) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-lg mx-auto">
          <UpgradeRequired
            title="Reading tests are a Pro/Elite feature"
            message="Upgrade your plan to unlock full OET reading tests."
          />
        </div>
      </div>
    )
  }

  if (!test || presentParts.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <Card className="max-w-lg mx-auto text-center p-8">
          <p className="text-lg text-gray-600 mb-4">This test has no content yet.</p>
          <Button onClick={() => router.push('/practice/reading')}>Back to Reading</Button>
        </Card>
      </div>
    )
  }

  // ── RESULT ──
  if (result) {
    const byId = new Map(result.results.map((r) => [r.questionId, r]))
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <Card className="p-8 mb-6">
            <div className="text-center mb-6">
              <div className="text-4xl font-bold text-emerald-600">{result.score}/6</div>
              <div className="text-lg font-semibold text-emerald-700 mt-2">{result.correct} of {result.total} correct</div>
            </div>
            <div className="flex flex-wrap justify-center gap-3 mb-2">
              {Object.entries(result.per_part).map(([part, band]) => (
                <span key={part} className="px-3 py-1 rounded-full text-sm font-semibold bg-blue-100 text-blue-700">
                  Part {part}: {band}/6
                </span>
              ))}
            </div>
          </Card>

          {presentParts.map((part) => (
            <div key={part} className="mb-6">
              <h3 className="text-lg font-bold text-[#0F2356] mb-3">Part {part}</h3>
              {passagesFor(part).map((pg) => (
                <Card key={pg.id} className="p-5 mb-4">
                  <p className="font-semibold text-gray-700 mb-3">{pg.title}</p>
                  <div className="space-y-4">
                    {pg.questions.map((q) => {
                      const r = byId.get(q.id)
                      return (
                        <div key={q.id} className="rounded-xl bg-gray-50 p-3">
                          <p className="text-sm font-semibold text-gray-800 mb-1">{questionNumberById.get(q.id)}. {stripLeadingQuestionNumber(q.content)}</p>
                          <div className={`text-sm px-2 py-1 rounded ${r?.is_correct ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}`}>
                            Your answer: {r?.selected || '(blank)'} {r?.is_correct ? '✓' : '✗'}
                          </div>
                          {!r?.is_correct && (
                            <div className="text-sm px-2 py-1 mt-1 rounded bg-emerald-50 text-emerald-800">
                              Correct: {r?.correct_answer}
                            </div>
                          )}
                          {r?.feedback && <p className="text-xs text-gray-500 mt-1">{r.feedback}</p>}
                          {!r?.is_correct && <AnswerExplanation questionId={q.id} passageBody={pg.body} />}
                        </div>
                      )
                    })}
                  </div>
                </Card>
              ))}
            </div>
          ))}

          <div className="flex gap-4">
            <Button className="flex-1" onClick={() => router.push('/practice/reading')}>Back to Reading</Button>
            <Button variant="outline" className="flex-1" onClick={() => router.push('/dashboard')}>Dashboard</Button>
          </div>
        </div>
      </div>
    )
  }

  // ── SESSION ──
  const timeLeft = currentPart === 'A' ? aLeft : bcLeft
  const timerLabel = currentPart === 'A' ? 'Part A' : 'Parts B & C'
  const isLastStep = stepIdx === presentParts.length - 1

  const renderQuestion = (q: Question) => (
    <div key={q.id} className="mb-6">
      <p className="font-semibold text-gray-800 mb-2">{questionNumberById.get(q.id)}. {stripLeadingQuestionNumber(q.content)}</p>
      {q.type === 'short_answer' ? (
        <input
          type="text"
          value={answers[q.id] ?? ''}
          onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
          placeholder="Type your answer"
          className="w-full px-4 py-2 border border-gray-200 rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
        />
      ) : (
        <div className="space-y-2">
          {q.options.map((opt, oi) => {
            const selected = answers[q.id] === opt
            const letter = String.fromCharCode(65 + oi) // A, B, C, D
            return (
              <label key={oi} className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition focus-within:ring-2 focus-within:ring-primary/40 ${selected ? 'border-primary bg-primary/5 shadow-sm' : 'border-gray-200 hover:border-gray-300'}`}>
                <input type="radio" name={`q-${q.id}`} checked={selected}
                  onChange={() => setAnswers((a) => ({ ...a, [q.id]: opt }))} className="sr-only" />
                <span className={`w-6 h-6 rounded-lg flex items-center justify-center text-xs font-bold shrink-0 transition ${selected ? 'bg-primary text-white' : 'bg-gray-100 text-gray-500'}`}>{letter}</span>
                <span className="text-gray-700 text-sm pt-0.5">{opt}</span>
              </label>
            )
          })}
        </div>
      )}
    </div>
  )

  // Parts A and C use a two-column text|questions layout, so they want the
  // width. Part B's short extracts read fine in a narrower single column.
  const containerWidth = currentPart === 'B' ? 'max-w-4xl' : 'max-w-6xl'

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className={`${containerWidth} mx-auto`}>
        {isPreview && (
          <div className="bg-blue-600 text-white rounded-xl px-4 py-2 text-sm font-semibold mb-4 flex items-center justify-between gap-3">
            <span>👁 Admin preview — what students see. Submitting is off. Hit <strong>✏ Edit</strong> on any text to fix it.</span>
            <button onClick={() => window.close()} className="underline shrink-0">Close</button>
          </div>
        )}
        {/* Premium sticky header: title · part stepper · timer · progress */}
        <div className="sticky top-0 z-10 pt-2 mb-6">
          <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-4">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <h1 className="text-lg font-bold text-[#0F2356] truncate">{test.title}</h1>
                <p className="text-[11px] text-muted-foreground uppercase tracking-wide">{mockId ? 'Full Mock Test · Reading (2 of 3)' : 'Full OET Reading · Part A + B + C'}</p>
              </div>

              {/* Part A → B → C stepper */}
              <div className="flex items-center">
                {presentParts.map((p, idx) => {
                  const state = idx < stepIdx ? 'done' : idx === stepIdx ? 'current' : 'todo'
                  return (
                    <div key={p} className="flex items-center">
                      <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition ${
                        state === 'current' ? 'bg-[#0F2356] text-white ring-4 ring-[#0F2356]/10'
                        : state === 'done' ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-gray-100 text-gray-400'}`}>
                        {state === 'done' ? '✓' : p}
                      </span>
                      {idx < presentParts.length - 1 && <span className={`w-6 h-0.5 ${idx < stepIdx ? 'bg-emerald-300' : 'bg-gray-200'}`} />}
                    </div>
                  )
                })}
              </div>

              {/* Timer — greys→amber→red as it runs down */}
              <div
                role="timer"
                aria-live="off"
                aria-atomic="true"
                aria-label={`${timerLabel} time remaining: ${fmt(timeLeft)}`}
                className={`px-4 py-2 rounded-xl font-bold tabular-nums flex items-center gap-2 ${
                timeLeft <= 0 ? 'bg-red-100 text-red-700'
                : timeLeft <= 300 ? 'bg-amber-100 text-amber-700'
                : 'bg-[#0F2356]/5 text-[#0F2356]'}`}>
                <span aria-hidden>⏱</span>
                <span className="text-[11px] font-semibold uppercase tracking-wide">{timerLabel}</span>
                <span className="text-base">{fmt(timeLeft)}</span>
              </div>
            </div>

            {/* Progress bar */}
            <div className="mt-3">
              <div className="flex justify-between text-[11px] text-muted-foreground mb-1">
                <span>{answeredCount} of {allQuestions.length} answered</span>
                <span>{Math.round((answeredCount / Math.max(1, allQuestions.length)) * 100)}%</span>
              </div>
              <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-primary to-emerald-500 transition-all duration-300"
                  style={{ width: `${(answeredCount / Math.max(1, allQuestions.length)) * 100}%` }} />
              </div>
            </div>
          </div>
        </div>

        {timeLeft <= 0 && (
          <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-2 text-sm mb-4">
            Time is up for this section. In the real exam you'd stop here — but you can keep going for practice.
          </div>
        )}

        {/* Part intro — premium navy gradient banner */}
        <div className="rounded-2xl p-5 mb-6 bg-gradient-to-br from-[#0F2356] to-[#1c3a7a] text-white shadow-md">
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-200 mb-1">Part {currentPart}</p>
          <p className="text-sm text-blue-50 leading-relaxed">{PART_INTRO[currentPart]}</p>
        </div>

        {/* Part A: four source texts in labelled boxes on the left (like the
            real paper's separate Text Booklet), questions on the right. */}
        {currentPart === 'A' ? (
          (() => {
            const pg = passagesFor('A')[0]
            if (!pg) return null
            const texts = splitPartATexts(pg.body)
            const subgroups = (['matching', 'phrase', 'completion'] as const)
              .map((g) => ({ g, questions: pg.questions.filter((q) => partASubgroup(q, q.content) === g) }))
              .filter((grp) => grp.questions.length > 0)

            return (
              <div className="grid lg:grid-cols-2 gap-6 mb-6 items-start">
                {/* LEFT: texts, sticky + independently scrollable on desktop */}
                <div className="space-y-4 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:pr-1">
                  {texts.map((t, i) => (
                    <TextCard key={i} label={t.label.toUpperCase()} title={t.title} body={t.body} editId={isPreview && i === 0 ? pg.id : undefined} />
                  ))}
                </div>

                {/* RIGHT: the three question groups */}
                <div className="space-y-6">
                  {subgroups.map(({ g, questions }) => (
                    <Card key={g} className="p-6">
                      <p className="text-xs font-semibold text-primary uppercase tracking-wide mb-4">{PART_A_SUBGROUP_LABEL[g]}</p>
                      {questions.map((q) => renderQuestion(q))}
                    </Card>
                  ))}
                </div>
              </div>
            )
          })()
        ) : currentPart === 'C' ? (
          /* Part C: each long text in a labelled box on the left (sticky),
             its own question set on the right -- same exam feel as Part A. */
          passagesFor('C').map((pg, i) => (
            <div key={pg.id} className="grid lg:grid-cols-2 gap-6 mb-8 items-start">
              <div className="lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:pr-1">
                <TextCard label={`TEXT ${i + 1}`} title={pg.title} body={pg.body} editId={isPreview ? pg.id : undefined} />
              </div>
              <Card className="p-6">
                <p className="text-xs font-semibold text-primary uppercase tracking-wide mb-4">Choose the answer (A, B, C or D) which fits best according to the text.</p>
                {pg.questions.map((q) => renderQuestion(q))}
              </Card>
            </div>
          ))
        ) : (
          /* Part B: six short extracts, each a titled box with its one question
             directly beneath. */
          passagesFor('B').map((pg) => (
            <div key={pg.id} className="mb-6">
              <TextCard title={pg.title} body={pg.body} editId={isPreview ? pg.id : undefined} />
              <div className="mt-4 px-1">
                {pg.questions.map((q) => renderQuestion(q))}
              </div>
            </div>
          ))
        )}

        {/* Nav — in a mock there's no going back, so the Previous control is hidden. */}
        <div className="flex items-center justify-between gap-4">
          {mockId ? <span /> : (
            <Button variant="outline" disabled={stepIdx === 0} onClick={() => { setStepIdx((s) => Math.max(0, s - 1)); window.scrollTo(0, 0) }}>
              ← Previous part
            </Button>
          )}
          {isLastStep ? (
            <Button onClick={handleSubmit} disabled={isSubmitting || isPreview}>
              {isPreview ? 'Preview (submit disabled)' : isSubmitting ? (mockId ? 'Submitting…' : 'Grading…') : mockId ? 'Finish Reading →' : 'Submit Test'}
            </Button>
          ) : (
            <Button onClick={() => { setStepIdx((s) => s + 1); window.scrollTo(0, 0) }}>
              Next part →
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
