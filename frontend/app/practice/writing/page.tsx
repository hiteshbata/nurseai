'use client'

import { useState, useEffect } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

interface Scenario {
  id: number
  title: string
  setting: string
  difficulty: string
  nurse_card: {
    role?: string
    tasks?: string[]
  }
}

interface CriterionScore {
  score: number | null
  feedback: string
}

interface Feedback {
  scoring_failed?: boolean
  scores: Record<string, CriterionScore>
  overall_score: number | null
  estimated_oet_grade: string | null
  raw_total?: number | null
  top_strengths: string[]
  top_improvements: string[]
  corrected_version: string
}

// Official OET Writing ranges: Purpose is scored /3, every other criterion /7.
const CRITERIA: { key: string; label: string; max: number }[] = [
  { key: 'purpose', label: 'Purpose', max: 3 },
  { key: 'content', label: 'Content', max: 7 },
  { key: 'conciseness', label: 'Conciseness & Clarity', max: 7 },
  { key: 'genre_style', label: 'Genre & Style', max: 7 },
  { key: 'organization', label: 'Organisation & Layout', max: 7 },
  { key: 'language', label: 'Language', max: 7 },
]

const WORD_MIN = 120

function countWords(text: string) {
  const trimmed = text.trim()
  return trimmed ? trimmed.split(/\s+/).length : 0
}

function scoreColor(score: number | null, max: number) {
  if (score === null) return 'text-gray-400'
  const ratio = score / max
  if (ratio >= 0.66) return 'text-emerald-600'
  if (ratio >= 0.5) return 'text-amber-500'
  return 'text-red-500'
}

type Phase = 'select' | 'write' | 'result'

