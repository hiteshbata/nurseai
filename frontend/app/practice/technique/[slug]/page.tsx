'use client'

import { useState, useEffect } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import toast from 'react-hot-toast'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

interface LessonContent {
  what: string
  why: string
  when: string
  how: string
  common_mistakes: string
  example: string
}

interface PracticeContent {
  passage?: string
  question?: string
  claim?: string
  options?: string[]
}

type Stage = 'guided' | 'independent' | 'exam_style'

interface Practice {
  id: number
  title: string
  instructions: string
  content: PracticeContent
  scoring_type: 'rule_based' | 'ai'
  difficulty: 'beginner' | 'intermediate' | 'exam'
  stage: Stage
}

interface Mastery {
  level: 'not_started' | 'practicing' | 'improving' | 'strong'
  attempts: number
  band: number | null
}

interface TechniqueDetail {
  id: number
  module: string
  slug: string
  name: string
  description: string
  learning_objective: string
  lesson_content: LessonContent
  difficulty: string
  estimated_minutes: number | null
  practice: Practice | null
  practices: Practice[]
  mastery: Mastery
}

interface AttemptResult {
  score: number | null
  feedback: Record<string, any>
  mistakes: Array<{ reason?: string; expected?: string; given?: string; mistake_type?: string; explanation?: string }>
  provider_failure: boolean
  mastery: Mastery
}

const MASTERY_LABELS: Record<Mastery['level'], string> = {
  not_started: 'Not Started',
  practicing: 'Practicing',
  improving: 'Improving',
  strong: 'Strong',
}

const STAGE_LABELS: Record<Stage, string> = {
  guided: 'Guided',
  independent: 'Independent',
  exam_style: 'Exam-style',
}

type Phase = 'lesson' | 'practice' | 'result'

