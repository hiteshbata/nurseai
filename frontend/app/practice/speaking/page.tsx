'use client'

import { useState, useEffect, useCallback } from 'react'
import dynamic from 'next/dynamic'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import SelectPhase from './SelectPhase'
import {
  Scenario,
  ChatMessage,
  Submission,
  RecommendedScenario,
  Phase,
  SPEAKING_SESSION_KEY,
  AUTO_LISTEN_KEY,
  CAPTIONS_KEY,
  PREP_SECONDS,
} from './shared'

// Voice/mic hooks, VoiceOrb, and the briefing/conversation/result UI are all
// only needed once a scenario is picked -- deferring them out of the initial
// bundle keeps the scenario-selection screen (the page's actual LCP content)
// from waiting on ~1000 lines of session/audio code it doesn't use yet.
const SpeakingSession = dynamic(() => import('./SpeakingSession'), {
  ssr: false,
  loading: () => (
    <div className="min-h-screen bg-[#F8FAFC] flex items-center justify-center">
      <div className="size-8 rounded-full border-2 border-[#0F2356]/20 border-t-[#0F2356] animate-spin" />
    </div>
  ),
})

export default function SpeakingPage() {
  const { session: authSession, status } = useSupabaseSession()
  const router = useRouter()
  const [phase, setPhase] = useState<Phase>('select')
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null)
  const [filterSpecialty, setFilterSpecialty] = useState<string>('all')
  const [filterDifficulty, setFilterDifficulty] = useState<string>('all')
  const [filterStatus, setFilterStatus] = useState<'all' | 'completed' | 'not_tried'>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [completedScenarioIds, setCompletedScenarioIds] = useState<Set<number>>(new Set())
  const [recommendedScenarios, setRecommendedScenarios] = useState<RecommendedScenario[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [feedback, setFeedback] = useState<any>(null)
  const [pastSubmissions, setPastSubmissions] = useState<Submission[]>([])
  const [comparisonResult, setComparisonResult] = useState<any>(null)
  const [comparisonError, setComparisonError] = useState<string | null>(null)
  const [isComparing, setIsComparing] = useState(false)
  const [readingTime, setReadingTime] = useState(PREP_SECONDS)

  const [examSeconds, setExamSeconds] = useState(0)
  const [convHistory, setConvHistory] = useState<ChatMessage[]>([])
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [typedResponse, setTypedResponse] = useState('')
  const [pronunciationResult, setPronunciationResult] = useState<any>(null)
  const [isAssessingPronunciation, setIsAssessingPronunciation] = useState(false)
  const [pronunciationError, setPronunciationError] = useState(false)
  const [hasRestoredSession, setHasRestoredSession] = useState(false)
  const [pendingResume, setPendingResume] = useState<{ scenario: Scenario; parsed: any } | null>(null)
  // Defaults on (matches the auto-restart behavior this replaces); persisted
  // across sessions since it's a standing preference, not per-scenario state.
  const [autoListen, setAutoListen] = useState(true)
  // Defaults on -- captions are an accessibility aid, not an opt-in extra.
  const [captionsOn, setCaptionsOn] = useState(true)
  const [isEnding, setIsEnding] = useState(false)
  const [isScoring, setIsScoring] = useState(false)
  const [conversationError, setConversationError] = useState<string | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const saved = window.localStorage.getItem(AUTO_LISTEN_KEY)
    if (saved !== null) setAutoListen(saved === 'true')
    const savedCaptions = window.localStorage.getItem(CAPTIONS_KEY)
    if (savedCaptions !== null) setCaptionsOn(savedCaptions === 'true')
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(AUTO_LISTEN_KEY, String(autoListen))
  }, [autoListen])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(CAPTIONS_KEY, String(captionsOn))
  }, [captionsOn])

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      loadScenarios()
    }
  }, [status])

  useEffect(() => {
    if (scenarios.length === 0 || typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    const scenarioId = params.get('scenario')
    if (!scenarioId) {
      if (!hasRestoredSession) {
        try {
          const saved = window.localStorage.getItem(SPEAKING_SESSION_KEY)
          if (saved) {
            const parsed = JSON.parse(saved)
            const savedScenario = scenarios.find((s) => s.id === parsed.selectedScenarioId)
            if (savedScenario && parsed.phase && parsed.phase !== 'select') {
              setPendingResume({ scenario: savedScenario, parsed })
            }
          }
        } catch (e) {
          console.error('Failed to restore speaking session:', e)
          window.localStorage.removeItem(SPEAKING_SESSION_KEY)
        } finally {
          setHasRestoredSession(true)
        }
      }
      return
    }
    const match = scenarios.find((s) => s.id === parseInt(scenarioId, 10))
    if (match) {
      handleSelectScenario(match)
    }
    setHasRestoredSession(true)
  }, [scenarios, hasRestoredSession])

  useEffect(() => {
    if (typeof window === 'undefined' || !selectedScenario) return
    if (phase === 'select') {
      window.localStorage.removeItem(SPEAKING_SESSION_KEY)
      return
    }
    window.localStorage.setItem(SPEAKING_SESSION_KEY, JSON.stringify({
      phase,
      selectedScenarioId: selectedScenario.id,
      readingTime,
      examSeconds,
      convHistory,
      history,
      sessionId,
      feedback,
    }))
  }, [phase, selectedScenario, readingTime, examSeconds, convHistory, history, sessionId, feedback])

  useEffect(() => {
    if (phase !== 'briefing') return
    const timer = setInterval(() => {
      setReadingTime(prev => {
        if (prev <= 1) {
          clearInterval(timer)
          setExamSeconds(0)
          setPhase('conversation')
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [phase])

  useEffect(() => {
    if (phase !== 'conversation') return
    const timer = setInterval(() => {
      setExamSeconds(prev => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [phase])

  useEffect(() => {
    const handler = () => {
      const isFs = !!document.fullscreenElement
      const nav = document.querySelector('nav')
      if (nav) nav.classList.toggle('hidden', isFs)
    }
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  const loadScenarios = async () => {
    try {
      const res = await api.get('/speaking/scenarios')
      setScenarios(res.data || [])
    } catch (e) {
      console.error('Failed to load scenarios:', e)
    } finally {
      setIsLoading(false)
    }
    // Independent of each other and of the scenario list above -- fetching
    // them in parallel instead of sequentially cuts this page's
    // time-to-content (and LCP, since the real heading/grid render behind a
    // loading skeleton until this all resolves) roughly 3x on a cold cache.
    const [submissionsResult, recommendationsResult] = await Promise.allSettled([
      api.get('/submissions', { params: { module: 'speaking' } }),
      api.get('/speaking/scenarios/recommendations', { params: { limit: 3 } }),
    ])
    if (submissionsResult.status === 'fulfilled') {
      const ids: number[] = (submissionsResult.value.data || []).map((sub: Submission) => sub.scenario_id)
      setCompletedScenarioIds(new Set(ids))
    } else {
      console.error('Failed to load completed scenarios:', submissionsResult.reason)
    }
    if (recommendationsResult.status === 'fulfilled') {
      setRecommendedScenarios(recommendationsResult.value.data || [])
    } else {
      // Non-critical — the picker still works fine without the recommended row.
      console.error('Failed to load recommended scenarios:', recommendationsResult.reason)
    }
  }

  const handleSelectScenario = useCallback((s: Scenario) => {
    setSelectedScenario(s)
    setReadingTime(PREP_SECONDS)
    setExamSeconds(0)
    setConvHistory([])
    setHistory([])
    setSessionId(null)
    setFeedback(null)
    setPronunciationResult(null)
    setComparisonResult(null)
    setTypedResponse('')
    // isEnding/isScoring only ever get set true by the previous session's End
    // Session flow and are never cleared there, since that session unmounts
    // into the results phase before scoring finishes. Without resetting them
    // here, a second session picked via "Try Again" would render with the
    // orb permanently stuck in its disabled "Ending/Scoring" state.
    setIsEnding(false)
    setIsScoring(false)
    setConversationError(null)
    setPhase('briefing')
  }, [])

  const handleSessionEnd = useCallback((chatHistory: ChatMessage[], resultFeedback: any) => {
    setHistory(chatHistory)
    setFeedback(resultFeedback)
    setComparisonResult(null)
    setPhase('result')
    if (resultFeedback) {
      trackEvent('score_viewed', {
        module: 'speaking',
        scenario_id: selectedScenario?.id,
        overall_band: resultFeedback.overall_band,
        plan: resultFeedback.plan,
        is_premium_trial: resultFeedback.is_premium_trial,
      })
    }
  }, [selectedScenario])

  const handleRetryWeakest = useCallback(() => {
    if (selectedScenario) handleSelectScenario(selectedScenario)
  }, [selectedScenario, handleSelectScenario])

  const handleTryAgain = useCallback(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(SPEAKING_SESSION_KEY)
    }
    setSelectedScenario(null)
    setHistory([])
    setFeedback(null)
    setConvHistory([])
    setSessionId(null)
    setExamSeconds(0)
    setReadingTime(PREP_SECONDS)
    setPronunciationResult(null)
    setComparisonResult(null)
    setTypedResponse('')
    setPhase('select')
  }, [])

  const handleResumeSession = useCallback(() => {
    if (!pendingResume) return
    const { scenario, parsed } = pendingResume
    setSelectedScenario(scenario)
    setPhase(parsed.phase)
    setReadingTime(typeof parsed.readingTime === 'number' ? parsed.readingTime : PREP_SECONDS)
    setExamSeconds(typeof parsed.examSeconds === 'number' ? parsed.examSeconds : 0)
    setConvHistory(Array.isArray(parsed.convHistory) ? parsed.convHistory : [])
    setHistory(Array.isArray(parsed.history) ? parsed.history : [])
    setSessionId(typeof parsed.sessionId === 'number' ? parsed.sessionId : null)
    setFeedback(parsed.feedback ?? null)
    setComparisonResult(null)
    setPendingResume(null)
  }, [pendingResume])

  const handleDiscardResume = useCallback(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(SPEAKING_SESSION_KEY)
    }
    setPendingResume(null)
  }, [])

  if (status === 'loading' || isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="h-9 w-64 rounded-lg bg-gray-200 animate-pulse" />
          <div className="h-5 w-80 rounded-lg bg-gray-100 animate-pulse mt-2" />
          <div className="grid md:grid-cols-2 gap-6 mt-8">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 flex flex-col gap-4">
                <div className="h-6 w-24 rounded-full bg-gray-100 animate-pulse" />
                <div className="h-6 w-3/4 rounded-lg bg-gray-200 animate-pulse" />
                <div className="space-y-2">
                  <div className="h-4 w-full rounded bg-gray-100 animate-pulse" />
                  <div className="h-4 w-5/6 rounded bg-gray-100 animate-pulse" />
                  <div className="h-4 w-2/3 rounded bg-gray-100 animate-pulse" />
                </div>
                <div className="h-11 w-full rounded-xl bg-gray-100 animate-pulse mt-auto" />
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (phase === 'select') {
    return (
      <SelectPhase
        scenarios={scenarios}
        pendingResume={pendingResume}
        recommendedScenarios={recommendedScenarios}
        filterSpecialty={filterSpecialty}
        filterDifficulty={filterDifficulty}
        filterStatus={filterStatus}
        searchQuery={searchQuery}
        completedScenarioIds={completedScenarioIds}
        onSelectScenario={handleSelectScenario}
        onResumeSession={handleResumeSession}
        onDiscardResume={handleDiscardResume}
        onSearchQueryChange={setSearchQuery}
        onFilterDifficultyChange={setFilterDifficulty}
        onFilterStatusChange={setFilterStatus}
        onFilterSpecialtyChange={setFilterSpecialty}
      />
    )
  }

  return (
    <SpeakingSession
      phase={phase}
      selectedScenario={selectedScenario}
      userId={authSession?.user?.id}
      router={router}
      readingTime={readingTime}
      examSeconds={examSeconds}
      setExamSeconds={setExamSeconds}
      convHistory={convHistory}
      setConvHistory={setConvHistory}
      history={history}
      sessionId={sessionId}
      setSessionId={setSessionId}
      feedback={feedback}
      onSessionEnd={handleSessionEnd}
      typedResponse={typedResponse}
      setTypedResponse={setTypedResponse}
      autoListen={autoListen}
      setAutoListen={setAutoListen}
      captionsOn={captionsOn}
      setCaptionsOn={setCaptionsOn}
      isEnding={isEnding}
      setIsEnding={setIsEnding}
      isScoring={isScoring}
      setIsScoring={setIsScoring}
      conversationError={conversationError}
      setConversationError={setConversationError}
      pastSubmissions={pastSubmissions}
      setPastSubmissions={setPastSubmissions}
      comparisonResult={comparisonResult}
      setComparisonResult={setComparisonResult}
      comparisonError={comparisonError}
      setComparisonError={setComparisonError}
      isComparing={isComparing}
      setIsComparing={setIsComparing}
      pronunciationResult={pronunciationResult}
      setPronunciationResult={setPronunciationResult}
      isAssessingPronunciation={isAssessingPronunciation}
      setIsAssessingPronunciation={setIsAssessingPronunciation}
      pronunciationError={pronunciationError}
      setPronunciationError={setPronunciationError}
      onTryAgain={handleTryAgain}
      onRetryWeakest={handleRetryWeakest}
      setPhase={setPhase}
    />
  )
}