export default function WritingPracticePage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [phase, setPhase] = useState<Phase>('select')
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [writingText, setWritingText] = useState('')
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }

    if (status === 'authenticated') {
      loadScenarios()
    }
  }, [status])

  const loadScenarios = async () => {
    try {
      const response = await api.get('/writing/scenarios')
      setScenarios(response.data || [])
    } catch (error) {
      console.error('Failed to fetch scenarios:', error)
      toast.error('Failed to load writing scenarios')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSelectScenario = (scenario: Scenario) => {
    setSelectedScenario(scenario)
    setWritingText('')
    setFeedback(null)
    setPhase('write')
  }

  const handleBackToScenarios = () => {
    setSelectedScenario(null)
    setWritingText('')
    setFeedback(null)
    setPhase('select')
  }

  const handleSubmit = async () => {
    if (!selectedScenario) return
    if (!writingText.trim()) {
      toast.error('Please write something before submitting')
      return
    }

    if (countWords(writingText) < WORD_MIN) {
      toast.error(`Your letter is too short — aim for 180–200 words (at least ${WORD_MIN}).`)
      return
    }

    setIsSubmitting(true)
    try {
      const response = await api.post('/writing/submit', {
        scenario_id: selectedScenario.id,
        content: writingText,
      })

      setFeedback(response.data.feedback)
      setPhase('result')
      if (response.data.feedback?.scoring_failed) {
        toast.error('Scoring is temporarily unavailable — please try again shortly.')
      } else {
        toast.success('Response scored successfully!')
        trackEvent('score_viewed', {
          module: 'writing',
          scenario_id: selectedScenario.id,
          overall_score: response.data.feedback?.overall_score,
        })
      }
    } catch (error: any) {
      console.error('Failed to submit:', error)
      const errData = error.response?.data?.detail
      if (error.response?.status === 403 && errData?.upgrade_required) {
        toast.error(
          <div>
            <p className="font-semibold">Writing practice requires Pro or Elite plan</p>
            <a
              href="/upgrade"
              className="inline-block mt-2 bg-[#0F2356] text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-[#0F2356]/90"
            >
              Upgrade to Pro →
            </a>
          </div>,
          { duration: 8000 }
        )
      } else {
        toast.error(errData?.error || errData?.message || error.response?.data?.detail || 'Failed to submit response')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading writing scenarios...</div>
      </div>
    )
  }

  if (phase === 'select') {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-3xl font-bold text-[#0F2356]">Writing Practice</h1>
          <p className="text-gray-500 mt-1">Choose a scenario to write an OET-style letter</p>

          {scenarios.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-lg shadow mt-8">
              <p className="text-xl text-gray-500 mb-2">No writing scenarios available</p>
              <p className="text-gray-400">Ask an admin to create writing scenarios</p>
            </div>
          ) : (
            <div className="grid md:grid-cols-2 gap-6 mt-8">
              {scenarios.map((s) => {
                const tasks = s.nurse_card?.tasks || []
                const difficultyBadge =
                  s.difficulty === 'easy' || s.difficulty === 'beginner'
                    ? 'bg-emerald-100 text-emerald-700'
                    : s.difficulty === 'hard' || s.difficulty === 'advanced'
                    ? 'bg-red-100 text-red-700'
                    : 'bg-amber-100 text-amber-700'
                return (
                  <Card
                    key={s.id}
                    className="p-6 flex flex-col gap-4 hover:shadow-md transition-all"
                  >
                    <span className={`px-3 py-1 rounded-full text-xs font-semibold w-fit ${difficultyBadge}`}>
                      {s.difficulty}
                    </span>
                    <h3 className="text-xl font-bold text-primary">{s.title}</h3>
                    <p className="text-gray-600 text-sm line-clamp-3 leading-relaxed">{s.setting}</p>
                    {tasks.length > 0 && (
                      <p className="text-sm text-gray-500">{tasks.length} writing tasks</p>
                    )}
                    <Button onClick={() => handleSelectScenario(s)} className="w-full">
                      Start Writing →
                    </Button>
                  </Card>
                )
              })}
            </div>
          )}
        </div>
      </div>
    )
  }

  if (phase === 'write' && selectedScenario) {
    const task = selectedScenario.nurse_card?.role || ''
    const words = countWords(writingText)
    const wordTone = words === 0 ? 'text-gray-400' : words < WORD_MIN ? 'text-amber-600' : words > 200 ? 'text-amber-600' : 'text-emerald-600'
    return (
      <div className="min-h-screen bg-gray-50 py-8 px-4">
        <div className="max-w-6xl mx-auto">
          <button onClick={handleBackToScenarios} className="text-sm text-gray-500 hover:text-gray-700 mb-4">
            ← Back to scenarios
          </button>

          {/* Exam header — informational, mirrors the real paper (no live timer) */}
          <div className="mb-6">
            <p className="text-xs font-semibold tracking-widest text-primary uppercase">OET Writing sub-test · Nursing</p>
            <h2 className="text-2xl font-bold text-gray-900">{selectedScenario.title}</h2>
            <p className="text-sm text-gray-500 mt-1">Reading time 5 minutes · Writing time 40 minutes · Body approximately 180–200 words</p>
          </div>

          <div className="grid lg:grid-cols-2 gap-6 items-start">
            {/* Case notes — styled like the exam paper */}
            <Card className="p-0 overflow-hidden lg:sticky lg:top-6">
              <div className="bg-gray-900 text-white text-xs font-bold px-4 py-2 tracking-widest">NOTES</div>
              <div className="p-6 max-h-[65vh] overflow-y-auto">
                <p className="text-[15px] text-gray-800 leading-relaxed whitespace-pre-wrap">{selectedScenario.setting}</p>
              </div>
            </Card>

            {/* Task + answer */}
            <div className="space-y-6">
              <Card className="p-6">
                <p className="text-xs font-bold tracking-widest text-gray-500 uppercase mb-2">Writing Task</p>
                <p className="text-gray-800 leading-relaxed whitespace-pre-wrap">{task}</p>
                <ul className="mt-4 space-y-1.5 text-sm text-gray-600">
                  <li className="flex gap-2"><span className="text-primary">•</span> Expand the relevant notes into complete sentences</li>
                  <li className="flex gap-2"><span className="text-primary">•</span> Do not use note form</li>
                  <li className="flex gap-2"><span className="text-primary">•</span> Use letter format</li>
                </ul>
              </Card>

              <Card className="p-6">
                <label htmlFor="writing" className="block text-sm font-semibold text-gray-700 mb-2">
                  Your Letter
                </label>
                <textarea
                  id="writing"
                  value={writingText}
                  onChange={(e) => setWritingText(e.target.value)}
                  className="w-full h-80 px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-emerald-100 focus:border-emerald-500 outline-none resize-y leading-relaxed"
                  placeholder="Dear ...,&#10;&#10;Write your letter here."
                />
                <div className={`text-sm mt-2 ${wordTone}`}>
                  {words} words {words === 0 ? '' : words < WORD_MIN ? '— aim for 180–200' : words > 200 ? '— a little long, aim for 180–200' : '✓'}
                </div>

                <Button onClick={handleSubmit} disabled={isSubmitting} className="w-full mt-4">
                  {isSubmitting ? 'Scoring...' : 'Submit for Scoring'}
                </Button>
              </Card>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (phase === 'result' && feedback) {
    if (feedback.scoring_failed) {
      return (
        <div className="min-h-screen bg-gray-50 py-12 px-4">
          <Card className="max-w-2xl mx-auto text-center p-8">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Scoring is temporarily unavailable</h2>
            <p className="text-gray-500 mb-6">Your letter was saved, but we couldn&apos;t generate feedback right now. Please try again shortly.</p>
            <div className="flex gap-4 justify-center">
              <Button onClick={() => setPhase('write')}>
                Try Again
              </Button>
              <Button variant="outline" onClick={handleBackToScenarios}>
                Back to Scenarios
              </Button>
            </div>
          </Card>
        </div>
      )
    }

    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <Card className="p-8 mb-6">
            <div className="text-center mb-8">
              <div className="text-5xl font-bold text-emerald-600">Grade {feedback.estimated_oet_grade}</div>
              <div className="text-lg font-semibold text-emerald-700 mt-2">
                Estimated OET score: {feedback.overall_score}/500
              </div>
              <div className="text-xs text-gray-400 mt-1">Approximate — for practice guidance only</div>
            </div>

            <div className="grid md:grid-cols-2 gap-4 mb-8">
              {CRITERIA.map(({ key, label, max }) => {
                const c = feedback.scores[key] || { score: null, feedback: '' }
                return (
                  <div key={key} className="rounded-xl bg-gray-50 p-4">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <p className="text-sm font-semibold text-[#0F2356]">{label}</p>
                      <span className={`text-sm font-bold shrink-0 ${scoreColor(c.score, max)}`}>
                        {c.score ?? '—'}/{max}
                      </span>
                    </div>
                    {c.feedback && <p className="text-xs text-gray-600 leading-relaxed">{c.feedback}</p>}
                  </div>
                )
              })}
            </div>

            {feedback.top_strengths?.length > 0 && (
              <div className="bg-emerald-50 p-4 rounded-lg mb-4">
                <h4 className="font-bold text-emerald-700 mb-2">Top Strengths</h4>
                <ul className="list-disc list-inside space-y-1">
                  {feedback.top_strengths.map((s, i) => (
                    <li key={i} className="text-sm text-emerald-800">{s}</li>
                  ))}
                </ul>
              </div>
            )}

            {feedback.top_improvements?.length > 0 && (
              <div className="bg-amber-50 p-4 rounded-lg mb-4">
                <h4 className="font-bold text-amber-700 mb-2">Areas to Improve</h4>
                <ul className="list-disc list-inside space-y-1">
                  {feedback.top_improvements.map((s, i) => (
                    <li key={i} className="text-sm text-amber-800">{s}</li>
                  ))}
                </ul>
              </div>
            )}

            {feedback.corrected_version && (
              <div className="bg-gray-50 p-4 rounded-lg">
                <h4 className="font-bold text-gray-700 mb-2">Improved Version</h4>
                <p className="text-gray-700 whitespace-pre-line text-sm leading-relaxed">{feedback.corrected_version}</p>
              </div>
            )}
          </Card>

          <div className="flex gap-4">
            <Button className="flex-1" onClick={handleBackToScenarios}>
              Try Another Scenario
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