export default function TechniqueDetailPage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const params = useParams<{ slug: string }>()
  const [phase, setPhase] = useState<Phase>('lesson')
  const [technique, setTechnique] = useState<TechniqueDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(false)
  const [answer, setAnswer] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [result, setResult] = useState<AttemptResult | null>(null)
  const [activePracticeId, setActivePracticeId] = useState<number | null>(null)

  const load = () => {
    setIsLoading(true)
    api.get(`/techniques/${params.slug}`)
      .then((res) => {
        setTechnique(res.data)
        setActivePracticeId(res.data.practice?.id ?? null)
      })
      .catch(() => setError(true))
      .finally(() => setIsLoading(false))
  }

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') load()
  }, [status, params.slug])

  const practices = technique?.practices ?? []
  const activePractice = practices.find((p) => p.id === activePracticeId) ?? technique?.practice ?? null
  const activeIndex = activePractice ? practices.findIndex((p) => p.id === activePractice.id) : -1
  const nextPractice = activeIndex >= 0 ? practices[activeIndex + 1] ?? null : null

  const startPractice = (practiceId?: number) => {
    if (practiceId !== undefined) setActivePracticeId(practiceId)
    setAnswer(null)
    setResult(null)
    setPhase('practice')
  }

  const submitAttempt = async () => {
    if (!technique || !activePractice || answer === null) {
      toast.error('Please choose an answer first')
      return
    }
    setIsSubmitting(true)
    try {
      const res = await api.post(`/techniques/${technique.slug}/attempts`, {
        micro_practice_id: activePractice.id,
        answer,
      })
      setResult(res.data)
      setTechnique((t) => (t ? { ...t, mastery: res.data.mastery } : t))
      setPhase('result')
    } catch {
      toast.error('Failed to submit your answer — please try again')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading technique...</div>
      </div>
    )
  }

  if (error || !technique) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-3xl mx-auto text-center py-16 bg-white rounded-lg shadow">
          <p className="text-xl text-gray-500 mb-2">Couldn't load this technique</p>
          <Link href="/practice/technique" className="text-primary font-semibold hover:underline">
            ← Back to Technique Practice
          </Link>
        </div>
      </div>
    )
  }

  const { lesson_content: lc } = technique

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-3xl mx-auto">
        <Link href="/practice/technique" className="text-sm text-gray-500 hover:text-gray-700">
          ← Back to Technique Practice
        </Link>

        <div className="flex items-start justify-between gap-4 mt-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-bold text-[#0F2356]">{technique.name}</h1>
            <p className="text-gray-500 mt-1">{technique.learning_objective}</p>
          </div>
          <span className="inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold bg-gray-100 text-gray-600 shrink-0">
            {MASTERY_LABELS[technique.mastery.level]}
          </span>
        </div>

        {phase === 'lesson' && (
          <div className="mt-8 space-y-4">
            <Card className="p-6"><h3 className="font-semibold text-gray-900 mb-2">What is it?</h3><p className="text-gray-700">{lc.what}</p></Card>
            <Card className="p-6"><h3 className="font-semibold text-gray-900 mb-2">Why it matters</h3><p className="text-gray-700">{lc.why}</p></Card>
            <Card className="p-6"><h3 className="font-semibold text-gray-900 mb-2">When to use it</h3><p className="text-gray-700">{lc.when}</p></Card>
            <Card className="p-6"><h3 className="font-semibold text-gray-900 mb-2">How to use it</h3><p className="text-gray-700">{lc.how}</p></Card>
            <Card className="p-6"><h3 className="font-semibold text-gray-900 mb-2">Common mistakes</h3><p className="text-gray-700">{lc.common_mistakes}</p></Card>
            <Card className="p-6 bg-primary/5 border-primary/10"><h3 className="font-semibold text-gray-900 mb-2">Example</h3><p className="text-gray-700">{lc.example}</p></Card>

            <Card className="p-6 text-center">
              {technique.practice ? (
                <>
                  <p className="text-gray-600 mb-4">Ready to try it yourself?</p>
                  <Button onClick={() => startPractice(technique.practice!.id)}>Start Practice</Button>
                  {practices.length > 1 && (
                    <p className="text-xs text-gray-400 mt-3">
                      {practices.length} practices available · starting with {STAGE_LABELS[technique.practice.stage]}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-gray-500">Practice for this technique is launching soon.</p>
              )}
            </Card>
          </div>
        )}

        {phase === 'practice' && activePractice && (
          <Card className="p-8 mt-8">
            <div className="flex items-center justify-between gap-3 mb-2">
              <h3 className="text-lg font-bold text-gray-900">{activePractice.title}</h3>
              <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-gray-100 text-gray-600 shrink-0">
                {STAGE_LABELS[activePractice.stage]}
              </span>
            </div>
            <p className="text-sm text-gray-500 mb-6">{activePractice.instructions}</p>

            {activePractice.content.passage && (
              <p className="text-gray-700 leading-relaxed whitespace-pre-line bg-gray-50 rounded-xl p-4 mb-6">
                {activePractice.content.passage}
              </p>
            )}
            {(activePractice.content.question || activePractice.content.claim) && (
              <p className="font-semibold text-gray-800 mb-4">
                {activePractice.content.question || `Claim: ${activePractice.content.claim}`}
              </p>
            )}

            <div className="space-y-2">
              {(activePractice.content.options || []).map((opt, i) => {
                const selected = answer === opt
                return (
                  <label
                    key={i}
                    className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition ${
                      selected ? 'border-primary bg-primary/5' : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <input type="radio" name="practice-answer" checked={selected} onChange={() => setAnswer(opt)} className="mt-1" />
                    <span className="text-gray-700 text-sm">{opt}</span>
                  </label>
                )
              })}
            </div>

            <Button onClick={submitAttempt} disabled={isSubmitting} className="w-full mt-8">
              {isSubmitting ? 'Grading...' : 'Submit Answer'}
            </Button>
          </Card>
        )}

        {phase === 'result' && result && (
          <Card className="p-8 mt-8">
            <div className="text-center mb-6">
              <div className={`text-4xl font-bold ${result.feedback.is_correct ? 'text-emerald-600' : 'text-amber-600'}`}>
                {result.score !== null ? `${result.score}/6` : 'Feedback unavailable'}
              </div>
              <div className="text-lg font-semibold text-gray-700 mt-2">
                {result.provider_failure
                  ? 'Your attempt was saved — feedback is temporarily unavailable.'
                  : result.feedback.is_correct
                  ? 'Correct!'
                  : 'Not quite — here\'s what to review'}
              </div>
            </div>

            {!result.provider_failure && result.feedback.is_correct === false && result.feedback.correct_answer && (
              <div className="rounded-xl bg-emerald-50 text-emerald-800 text-sm px-4 py-3 mb-4">
                Correct answer: {result.feedback.correct_answer}
              </div>
            )}
            {result.feedback.explanation && (
              <p className="text-sm text-gray-600 mb-2">{result.feedback.explanation}</p>
            )}
            {!result.feedback.is_correct && result.mistakes[0]?.explanation && (
              <div className="rounded-xl bg-amber-50 text-amber-800 text-sm px-4 py-3 mb-4">
                {result.mistakes[0].explanation}
              </div>
            )}
            {result.feedback.reasoning && (
              <p className="text-sm text-gray-600 mb-2">{result.feedback.reasoning}</p>
            )}
            {result.feedback.improvement_tip && (
              <div className="rounded-xl bg-sky-50 text-sky-800 text-sm px-4 py-3 mb-4">
                Tip: {result.feedback.improvement_tip}
              </div>
            )}

            <div className="flex gap-4 mt-6">
              {result.feedback.is_correct && nextPractice ? (
                <Button className="flex-1" onClick={() => startPractice(nextPractice.id)}>
                  Next Practice ({STAGE_LABELS[nextPractice.stage]})
                </Button>
              ) : (
                <Button className="flex-1" onClick={() => startPractice()}>Try Again</Button>
              )}
              <Button variant="outline" className="flex-1" onClick={() => router.push('/practice/technique')}>
                Back to Techniques
              </Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
