'use client'

import { useState, useEffect, useRef } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api, { isUpgradeRequiredError } from '@/lib/api'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { UpgradeRequired } from '@/components/UpgradeRequired'
import { FullTestCard } from '@/components/practice/FullTestCard'
import DictionaryLookup from '@/components/DictionaryLookup'
import AnswerExplanation from '@/components/reading/AnswerExplanation'
import { WeakSpots } from '@/components/practice/WeakSpots'
import { stripLeadingQuestionNumber, partASubgroup, PART_A_SUBGROUP_LABEL } from '@/lib/utils'

interface PassageSummary {
  id: number
  title: string
  part: string
  difficulty: string
}

interface Question {
  id: number
  content: string
  type: 'mcq' | 'short_answer'
  options: string[]
}

interface PassageDetail extends PassageSummary {
  body: string
  questions: Question[]
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
  words_per_minute: number | null
}

interface Highlight {
  start: number
  end: number
}

type Phase = 'select' | 'read' | 'result'

/** Character offset of a Range boundary relative to `root`, walking all text
 * nodes underneath it. Works even once highlights split the text into
 * multiple <mark>/<span> nodes, unlike raw Range.startOffset. */
function getCharacterOffsetWithin(root: Node, boundaryNode: Node, boundaryOffset: number): number {
  let total = 0
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let current: Node | null
  while ((current = walker.nextNode())) {
    if (current === boundaryNode) return total + boundaryOffset
    total += current.textContent?.length ?? 0
  }
  return total
}

function splitWithHighlights(body: string, highlights: Highlight[]) {
  if (highlights.length === 0) return [{ text: body, highlightIndex: -1 }]
  const sorted = highlights
    .map((h, origIndex) => ({ ...h, origIndex }))
    .sort((a, b) => a.start - b.start)
  const segments: { text: string; highlightIndex: number }[] = []
  let cursor = 0
  for (const h of sorted) {
    if (h.start > cursor) segments.push({ text: body.slice(cursor, h.start), highlightIndex: -1 })
    if (h.end > cursor) {
      segments.push({ text: body.slice(Math.max(h.start, cursor), h.end), highlightIndex: h.origIndex })
      cursor = h.end
    }
  }
  if (cursor < body.length) segments.push({ text: body.slice(cursor), highlightIndex: -1 })
  return segments
}

