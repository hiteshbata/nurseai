'use client'

import { useState, useEffect, useMemo, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import ListeningAudioPlayer from '@/components/ListeningAudioPlayer'
import DictionaryLookup from '@/components/DictionaryLookup'
import { stripLeadingQuestionNumber } from '@/lib/utils'
import { getMockId, finishMockSection, useMockDeadline } from '@/lib/mock'

function fmt(sec: number) {
  const m = Math.floor(Math.max(0, sec) / 60)
  const s = Math.max(0, sec) % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

interface Question {
  id: number
  content: string
  type: 'mcq' | 'short_answer'
  options: string[]
}

interface Section {
  id: number
  title: string
  part: string
  audio_url: string | null
  body: string | null
  questions: Question[]
}

interface TestDetail {
  id: number
  title: string
  part_audio: Record<string, string | null>
  sections: Section[]
}

interface QuestionResult {
  questionId: number
  selected: string | null
  correct_answer: string
  is_correct: boolean
  feedback?: string
}

interface Turn { speaker: string; text: string }

interface SubmitResult {
  score: number
  correct: number
  total: number
  results: QuestionResult[]
  per_part: Record<string, number>
  transcripts: Record<string, Turn[] | string | null>
}

const PARTS = ['A', 'B', 'C'] as const

const PART_INTRO: Record<string, string> = {
  A: 'You will hear two extracts. In each, a health professional talks to a patient. Complete the notes with a word or short phrase as you listen. Each extract plays ONCE.',
  B: 'You will hear six short extracts from healthcare settings. For each, choose the answer (A, B or C) which fits best. Each extract plays ONCE.',
  C: 'You will hear two longer extracts — health professionals talking about their work. For each question, choose the answer (A, B or C) which fits best. Each extract plays ONCE.',
}

// Minimal Markdown for Part A notes: ## headings, - bullets, **bold**, blank
// lines separate blocks; everything else is a line of text. OET notes are short.
function NotesBody({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <div className="text-sm text-gray-700 space-y-1">
      {lines.map((line, i) => {
        const heading = line.match(/^\s*(#{1,6})\s+(.*\S)\s*$/)
        if (heading) {
          return <p key={i} className="font-bold text-gray-900 mt-3">{renderInline(heading[2])}</p>
        }
        const bullet = line.match(/^\s*[-*•]\s+(.*)$/)
        if (bullet) {
          return <p key={i} className="pl-4 relative before:content-['•'] before:absolute before:left-0 before:text-gray-400">{renderInline(bullet[1])}</p>
        }
        if (line.trim() === '') return <div key={i} className="h-2" />
        return <p key={i}>{renderInline(line)}</p>
      })}
    </div>
  )
}

function renderInline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) => {
    const m = part.match(/^\*\*([^*]+)\*\*$/)
    return m ? <strong key={i} className="font-semibold text-gray-900">{m[1]}</strong> : <span key={i}>{part}</span>
  })
}

function Transcript({ value }: { value: Turn[] | string | null }) {
  if (!value) return null
  if (typeof value === 'string') {
    return <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">{value}</p>
  }
  return (
    <div className="space-y-2 text-sm text-gray-700">
      {value.map((t, i) => (
        <p key={i}><span className="font-semibold text-gray-900">{t.speaker}:</span> {t.text}</p>
      ))}
    </div>
  )
}

export default function ListeningTestSessionPage() {
  const { id } = useParams<{ id: string }>()
  const { status } = useSupabaseSession()
  const router = useRouter()

  const [test, setTest] = useState<TestDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [stepIdx, setStepIdx] = useState(0)
  const [result, setResult] = useState<SubmitResult | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isPreview, setIsPreview] = useState(false)
  // Full Mock Test mode (?mock=<id>): a strict server-anchored countdown runs,
  // the section auto-submits at 0, the score is hidden, and the section is
  // reported to the mock orchestrator instead of showing a result.
  const [mockId, setMockId] = useState<string | null>(null)
  const autoSubmitted = useRef(false)
  const { deadlineMs } = useMockDeadline(mockId, 'listening')
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      const preview = new URLSearchParams(window.location.search).get('preview') === '1'
      setIsPreview(preview)
      setMockId(getMockId())
      const url = preview ? `/listening/admin/tests/${id}/preview` : `/listening/tests/${id}`
      api.get(url)
        .then((res) => setTest(res.data))
        .catch(() => toast.error(preview ? 'Preview failed — admin access required' : 'Failed to load test'))
        .finally(() => setIsLoading(false))
    }
  }, [status, id])

  const presentParts = useMemo(() => {
    if (!test) return []
    return PARTS.filter((p) => test.sections.some((s) => s.part === p))
  }, [test])

  const currentPart = presentParts[stepIdx]

  const sectionsFor = (part: string) => (test?.sections || []).filter((s) => s.part === part)
  const allQuestions = useMemo(() => (test?.sections || []).flatMap((s) => s.questions), [test])
  const answeredCount = allQuestions.filter((q) => (answers[q.id] ?? '').trim() !== '').length

  // OET Listening is one continuous answer sheet: questions 1-42 across Part A -> B -> C.
  const questionNumberById = useMemo(() => {
    const map = new Map<number, number>()
    let n = 0
    for (const part of PARTS) {
      for (const s of (test?.sections || []).filter((sec) => sec.part === part)) {
        for (const q of s.questions) map.set(q.id, ++n)
      }
    }
    return map
  }, [test])

  const handleSubmit = async () => {
    if (!test) return
    setIsSubmitting(true)
    try {
      const res = await api.post(`/listening/tests/${test.id}/submit`, {
        answers: allQuestions.map((q) => ({ questionId: q.id, selectedOption: answers[q.id] ?? null })),
      })
      if (mockId) {
        // In a mock the score stays hidden — report the section and move on.
        await finishMockSection(mockId, 'listening', { band: res.data.score, correct: res.data.correct, total: res.data.total })
        router.replace('/practice/mock')
        return
      }
      setResult(res.data)
      window.scrollTo(0, 0)
    } catch {
      toast.error('Failed to submit test')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Mock countdown to the server-anchored deadline; auto-submits at 0.
  useEffect(() => {
    if (!deadlineMs) return
    const tick = () => setSecondsLeft(Math.max(0, Math.round((deadlineMs - Date.now()) / 1000)))
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [deadlineMs])

  useEffect(() => {
    if (mockId && secondsLeft === 0 && !result && !autoSubmitted.current) {
      autoSubmitted.current = true
      handleSubmit()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mockId, secondsLeft, result])

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading test…</div>
      </div>
    )
  }

  if (!test || presentParts.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <Card className="max-w-lg mx-auto text-center p-8">
          <p className="text-lg text-gray-600 mb-4">This test has no content yet.</p>
          <Button onClick={() => router.push('/practice/listening')}>Back to Listening</Button>
        </Card>
      </div>
    )
  }

  const renderQuestion = (q: Question) => (
    <div key={q.id} className="mb-6">
      <p className="font-semibold text-gray-800 mb-2">{questionNumberById.get(q.id)}. {stripLeadingQuestionNumber(q.content)}</p>
      {q.type === 'short_answer' ? (
        <input
          type="text"
          value={answers[q.id] ?? ''}
          onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
          placeholder="Type what you hear"
          className="w-full px-4 py-2 border border-gray-200 rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
        />
      ) : (
        <div className="space-y-2">
          {q.options.map((opt, oi) => {
            const selected = answers[q.id] === opt
            const letter = String.fromCharCode(65 + oi) // A, B, C
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
            <div className="flex flex-wrap justify-center gap-3">
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
              {sectionsFor(part).map((s) => (
                <Card key={s.id} className="p-5 mb-4">
                  <p className="font-semibold text-gray-700 mb-3">{s.title}</p>
                  <div className="space-y-4">
                    {s.questions.map((q) => {
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
                        </div>
                      )
                    })}
                  </div>
                  {result.transcripts?.[s.id] && (
                    <details className="mt-4 group">
                      <summary className="cursor-pointer text-sm font-semibold text-primary">Show transcript</summary>
                      <div className="mt-2 rounded-xl bg-white border border-gray-100 p-4">
                        <DictionaryLookup>
                          <Transcript value={result.transcripts[s.id]} />
                        </DictionaryLookup>
                        <p className="text-xs text-gray-400 mt-3">Double-click any word for a quick definition</p>
                      </div>
                    </details>
                  )}
                </Card>
              ))}
            </div>
          ))}

          <div className="flex gap-4">
            <Button className="flex-1" onClick={() => router.push('/practice/listening')}>Back to Listening</Button>
            <Button variant="outline" className="flex-1" onClick={() => router.push('/dashboard')}>Dashboard</Button>
          </div>
        </div>
      </div>
    )
  }

  // ── SESSION ──
  const isLastStep = stepIdx === presentParts.length - 1

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {isPreview && (
          <div className="bg-blue-600 text-white rounded-xl px-4 py-2 text-sm font-semibold mb-4 flex items-center justify-between gap-3">
            <span>👁 Admin preview — what students see. Submitting is off; audio replay is unlocked for review.</span>
            <button onClick={() => window.close()} className="underline shrink-0">Close</button>
          </div>
        )}

        {/* Sticky header: title · part stepper · progress */}
        <div className="sticky top-0 z-10 pt-2 mb-6">
          <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-4">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <h1 className="text-lg font-bold text-[#0F2356] truncate">{test.title}</h1>
                <p className="text-[11px] text-gray-400 uppercase tracking-wide">{mockId ? 'Full Mock Test · Listening (1 of 3)' : 'Full OET Listening · Part A + B + C'}</p>
              </div>
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

              {/* Mock countdown (whole-section cap; the audio itself sets the real pace) */}
              {mockId && secondsLeft !== null && (
                <div className={`px-4 py-2 rounded-xl font-bold tabular-nums flex items-center gap-2 ${
                  secondsLeft <= 0 ? 'bg-red-100 text-red-700'
                  : secondsLeft <= 300 ? 'bg-amber-100 text-amber-700'
                  : 'bg-[#0F2356]/5 text-[#0F2356]'}`}>
                  <span aria-hidden>⏱</span>
                  <span className="text-base">{fmt(secondsLeft)}</span>
                </div>
              )}
            </div>
            <div className="mt-3">
              <div className="flex justify-between text-[11px] text-gray-400 mb-1">
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

        {/* Part intro */}
        <div className="rounded-2xl p-5 mb-4 bg-gradient-to-br from-[#0F2356] to-[#1c3a7a] text-white shadow-md">
          <p className="text-xs font-semibold uppercase tracking-widest text-blue-200 mb-1">Part {currentPart}</p>
          <p className="text-sm text-blue-50 leading-relaxed">{PART_INTRO[currentPart]}</p>
        </div>

        {/* Part instructions audio (the "In this part…" narration), if provided. */}
        {test.part_audio?.[currentPart] && (
          <div className="mb-6">
            <p className="text-xs font-semibold text-gray-500 mb-1">Part {currentPart} instructions</p>
            <ListeningAudioPlayer key={`intro-${currentPart}`} srcs={[test.part_audio[currentPart]!]} allowReplay={isPreview} />
          </div>
        )}

        {currentPart === 'A' ? (
          /* Part A: each extract = audio + notes (left) with its gap-fill inputs (right). */
          sectionsFor('A').map((s) => (
            <div key={s.id} className="mb-8">
              <p className="text-sm font-bold text-[#0F2356] mb-3">{s.title}</p>
              <div className="grid lg:grid-cols-2 gap-6 items-start">
                <div className="space-y-4 lg:sticky lg:top-28">
                  <ListeningAudioPlayer srcs={s.audio_url ? [s.audio_url] : []} allowReplay={isPreview} />
                  {s.body && (
                    <Card className="p-5">
                      <NotesBody text={s.body} />
                    </Card>
                  )}
                </div>
                <Card className="p-6">
                  {s.questions.map((q) => renderQuestion(q))}
                </Card>
              </div>
            </div>
          ))
        ) : (
          /* Part B (six short extracts, one MCQ each) and Part C (long extracts,
             several MCQs): audio on top, questions beneath. */
          sectionsFor(currentPart).map((s) => (
            <Card key={s.id} className="p-6 mb-6">
              <p className="font-bold text-gray-800 mb-3">{s.title}</p>
              <div className="mb-5"><ListeningAudioPlayer srcs={s.audio_url ? [s.audio_url] : []} allowReplay={isPreview} /></div>
              {s.questions.map((q) => renderQuestion(q))}
            </Card>
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
              {isPreview ? 'Preview (submit disabled)' : isSubmitting ? (mockId ? 'Submitting…' : 'Grading…') : mockId ? 'Finish Listening →' : 'Submit Test'}
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
