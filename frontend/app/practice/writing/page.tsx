'use client'

import { useState, useEffect } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import toast from 'react-hot-toast'

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
  top_strengths: string[]
  top_improvements: string[]
  corrected_version: string
}

const CRITERIA_LABELS: Record<string, string> = {
  purpose: 'Purpose',
  content: 'Content',
  conciseness: 'Conciseness & Clarity',
  genre_style: 'Genre & Style',
  organization: 'Organization',
  language: 'Language',
}

function scoreColor(score: number | null) {
  if (score === null) return 'text-gray-400'
  if (score >= 4) return 'text-emerald-600'
  if (score >= 3) return 'text-amber-500'
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

    if (writingText.length < 100) {
      toast.error('Please write at least 100 characters')
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
                  <div
                    key={s.id}
                    className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 flex flex-col gap-4 hover:shadow-md transition-all"
                  >
                    <span className={`px-3 py-1 rounded-full text-xs font-semibold w-fit ${difficultyBadge}`}>
                      {s.difficulty}
                    </span>
                    <h3 className="text-xl font-bold text-[#0F2356]">{s.title}</h3>
                    <p className="text-gray-600 text-sm line-clamp-3 leading-relaxed">{s.setting}</p>
                    {tasks.length > 0 && (
                      <p className="text-sm text-gray-500">{tasks.length} writing tasks</p>
                    )}
                    <button
                      onClick={() => handleSelectScenario(s)}
                      className="w-full bg-orange-600 text-white rounded-xl py-3 font-semibold text-sm hover:bg-orange-700 transition-colors"
                    >
                      Start Writing →
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    )
  }

  if (phase === 'write' && selectedScenario) {
    const tasks = selectedScenario.nurse_card?.tasks || []
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <button onClick={handleBackToScenarios} className="text-sm text-gray-500 hover:text-gray-700 mb-4">
            ← Back to scenarios
          </button>

          <div className="bg-white p-8 rounded-lg shadow mb-6">
            <span className="inline-block bg-orange-100 text-orange-800 px-3 py-1 rounded-full text-sm font-semibold mb-4">
              Writing Module
            </span>
            <h2 className="text-2xl font-bold text-gray-900 mb-4">{selectedScenario.title}</h2>

            <div className="mb-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Case Notes</p>
              <p className="text-gray-700 leading-relaxed whitespace-pre-line">{selectedScenario.setting}</p>
            </div>

            {tasks.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Your Task</p>
                <ol className="space-y-2">
                  {tasks.map((task, i) => (
                    <li key={i} className="flex gap-3 text-gray-700 text-sm">
                      <span className="shrink-0 w-5 h-5 rounded-full bg-orange-100 text-orange-700 text-xs font-bold flex items-center justify-center mt-0.5">
                        {i + 1}
                      </span>
                      <span>{task}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>

          <div className="bg-white p-8 rounded-lg shadow">
            <label htmlFor="writing" className="block text-sm font-semibold text-gray-700 mb-2">
              Your Letter (minimum 100 characters)
            </label>
            <textarea
              id="writing"
              value={writingText}
              onChange={(e) => setWritingText(e.target.value)}
              className="w-full h-64 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent outline-none resize-none"
              placeholder="Write your letter here..."
            />
            <div className="text-sm text-gray-500 mt-2">{writingText.length} characters</div>

            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="w-full mt-4 px-6 py-3 bg-orange-600 text-white rounded-lg font-semibold hover:bg-orange-700 transition disabled:opacity-50"
            >
              {isSubmitting ? 'Scoring...' : 'Submit for Scoring'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (phase === 'result' && feedback) {
    if (feedback.scoring_failed) {
      return (
        <div className="min-h-screen bg-gray-50 py-12 px-4">
          <div className="max-w-2xl mx-auto text-center bg-white p-8 rounded-lg shadow">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Scoring is temporarily unavailable</h2>
            <p className="text-gray-500 mb-6">Your letter was saved, but we couldn&apos;t generate feedback right now. Please try again shortly.</p>
            <div className="flex gap-4 justify-center">
              <button
                onClick={() => setPhase('write')}
                className="px-6 py-3 bg-orange-600 text-white rounded-lg font-semibold hover:bg-orange-700 transition"
              >
                Try Again
              </button>
              <button
                onClick={handleBackToScenarios}
                className="px-6 py-3 bg-gray-200 text-gray-800 rounded-lg font-semibold hover:bg-gray-300 transition"
              >
                Back to Scenarios
              </button>
            </div>
          </div>
        </div>
      )
    }

    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white p-8 rounded-lg shadow mb-6">
            <div className="text-center mb-8">
              <div className="text-4xl font-bold text-emerald-600">{feedback.overall_score}/6</div>
              <div className="text-lg font-semibold text-emerald-700 mt-2">
                Estimated Grade: {feedback.estimated_oet_grade}
              </div>
            </div>

            <div className="grid md:grid-cols-2 gap-4 mb-8">
              {Object.entries(CRITERIA_LABELS).map(([key, label]) => {
                const c = feedback.scores[key] || { score: null, feedback: '' }
                return (
                  <div key={key} className="rounded-xl bg-gray-50 p-4">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <p className="text-sm font-semibold text-[#0F2356]">{label}</p>
                      <span className={`text-sm font-bold shrink-0 ${scoreColor(c.score)}`}>
                        {c.score ?? '—'}/6
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
          </div>

          <div className="flex gap-4">
            <button
              onClick={handleBackToScenarios}
              className="flex-1 px-6 py-3 bg-orange-600 text-white rounded-lg font-semibold hover:bg-orange-700 transition"
            >
              Try Another Scenario
            </button>
            <button
              onClick={() => router.push('/dashboard')}
              className="flex-1 px-6 py-3 border border-[#0F2356] text-[#0F2356] rounded-lg font-semibold hover:bg-[#0F2356]/5 transition"
            >
              Go to Dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }

  return null
}