export default function ReadingPracticePage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [phase, setPhase] = useState<Phase>('select')
  const [tests, setTests] = useState<Array<{ id: number; title: string; passage_count: number }>>([])
  const [completedTestIds, setCompletedTestIds] = useState<Set<number>>(new Set())
  const [passage, setPassage] = useState<PassageDetail | null>(null)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [result, setResult] = useState<SubmitResult | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [readStartedAt, setReadStartedAt] = useState<number | null>(null)
  const [highlights, setHighlights] = useState<Highlight[]>([])
  const [note, setNote] = useState('')
  const [savingNotes, setSavingNotes] = useState(false)
  const [upgradeRequired, setUpgradeRequired] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      api.get('/reading/tests')
        .then((res) => setTests(res.data || []))
        .catch((error) => {
          if (isUpgradeRequiredError(error)) setUpgradeRequired(true)
        })
        .finally(() => setIsLoading(false))
      api.get('/reading/tests/completed-ids')
        .then((res) => setCompletedTestIds(new Set(res.data || [])))
        .catch(() => {})
    }
  }, [status])

  const openPassage = async (id: number) => {
    setIsLoading(true)
    try {
      const res = await api.get(`/reading/passages/${id}`)
      setPassage(res.data)
      setAnswers({})
      setResult(null)
      setReadStartedAt(Date.now())
      setPhase('read')
      try {
        const notesRes = await api.get(`/reading/passages/${id}/notes`)
        setHighlights(notesRes.data.highlights || [])
        setNote(notesRes.data.note || '')
      } catch {
        setHighlights([])
        setNote('')
      }
    } catch (error) {
      if (!isUpgradeRequiredError(error)) toast.error('Failed to open passage')
    } finally {
      setIsLoading(false)
    }
  }

  const backToList = () => {
    setPassage(null)
    setAnswers({})
    setResult(null)
    setHighlights([])
    setNote('')
    setPhase('select')
  }

  const persistNotes = async (nextHighlights: Highlight[], nextNote: string) => {
    if (!passage) return
    setSavingNotes(true)
    try {
      await api.put(`/reading/passages/${passage.id}/notes`, { highlights: nextHighlights, note: nextNote })
    } catch (error) {
      if (!isUpgradeRequiredError(error)) toast.error('Failed to save your notes')
    } finally {
      setSavingNotes(false)
    }
  }

  const handleBodyMouseUp = () => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || sel.rangeCount === 0 || !bodyRef.current) return
    const text = sel.toString().trim()
    // Single words are handled by the double-click dictionary lookup instead —
    // otherwise looking up a word would also spuriously highlight it.
    if (!text || !/\s/.test(text)) return

    const range = sel.getRangeAt(0)
    if (!bodyRef.current.contains(range.commonAncestorContainer)) return
    const start = getCharacterOffsetWithin(bodyRef.current, range.startContainer, range.startOffset)
    const end = getCharacterOffsetWithin(bodyRef.current, range.endContainer, range.endOffset)
    sel.removeAllRanges()
    if (end <= start) return

    const next = [...highlights, { start, end }]
    setHighlights(next)
    persistNotes(next, note)
  }

  const removeHighlight = (index: number) => {
    const next = highlights.filter((_, i) => i !== index)
    setHighlights(next)
    persistNotes(next, note)
  }

  const handleSubmit = async () => {
    if (!passage) return
    if (Object.keys(answers).length < passage.questions.length) {
      toast.error('Please answer every question before submitting')
      return
    }
    setIsSubmitting(true)
    try {
      const res = await api.post('/reading/submit', {
        passage_id: passage.id,
        answers: passage.questions.map((q) => ({
          questionId: q.id,
          selectedOption: answers[q.id] ?? null,
        })),
        elapsed_seconds: readStartedAt ? Math.round((Date.now() - readStartedAt) / 1000) : null,
      })
      setResult(res.data)
      setPhase('result')
    } catch (error) {
      if (!isUpgradeRequiredError(error)) toast.error('Failed to submit answers')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading reading practice...</div>
      </div>
    )
  }

  if (phase === 'select') {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-3xl font-bold text-[#0F2356]">Reading Practice</h1>
              <p className="text-gray-500 mt-1">Read an OET-style passage and answer the questions</p>
            </div>
            <Link href="/practice/reading/mistakes" className="text-sm font-semibold text-primary hover:underline">
              Review your mistakes →
            </Link>
          </div>

          <WeakSpots endpoint="/reading/weakness" />

          {upgradeRequired ? (
            <UpgradeRequired
              className="mt-8"
              title="Reading practice is a Pro/Elite feature"
              message="Upgrade your plan to unlock full OET reading passages and tests."
            />
          ) : tests.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-lg shadow mt-8">
              <p className="text-xl text-gray-500 mb-2">No reading tests available yet</p>
              <p className="text-muted-foreground">Check back soon — new tests are added regularly.</p>
            </div>
          ) : (
            <div className="mt-8">
              <h2 className="text-lg font-bold text-[#0F2356] mb-1">Full Reading Tests</h2>
              <p className="text-sm text-gray-500 mb-4">A complete OET paper — Part A, B and C in one timed session, just like the exam.</p>
              <div className="grid md:grid-cols-2 gap-6">
                {tests.map((t) => (
                  <FullTestCard
                    key={t.id}
                    title={t.title}
                    meta="Parts A + B + C · 60 min"
                    completed={completedTestIds.has(t.id)}
                    onStart={() => router.push(`/practice/reading/test/${t.id}`)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  if (phase === 'read' && passage) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <button onClick={backToList} className="text-sm text-gray-500 hover:text-gray-700 mb-4">
            ← Back to passages
          </button>

          <Card className="p-8 mb-6">
            <span className="inline-block bg-primary/10 text-primary px-3 py-1 rounded-full text-sm font-semibold mb-4">
              Reading — Part {passage.part}
            </span>
            <h2 className="text-2xl font-bold text-gray-900 mb-4">{passage.title}</h2>
            <DictionaryLookup>
              <div
                ref={bodyRef}
                onMouseUp={handleBodyMouseUp}
                className="text-gray-700 leading-relaxed whitespace-pre-line"
              >
                {splitWithHighlights(passage.body, highlights).map((seg, i) =>
                  seg.highlightIndex === -1 ? (
                    <span key={i}>{seg.text}</span>
                  ) : (
                    <mark
                      key={i}
                      className="bg-amber-200 cursor-pointer rounded px-0.5"
                      title="Click to remove highlight"
                      onClick={() => removeHighlight(seg.highlightIndex)}
                    >
                      {seg.text}
                    </mark>
                  )
                )}
              </div>
            </DictionaryLookup>
            <p className="text-xs text-muted-foreground mt-3">Double-click a word for a definition. Select a phrase to highlight it — click a highlight to remove it.</p>
          </Card>

          <Card className="p-8 mb-6">
            <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">Your notes</h3>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              onBlur={() => persistNotes(highlights, note)}
              placeholder="Jot down anything you want to remember about this passage..."
              rows={3}
              className="w-full px-4 py-2 border border-gray-200 rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none text-sm"
            />
            {savingNotes && <p className="text-xs text-muted-foreground mt-1">Saving…</p>}
          </Card>

          <Card className="p-8">
            <h3 className="text-lg font-bold text-gray-900 mb-6">Questions</h3>
            <div className="space-y-8">
              {(passage.part === 'A'
                ? (['matching', 'phrase', 'completion'] as const)
                    .map((g) => ({ g, questions: passage.questions.filter((q) => partASubgroup(q, q.content) === g) }))
                    .filter((grp) => grp.questions.length > 0)
                : [{ g: null, questions: passage.questions }]
              ).map(({ g, questions }) => (
                <div key={g ?? 'all'}>
                  {g && (
                    <p className="text-xs font-semibold text-primary uppercase tracking-wide mb-4">{PART_A_SUBGROUP_LABEL[g]}</p>
                  )}
                  <div className="space-y-8">
                    {questions.map((q) => {
                      const qi = passage.questions.indexOf(q)
                      return (
                        <div key={q.id}>
                          <p className="font-semibold text-gray-800 mb-3">
                            {qi + 1}. {stripLeadingQuestionNumber(q.content)}
                          </p>
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
                                return (
                                  <label
                                    key={oi}
                                    className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition ${
                                      selected ? 'border-primary bg-primary/5' : 'border-gray-200 hover:border-gray-300'
                                    }`}
                                  >
                                    <input
                                      type="radio"
                                      name={`q-${q.id}`}
                                      checked={selected}
                                      onChange={() => setAnswers((a) => ({ ...a, [q.id]: opt }))}
                                      className="mt-1"
                                    />
                                    <span className="text-gray-700 text-sm">{opt}</span>
                                  </label>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>

            <Button onClick={handleSubmit} disabled={isSubmitting} className="w-full mt-8">
              {isSubmitting ? 'Grading...' : 'Submit Answers'}
            </Button>
          </Card>
        </div>
      </div>
    )
  }

  if (phase === 'result' && result && passage) {
    const byId = new Map(result.results.map((r) => [r.questionId, r]))
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <Card className="p-8 mb-6">
            <div className="text-center mb-8">
              <div className="text-4xl font-bold text-emerald-600">{result.score}/6</div>
              <div className="text-lg font-semibold text-emerald-700 mt-2">
                {result.correct} of {result.total} correct
              </div>
              {result.words_per_minute && (
                <div className="text-sm text-muted-foreground mt-1">Reading speed: {result.words_per_minute} words/minute</div>
              )}
            </div>

            <div className="space-y-6">
              {passage.questions.map((q, qi) => {
                const r = byId.get(q.id)
                return (
                  <div key={q.id} className="rounded-xl bg-gray-50 p-4">
                    <p className="font-semibold text-gray-800 mb-2">
                      {qi + 1}. {stripLeadingQuestionNumber(q.content)}
                    </p>
                    {q.type === 'short_answer' ? (
                      <div className="space-y-1">
                        <div className={`text-sm px-3 py-1.5 rounded-lg ${r?.is_correct ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}`}>
                          Your answer: {r?.selected || '(blank)'} {r?.is_correct ? '✓' : '✗'}
                        </div>
                        {!r?.is_correct && (
                          <div className="text-sm px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-800">
                            Reference answer: {r?.correct_answer}
                          </div>
                        )}
                        {r?.feedback && <p className="text-xs text-gray-500 px-3">{r.feedback}</p>}
                      </div>
                    ) : (
                      q.options.map((opt, oi) => {
                        const isAnswer = r?.correct_answer === opt
                        const isPicked = r?.selected === opt
                        return (
                          <div
                            key={oi}
                            className={`text-sm px-3 py-1.5 rounded-lg ${
                              isAnswer
                                ? 'bg-emerald-100 text-emerald-800 font-semibold'
                                : isPicked
                                ? 'bg-red-100 text-red-800'
                                : 'text-gray-600'
                            }`}
                          >
                            {opt}
                            {isAnswer && ' ✓'}
                            {isPicked && !isAnswer && ' ✗ (your answer)'}
                          </div>
                        )
                      })
                    )}
                    {!r?.is_correct && <AnswerExplanation questionId={q.id} passageBody={passage.body} />}
                  </div>
                )
              })}
            </div>
          </Card>

          <div className="flex gap-4">
            <Button className="flex-1" onClick={backToList}>
              Try Another Passage
            </Button>
            <Button variant="outline" className="flex-1" onClick={() => router.push('/dashboard')}>
              Go to Dashboard
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return null
}
