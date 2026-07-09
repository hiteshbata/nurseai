'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { CheckCircle2, Mic, Trophy, Target, ArrowLeft, Search, X, Captions, Star, PartyPopper } from 'lucide-react'
import VoiceOrb from '@/components/VoiceOrb'
import PlanUsageBanner from '@/components/PlanUsageBanner'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { trackEvent } from '@/lib/analytics'
import { useMicrophone } from '@/app/hooks/useMicrophone'
import { useSpeakingSession } from '@/app/hooks/useSpeakingSession'
import { useRealtimeSpeakingSession } from '@/app/hooks/useRealtimeSpeakingSession'

// Toggle to switch the whole speaking flow onto the realtime voice pipeline
// (backend: /speaking/realtime/stream, provider selected server-side via
// VOICE_PROVIDER=openai|gemini) instead of the Deepgram STT + TTS
// round-trip. Both hooks return the same shape so this is the only line
// that needs to change to test/roll out the new pipeline. If the realtime
// provider itself goes down mid-rollout, the component automatically
// drops back to the legacy pipeline per-session (see useLegacyFallback
// below) without needing this flag touched.
const USE_REALTIME_API = false

interface Scenario {
  id: number
  title: string
  setting: string
  difficulty: string
  nurse_card: any
  specialty?: string
  patient_gender?: string
  voice_config?: {
    voice_name?: string
    speaking_rate?: number
    pitch?: number
    language_code?: string
  }
}

interface ChatMessage {
  role: 'nurse' | 'patient'
  content: string
}

interface Submission {
  id: number
  scenario_id: number
  module: string
  score: number
  created_at: string
}

interface RecommendedScenario {
  scenario_id: number
  title: string
  setting: string
  difficulty: string
  reason: string
}

const sanitizeText = (text: string): string => {
  if (!text) return ''
  return text
    .replace(/<[^>]*>/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
}

type Phase = 'select' | 'briefing' | 'conversation' | 'result'

const SPEAKING_SESSION_KEY = 'speakoet-speaking-session-v1'
const AUTO_LISTEN_KEY = 'speakoet-auto-listen'
const CAPTIONS_KEY = 'speakoet-captions'
const PREP_SECONDS = 180
// Records the whole session (separate from live STT streaming) for the
// post-session /speaking/pronunciation call.
const SESSION_RECORDING_MIME_CANDIDATES = ['audio/webm', 'audio/ogg', 'audio/mp4']

const STAGES_NAV = [
  { key: 'select', label: 'Select' },
  { key: 'briefing', label: 'Read Brief' },
  { key: 'conversation', label: 'Practice' },
  { key: 'result', label: 'Results' },
]

const clinicalLabels: Record<string, string> = {
  empathy: 'Empathy',
  patient_perspective: "Patient's Perspective",
  providing_structure: 'Providing Structure',
  information_gathering: 'Information Gathering',
  information_giving: 'Information Giving',
}

const linguisticLabels: Record<string, string> = {
  intelligibility: 'Intelligibility',
  fluency: 'Fluency',
  appropriateness_of_language: 'Appropriateness of Language',
  grammar: 'Grammar & Expression',
}

const basicLabels: Record<string, string> = {
  clinical_communication: 'Clinical Communication',
  linguistic_delivery: 'Linguistic Delivery',
  relationship_building: 'Relationship Building',
}

const LOCKED_CRITERIA_PREVIEW = ['Empathy', 'Information Gathering', 'Fluency', 'Grammar & Expression']

function scoreColor(score: number) {
  if (score >= 4) return 'text-emerald-600'
  if (score >= 3) return 'text-amber-500'
  return 'text-red-500'
}

function normalizeDifficulty(difficulty: string): 'beginner' | 'intermediate' | 'advanced' {
  if (difficulty === 'easy' || difficulty === 'beginner') return 'beginner'
  if (difficulty === 'hard' || difficulty === 'advanced') return 'advanced'
  return 'intermediate'
}

function scoreToGrade(score: number): string {
  if (score >= 4.5) return 'A'
  if (score >= 4.0) return 'B'
  if (score >= 3.5) return 'C+'
  if (score >= 3.0) return 'C'
  if (score >= 2.0) return 'D'
  return 'E'
}

export default function SpeakingPage() {
  const { status } = useSupabaseSession()
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
  const [isDark, setIsDark] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [isCardZoomed, setIsCardZoomed] = useState(false)
  const [isMobileCardOpen, setIsMobileCardOpen] = useState(false)
  const [pronunciationResult, setPronunciationResult] = useState<any>(null)
  const [isAssessingPronunciation, setIsAssessingPronunciation] = useState(false)
  const [pronunciationError, setPronunciationError] = useState(false)
  const [hasRestoredSession, setHasRestoredSession] = useState(false)
  const [scoringElapsed, setScoringElapsed] = useState(0)
  const [pendingResume, setPendingResume] = useState<{ scenario: Scenario; parsed: any } | null>(null)
  // Defaults on (matches the auto-restart behavior this replaces); persisted
  // across sessions since it's a standing preference, not per-scenario state.
  const [autoListen, setAutoListen] = useState(true)
  // Defaults on -- captions are an accessibility aid, not an opt-in extra.
  const [captionsOn, setCaptionsOn] = useState(true)

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
    if (phase === 'result' && selectedScenario) {
      fetchSubmissions()
    }
  }, [phase, selectedScenario])

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
      setIsFullscreen(isFs)
      const nav = document.querySelector('nav')
      if (nav) nav.classList.toggle('hidden', isFs)
    }
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])



  const handleHistoryChange = useCallback((h: ChatMessage[]) => {
    setConvHistory(h)
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
    try {
      const res = await api.get('/submissions', { params: { module: 'speaking' } })
      const ids: number[] = (res.data || []).map((sub: Submission) => sub.scenario_id)
      setCompletedScenarioIds(new Set(ids))
    } catch (e) {
      console.error('Failed to load completed scenarios:', e)
    }
    try {
      const res = await api.get('/speaking/scenarios/recommendations', { params: { limit: 3 } })
      setRecommendedScenarios(res.data || [])
    } catch (e) {
      // Non-critical — the picker still works fine without the recommended row.
      console.error('Failed to load recommended scenarios:', e)
    }
  }

  const handleSelectScenario = (s: Scenario) => {
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
  }

  const handleStartConversation = async () => {
    setExamSeconds(0)
    const micResult = await sessionMic.start()
    if (micResult.ok) {
      setConversationError(null)
    } else if (micResult.reason === 'unsupported') {
      setConversationError('Audio recording is not supported in this browser. Use typed practice below or switch browsers.')
    } else {
      setConversationError('Microphone is unavailable. You can continue with typed practice or allow microphone access.')
    }
    setPhase('conversation')
    trackEvent('speaking_session_started', {
      scenario_id: selectedScenario?.id,
      scenario_title: selectedScenario?.title,
      difficulty: selectedScenario?.difficulty,
    })
  }

  const handleSessionEnd = (chatHistory: ChatMessage[], resultFeedback: any) => {
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
  }

  const handleRetryWeakest = () => {
    if (selectedScenario) handleSelectScenario(selectedScenario)
  }

  const handleTryAgain = () => {
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
  }

  const handleResumeSession = () => {
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
  }

  const handleDiscardResume = () => {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(SPEAKING_SESSION_KEY)
    }
    setPendingResume(null)
  }

  const canCompare = pastSubmissions.length > 1

  const fetchSubmissions = async () => {
    if (!selectedScenario) return
    try {
      const res = await api.get('/submissions', {
        params: { module: 'speaking', scenario_id: selectedScenario.id }
      })
      setPastSubmissions(res.data || [])
    } catch (e) {
      console.error('Failed to fetch submissions:', e)
    }
  }

  const [isEnding, setIsEnding] = useState(false)
  const [isScoring, setIsScoring] = useState(false)
  const [conversationError, setConversationError] = useState<string | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Session-long recording (separate from live STT streaming below) --
  // used only for the /speaking/pronunciation call after scoring.
  const sessionMic = useMicrophone({
    mimeTypeCandidates: SESSION_RECORDING_MIME_CANDIDATES,
    timesliceMs: 1000,
  })

  // Set once the backend reports the realtime voice provider itself is
  // down (VOICE_PROVIDER connect failure or an unrecoverable mid-session
  // provider error) -- see onProviderUnavailable below. Once true, the rest
  // of this component permanently uses the legacy Deepgram/Gemini/TTS
  // pipeline for the remainder of this practice session; convHistory and
  // sessionId are already shared state, so the handoff is seamless.
  const [useLegacyFallback, setUseLegacyFallback] = useState(false)

  // Both hooks are always called (rules-of-hooks requires a stable call
  // order) -- USE_REALTIME_API/useLegacyFallback just pick which one's
  // result the rest of the component uses. Neither does anything until its
  // own startListening is invoked, so the unused one is inert.
  const legacySession = useSpeakingSession({
    scenario: selectedScenario,
    convHistory,
    setConvHistory,
    sessionId,
    setSessionId,
    isEnding,
    autoListen,
  })
  const realtimeSession = useRealtimeSpeakingSession({
    scenario: selectedScenario,
    convHistory,
    setConvHistory,
    sessionId,
    setSessionId,
    isEnding,
    onProviderUnavailable: () => {
      setUseLegacyFallback(true)
      setConversationError('Live voice mode is temporarily unavailable — switched to standard voice mode.')
    },
  })
  const useRealtime = USE_REALTIME_API && !useLegacyFallback
  const session = useRealtime ? realtimeSession : legacySession

  // The instant the fallback flips on, pick up listening again on the
  // legacy pipeline automatically -- realtimeSession.onProviderUnavailable
  // already tore its own mic/socket down, so nothing is capturing audio
  // until this fires.
  useEffect(() => {
    if (useLegacyFallback && phase === 'conversation' && !isEnding) {
      legacySession.startListening()
    }
    // legacySession.startListening specifically, not the whole object --
    // see the identical pattern/reasoning on handleTypedSubmit below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [useLegacyFallback])

  // isProcessing is shared across the live conversation turn (owned by the
  // session hook) and the post-session scoring call (owned here) so both
  // still gate the same UI affordances they did before this was split out.
  const isProcessing = session.isProcessing || isScoring

  useEffect(() => {
    if (!isEnding) {
      setScoringElapsed(0)
      return
    }
    const interval = setInterval(() => setScoringElapsed((s) => s + 1), 1000)
    return () => clearInterval(interval)
  }, [isEnding])

  useEffect(() => {
    if (conversationError) {
      const timer = setTimeout(() => setConversationError(null), 8000)
      return () => clearTimeout(timer)
    }
  }, [conversationError])

  const handleTypedSubmit = useCallback(async () => {
    const text = typedResponse.trim()
    if (!text || isProcessing || isEnding) return
    setTypedResponse('')
    await session.sendTypedMessage(text)
    // session.sendTypedMessage specifically, not the whole session object --
    // useSpeakingSession returns a fresh object every render (isListening/
    // interimText/etc. are state), which would otherwise recreate this on
    // every render instead of only when the message-sending logic changes.
  }, [typedResponse, isProcessing, isEnding, session.sendTypedMessage])

  const handleEndConversation = useCallback(async () => {
    if (!selectedScenario) return
    const nurseTurns = convHistory.filter(m => m.role === 'nurse')
    if (nurseTurns.length === 0) {
      setConversationError('Speak or type at least one response before ending the session.')
      return
    }
    setIsEnding(true)
    session.stopListening()
    session.stopSpeaking()
    setIsScoring(true)
    try {
      const res = await api.post('/speaking/score', {
        scenario_id: selectedScenario.id,
        history: convHistory.map(m => ({ role: m.role, content: m.content })),
        duration_seconds: examSeconds,
        session_id: sessionId,
      })
      handleSessionEnd(convHistory, {
        ...res.data.feedback,
        is_premium_trial: res.data.is_premium_trial,
        plan: res.data.plan,
        criteria_count: res.data.criteria_count,
      })

      // Get pronunciation assessment
      try {
        setIsAssessingPronunciation(true)
        setPronunciationError(false)

        // Stop recording and get audio blob
        const audioBlob = await sessionMic.stop()

        if (audioBlob && audioBlob.size > 0) {
          // Get nurse-only transcript
          const nurseTranscript = convHistory
            .filter(m => m.role === 'nurse')
            .map(m => m.content)
            .join(' ')

          // Send to pronunciation endpoint
          const formData = new FormData()
          formData.append('audio', audioBlob, 'session.webm')
          formData.append('nurse_transcript', nurseTranscript)

          const pronRes = await api.post(
            '/speaking/pronunciation',
            formData,
            { headers: { 'Content-Type': 'multipart/form-data' } }
          )

          if (pronRes.data.success) {
            setPronunciationResult({
              ...pronRes.data.pronunciation,
              plan_limited: pronRes.data.plan_limited,
              upgrade_required: pronRes.data.upgrade_required,
            })
          }
        }
      } catch (pronError) {
        console.error('Pronunciation assessment failed:', pronError)
        // Non-critical — don't block results display
        setPronunciationError(true)
      } finally {
        setIsAssessingPronunciation(false)
      }
    } catch (e: any) {
      console.error('Score error:', e)
      handleSessionEnd(convHistory, null)
    } finally {
      setIsScoring(false)
    }
    // session.stopListening/stopSpeaking and sessionMic.stop specifically,
    // not the whole session/sessionMic objects -- both hooks return a fresh
    // object every render (their internal state changes), which would
    // otherwise recreate this on every render instead of only when
    // selectedScenario/convHistory/sessionId/examSeconds actually change.
  }, [selectedScenario, convHistory, sessionId, examSeconds, session.stopListening, session.stopSpeaking, sessionMic.stop])

  useEffect(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.getVoices()
    }
  }, [])

  useEffect(() => {
    const el = chatEndRef.current?.parentElement
    if (!el) return
    const threshold = 60
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
    if (isNearBottom) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [convHistory, session.interimText])

  const handleCompare = async () => {
    if (!selectedScenario || pastSubmissions.length < 2) return
    setIsComparing(true)
    setComparisonError(null)
    try {
      const sorted = [...pastSubmissions].sort(
        (a: Submission, b: Submission) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
      const res = await api.post('/compare/attempts', {
        scenario_id: selectedScenario.id,
        attempt1_id: sorted[1].id,
        attempt2_id: sorted[0].id,
      })
      setComparisonResult(res.data)
    } catch (e: any) {
      console.error('Comparison failed:', e)
      if (e?.response?.status === 403) {
        setComparisonError('That attempt is outside your plan’s comparison window — upgrade to Pro for unlimited attempt comparison.')
      } else {
        setComparisonError('Comparison failed. Please try again.')
      }
    } finally {
      setIsComparing(false)
    }
  }

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

  /* ── SCENARIO SELECTION ── */
  if (phase === 'select') {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-3xl font-bold text-[#0F2356]">Speaking Practice</h1>
          <p className="text-gray-500 mt-1">Choose a scenario to begin your OET roleplay</p>

          {pendingResume && (
            <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
              <div>
                <p className="text-sm font-semibold text-[#0F2356]">
                  You have an unfinished session: {pendingResume.scenario.title}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">Pick up where you left off, or discard it and start fresh.</p>
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={handleDiscardResume}
                  className="rounded-lg px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-100 transition"
                >
                  Discard
                </button>
                <button
                  onClick={handleResumeSession}
                  className="rounded-lg bg-emerald-500 text-white px-4 py-2 text-sm font-semibold hover:bg-emerald-600 transition"
                >
                  Resume
                </button>
              </div>
            </div>
          )}

          {scenarios.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-xl shadow">
              <p className="text-xl text-gray-500 mb-2">No scenarios available</p>
              <p className="text-gray-400">Ask an admin to create speaking scenarios</p>
            </div>
          ) : (
            <>
              {/* Recommended row — leads with 3 personalized picks (new scenarios
                  first, then weakest-scored) above the full browsable grid, so
                  users aren't left to scan 100+ cards to find where to start. */}
              {recommendedScenarios.length > 0 && (
                <div className="mb-6">
                  <p className="text-xs font-semibold uppercase tracking-wide text-emerald-600 mb-3 flex items-center gap-1.5">
                    <Star className="w-3.5 h-3.5" aria-hidden="true" /> Recommended for you
                  </p>
                  <div className="grid gap-3 sm:grid-cols-3">
                    {recommendedScenarios.map((r) => {
                      const full = scenarios.find((s) => s.id === r.scenario_id)
                      const diffLabel =
                        r.difficulty === 'beginner' || r.difficulty === 'easy'
                          ? 'Beginner'
                          : r.difficulty === 'advanced' || r.difficulty === 'hard'
                          ? 'Advanced'
                          : 'Intermediate'
                      return (
                        <button
                          key={r.scenario_id}
                          onClick={() => full && handleSelectScenario(full)}
                          disabled={!full}
                          className="text-left rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-teal-50 p-4 transition-all hover:shadow-md hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
                        >
                          <span className="inline-block rounded-full bg-white/70 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                            {diffLabel}
                          </span>
                          <h4 className="mt-2 font-bold text-[#0F2356] line-clamp-1">{r.title}</h4>
                          <p className="mt-1 text-xs text-gray-500 line-clamp-2">{r.reason}</p>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Search + difficulty/status filters */}
              <div className="flex flex-col sm:flex-row gap-3 mb-4">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search scenarios by title or setting..."
                    aria-label="Search scenarios"
                    className="pl-10 pr-9"
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery('')}
                      aria-label="Clear search"
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
                <Select
                  value={filterDifficulty}
                  onChange={(e) => setFilterDifficulty(e.target.value)}
                  aria-label="Filter by difficulty"
                  className="sm:w-48"
                >
                  <option value="all">All difficulties</option>
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                </Select>
                <Select
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value as typeof filterStatus)}
                  aria-label="Filter by completion status"
                  className="sm:w-48"
                >
                  <option value="all">All scenarios</option>
                  <option value="completed">Completed</option>
                  <option value="not_tried">Not yet tried</option>
                </Select>
              </div>

              {/* Specialty filter pills */}
              {(() => {
                const specialtyCounts: Record<string, number> = {}
                for (const s of scenarios) {
                  const sp = s.specialty || 'Uncategorized'
                  specialtyCounts[sp] = (specialtyCounts[sp] || 0) + 1
                }
                const specialties = Object.keys(specialtyCounts).sort()
                return (
                  <div className="flex flex-wrap gap-2 mb-6">
                    <button
                      onClick={() => setFilterSpecialty('all')}
                      className={`min-h-11 px-3.5 rounded-full text-xs font-semibold transition ${
                        filterSpecialty === 'all'
                          ? 'bg-[#0F2356] text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                    >
                      All ({scenarios.length})
                    </button>
                    {specialties.map((sp) => (
                      <button
                        key={sp}
                        onClick={() => setFilterSpecialty(sp)}
                        className={`min-h-11 px-3.5 rounded-full text-xs font-semibold transition ${
                          filterSpecialty === sp
                            ? 'bg-[#0F2356] text-white'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                      >
                        {sp} ({specialtyCounts[sp]})
                      </button>
                    ))}
                  </div>
                )
              })()}

              {(() => {
                const query = searchQuery.trim().toLowerCase()
                const filteredScenarios = scenarios.filter((s) => {
                  if (filterSpecialty !== 'all' && (s.specialty || 'Uncategorized') !== filterSpecialty) return false
                  if (filterDifficulty !== 'all' && normalizeDifficulty(s.difficulty) !== filterDifficulty) return false
                  const isCompleted = completedScenarioIds.has(s.id)
                  if (filterStatus === 'completed' && !isCompleted) return false
                  if (filterStatus === 'not_tried' && isCompleted) return false
                  if (query && !s.title.toLowerCase().includes(query) && !s.setting.toLowerCase().includes(query)) return false
                  return true
                })

                if (filteredScenarios.length === 0) {
                  return (
                    <div className="text-center py-16 bg-white rounded-xl shadow">
                      <p className="text-lg font-semibold text-gray-500 mb-1">No scenarios match your filters</p>
                      <p className="text-gray-400 text-sm">Try a different search term or clear a filter</p>
                    </div>
                  )
                }

                return (
                  <div className="grid md:grid-cols-2 gap-6">
                    {filteredScenarios.map((s) => {
                      const card = s.nurse_card || {}
                      const tasks = card.tasks || []
                      const isCompleted = completedScenarioIds.has(s.id)
                      const difficultyBadge =
                        s.difficulty === 'easy' || s.difficulty === 'beginner'
                          ? 'bg-emerald-100 text-emerald-700'
                          : s.difficulty === 'hard' || s.difficulty === 'advanced'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-amber-100 text-amber-700'
                      const difficultyLabel =
                        s.difficulty === 'beginner' || s.difficulty === 'easy' ? 'Beginner'
                          : s.difficulty === 'advanced' || s.difficulty === 'hard' ? 'Advanced'
                          : 'Intermediate'
                      return (
                  <div
                    key={s.id}
                    onClick={() => handleSelectScenario(s)}
                    className="relative bg-white rounded-2xl shadow-sm border border-gray-100 p-6 flex flex-col gap-4 hover:shadow-md hover:scale-[1.01] active:scale-[0.99] active:shadow-sm transition-all duration-200 cursor-pointer"
                  >
                    {isCompleted && (
                      <span className="absolute top-4 right-4 flex items-center gap-1 rounded-full bg-emerald-500 text-white text-[10px] font-semibold px-2.5 py-1">
                        <CheckCircle2 className="size-3" />
                        Completed
                      </span>
                    )}
                    <div className="flex items-center gap-2 flex-wrap pr-24">
                      <span className={`px-3 py-1 rounded-full text-xs font-semibold w-fit ${difficultyBadge}`}>
                        {difficultyLabel}
                      </span>
                      {s.specialty && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-blue-50 text-blue-600">
                          {s.specialty}
                        </span>
                      )}
                    </div>
                    <h3 className="text-xl font-bold text-[#0F2356]">{s.title}</h3>
                    <p className="text-gray-600 text-sm line-clamp-3 leading-relaxed">
                      {sanitizeText(s.setting)}
                    </p>
                    <hr className="border-gray-100" />
                    <p className="text-xs font-semibold text-[#0F2356] uppercase tracking-wide">
                      YOUR TASKS
                    </p>
                    <ul className="space-y-1">
                      {tasks.slice(0, 3).map((task: string, i: number) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                          <span className="w-1.5 h-1.5 rounded-full bg-gray-400 mt-2 flex-shrink-0" />
                          <span>{sanitizeText(task)}</span>
                        </li>
                      ))}
                    </ul>
                    {tasks.length > 3 && (
                      <p className="text-sm text-[#10B981] font-medium">
                        +{tasks.length - 3} more tasks
                      </p>
                    )}
                    <div className="flex-1" />
                    <button
                      onClick={() => handleSelectScenario(s)}
                      className="w-full bg-[#0F2356] text-white rounded-xl py-3 font-semibold text-sm hover:bg-opacity-90 transition-colors flex items-center justify-center gap-2"
                    >
                      Start Scenario →
                    </button>
                  </div>
                      )
                    })}
                  </div>
                )
              })()}
            </>
          )}
        </div>
      </div>
    )
  }

  /* ── BRIEFING (v0 redesign) ── */
  if (phase === 'briefing' && selectedScenario) {
    const formatTime = (s: number) => {
      const m = Math.floor(s / 60)
      const sec = s % 60
      return m > 0 ? `${m}m ${sec}s` : `${sec}s`
    }

    return (
      <div className="min-h-screen bg-[#F8FAFC] px-4 py-10">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-center justify-center gap-2 mb-8 flex-wrap">
            {STAGES_NAV.map((stage, i) => (
              <div key={stage.key} className="flex items-center gap-2">
                <div
                  className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-all ${
                    stage.key === 'briefing'
                      ? 'bg-emerald-500 text-white'
                      : stage.key === 'select'
                      ? 'bg-[#0F2356]/10 text-[#0F2356]'
                      : 'bg-gray-100 text-gray-400'
                  }`}
                >
                  {stage.key === 'select' && <CheckCircle2 className="size-3" />}
                  {stage.label}
                </div>
                {i < STAGES_NAV.length - 1 && (
                  <span className="text-gray-300 text-xs">›</span>
                )}
              </div>
            ))}
          </div>

          <div className="rounded-2xl bg-white shadow-sm p-8">
            <div className="mb-6">
              <p className="text-emerald-600 text-xs font-semibold uppercase tracking-widest mb-2">Setting</p>
              <p className="text-gray-700 leading-relaxed mt-1">{sanitizeText(selectedScenario.setting)}</p>
            </div>

            <div className="mb-6">
              <p className="text-emerald-600 text-xs font-semibold uppercase tracking-widest mb-2">Nurse Role</p>
              <p className="text-gray-700 leading-relaxed mt-1">{sanitizeText(selectedScenario.nurse_card?.role || '')}</p>
            </div>

            <div className="mb-8">
              <p className="text-emerald-600 text-xs font-semibold uppercase tracking-widest mb-2">Your Tasks</p>
              <ol className="flex flex-col gap-2">
                {(selectedScenario.nurse_card?.tasks || []).map((task: string, i: number) => (
                  <li key={i} className="flex gap-3 text-gray-700">
                    <span className="shrink-0 size-5 rounded-full bg-[#0F2356]/10 text-[#0F2356] text-xs font-bold flex items-center justify-center mt-0.5">
                      {i + 1}
                    </span>
                    <span>{sanitizeText(task)}</span>
                  </li>
                ))}
              </ol>
            </div>

            <div className="mb-6">
              <p className="text-center text-sm text-gray-500 mb-2">
                Reading time remaining:{' '}
                <span className="font-semibold text-gray-700">{formatTime(readingTime)}</span>
              </p>
              <Progress
                value={(readingTime / PREP_SECONDS) * 100}
                className="h-2 bg-gray-100 [&>div]:bg-emerald-500"
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={handleStartConversation}
                className="flex-1 rounded-xl bg-emerald-500 text-white py-2.5 text-sm font-semibold hover:bg-emerald-600 transition"
              >
                {readingTime > 0 ? 'Start Early' : 'Begin Speaking'}
              </button>
              <button
                onClick={handleTryAgain}
                className="flex-1 rounded-xl py-2.5 text-sm font-semibold text-gray-600 hover:bg-gray-100 transition"
              >
                Back to Scenarios
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  /* ── VOICE CONVERSATION (v0 right panel redesign) ── */
  if (phase === 'conversation' && selectedScenario) {
    // Live caption line: nurse's in-progress speech while listening, else the
    // patient's reply text for as long as its audio is playing.
    const lastPatientMessage = [...convHistory].reverse().find((m) => m.role === 'patient')?.content
    const liveCaption = session.interimText || (session.isSpeaking ? lastPatientMessage : '') || ''
    const liveCaptionSpeaker = session.interimText ? 'You' : 'Patient'

    return (
      <div className="fixed inset-0 top-[64px] bg-[#F8FAFC] z-40 flex flex-col lg:flex-row">
        {/* LEFT PANEL */}
        <div className="w-full lg:w-[35%] h-[42%] lg:h-full overflow-y-auto bg-[#F8FAFC] border-b lg:border-b-0 lg:border-r border-gray-200 p-4 lg:p-6">
          <div className="flex flex-col gap-5">
              <div>
                <p className="text-emerald-600 text-xs font-semibold uppercase tracking-widest mb-1.5">Setting</p>
                <p className="text-xs text-gray-600 leading-relaxed line-clamp-4">{sanitizeText(selectedScenario.setting)}</p>
              </div>
              <Separator />
              <div>
                <p className="text-emerald-600 text-xs font-semibold uppercase tracking-widest mb-1.5">Your Role</p>
                <p className="text-xs text-gray-600 leading-relaxed line-clamp-3">{sanitizeText(selectedScenario.nurse_card?.role || '')}</p>
              </div>
              <Separator />
              <div>
                <p className="text-emerald-600 text-xs font-semibold uppercase tracking-widest mb-2">Tasks</p>
                <ol className="flex flex-col gap-1.5">
                  {(selectedScenario.nurse_card?.tasks || []).map((task: string, i: number) => (
                    <li key={i} className="flex gap-2 text-xs text-gray-600">
                      <span className="shrink-0 font-semibold text-[#0F2356]">{i + 1}.</span>
                      <span>{sanitizeText(task)}</span>
                    </li>
                  ))}
                </ol>
              </div>

          </div>
        </div>

        {/* RIGHT PANEL */}
        <div className="w-full lg:w-[65%] h-[58%] lg:h-full flex flex-col bg-white">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <div className="flex items-center gap-2" role="status" aria-live="polite">
              <p className="text-sm font-semibold text-[#0F2356]">Conversation</p>
              {sessionMic.isRecording && (
                session.isListening ? (
                  <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-500" title="Your microphone is capturing your voice right now">
                    <span className="size-2 rounded-full bg-red-500 animate-pulse" />
                    Recording
                  </span>
                ) : (
                  <span
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-400"
                    title={
                      convHistory.some((m) => m.role === 'nurse')
                        ? autoListen && session.isSpeaking
                          ? 'Mic reopens once the patient finishes speaking'
                          : 'Tap the orb to speak again'
                        : 'Tap the orb below to start speaking'
                    }
                  >
                    <span className="size-2 rounded-full bg-gray-300" />
                    {convHistory.some((m) => m.role === 'nurse') ? 'Mic paused' : 'Not recording yet'}
                  </span>
                )
              )}
              {session.isSpeaking && (
                <span className="text-xs text-blue-500 animate-pulse">Patient speaking…</span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setAutoListen((v) => !v)}
                role="switch"
                aria-checked={autoListen}
                title="When on, the mic reopens automatically once the patient finishes speaking"
                className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition ${
                  autoListen ? 'bg-emerald-50 text-emerald-600' : 'bg-gray-100 text-gray-500'
                }`}
              >
                <span
                  className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors ${
                    autoListen ? 'bg-emerald-500' : 'bg-gray-300'
                  }`}
                >
                  <span
                    className={`inline-block size-3 transform rounded-full bg-white transition-transform ${
                      autoListen ? 'translate-x-3.5' : 'translate-x-0.5'
                    }`}
                  />
                </span>
                Auto-listen
              </button>
              <button
                onClick={() => setCaptionsOn((v) => !v)}
                role="switch"
                aria-checked={captionsOn}
                title="Show a large live caption of what's being said"
                className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition ${
                  captionsOn ? 'bg-emerald-50 text-emerald-600' : 'bg-gray-100 text-gray-500'
                }`}
              >
                <Captions className="size-3.5" />
                Captions
              </button>
              <p className="font-mono text-base font-bold text-[#0F2356]">
              {String(Math.floor(examSeconds / 60)).padStart(2, '0')}:{String(examSeconds % 60).padStart(2, '0')}
              </p>
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto p-6" role="log" aria-live="polite">
            {convHistory.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center gap-3 text-center">
                <div className="size-14 rounded-full bg-[#0F2356]/10 flex items-center justify-center">
                  <Mic className="size-7 text-[#0F2356]/60" />
                </div>
                <p className="font-semibold text-gray-700">Ready to begin</p>
                <p className="text-sm text-gray-400 max-w-xs">
                  Tap the orb below to speak to your patient
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                {convHistory.map((msg, i) => (
                  <div key={i} className={`flex gap-3 ${msg.role === 'nurse' ? 'flex-row-reverse' : 'flex-row'}`}>
                    <Avatar className="size-8 shrink-0">
                      <AvatarFallback className={`text-xs font-bold text-white ${msg.role === 'nurse' ? 'bg-[#0F2356]' : 'bg-gray-400'}`}>
                        {msg.role === 'nurse' ? 'N' : 'P'}
                      </AvatarFallback>
                    </Avatar>
                    <div className={`flex flex-col gap-1 max-w-[70%] ${msg.role === 'nurse' ? 'items-end' : 'items-start'}`}>
                      <span className="text-xs text-gray-400">
                        {msg.role === 'nurse' ? 'You (Nurse)' : 'Patient'}
                      </span>
                      <div className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                        msg.role === 'nurse' ? 'bg-[#0F2356] text-white' : 'bg-gray-100 text-gray-800'
                      }`}>
                        {msg.content}
                      </div>
                    </div>
                  </div>
                ))}
                {session.interimText && (
                  <div className="flex gap-3 flex-row-reverse" aria-hidden="true">
                    <Avatar className="size-8 shrink-0">
                      <AvatarFallback className="text-xs font-bold text-white bg-[#0F2356]">N</AvatarFallback>
                    </Avatar>
                    <div className="flex flex-col gap-1 items-end max-w-[70%]">
                      <span className="text-xs text-gray-400">You (Nurse)</span>
                      <div className="rounded-2xl px-4 py-2.5 text-sm leading-relaxed bg-[#0F2356]/80 text-white/80">
                        {session.interimText}...
                      </div>
                    </div>
                  </div>
                )}
                {isProcessing && (
                  <div className="flex gap-3 flex-row" aria-hidden="true">
                    <Avatar className="size-8 shrink-0">
                      <AvatarFallback className="text-xs font-bold text-white bg-gray-400">P</AvatarFallback>
                    </Avatar>
                    <div className="flex flex-col gap-1 items-start max-w-[70%]">
                      <span className="text-xs text-gray-400">Patient</span>
                      <div className="rounded-2xl px-4 py-3 bg-gray-100">
                        <div className="flex gap-1">
                          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )}
          </div>

          <div className="border-t border-gray-100 bg-white px-4 py-3">
            <div className="mx-auto flex max-w-3xl flex-col gap-2 sm:flex-row">
              <input
                value={typedResponse}
                onChange={(e) => setTypedResponse(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleTypedSubmit()
                  }
                }}
                disabled={isProcessing || isEnding}
                placeholder="Mic unavailable? Type your nurse response here..."
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="off"
                spellCheck={false}
                data-lpignore="true"
                data-1p-ignore
                className="min-h-11 flex-1 rounded-xl border border-gray-200 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:bg-gray-50"
              />
              <button
                onClick={handleTypedSubmit}
                disabled={!typedResponse.trim() || isProcessing || isEnding}
                className="min-h-11 rounded-xl bg-[#0F2356] px-4 text-sm font-semibold text-white transition hover:bg-[#0F2356]/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Send
              </button>
            </div>
            {(isProcessing || isEnding) && (
              <p className="mx-auto mt-1.5 max-w-3xl text-xs text-gray-400">
                {isEnding ? 'Ending session…' : "Waiting for the patient's reply…"}
              </p>
            )}
          </div>

          {captionsOn && liveCaption && (
            <div
              role="status"
              aria-live="polite"
              className="mx-4 mb-2 rounded-xl bg-[#0F2356] px-4 py-3 text-center"
            >
              <span className="mr-2 text-xs font-semibold uppercase tracking-wide text-emerald-300">
                {liveCaptionSpeaker}
              </span>
              <span className="text-base font-medium text-white">{liveCaption}</span>
            </div>
          )}

          <VoiceOrb
            isListening={session.isListening}
            isProcessing={isProcessing}
            isSpeaking={session.isSpeaking}
            isEnding={isEnding}
            canEndSession={convHistory.some(m => m.role === 'nurse')}
            statusOverride={
              isEnding
                ? scoringElapsed < 8
                  ? 'Scoring your responses...'
                  : "Still scoring — this can take up to a minute..."
                : undefined
            }
            onToggle={() => session.isListening ? session.stopListening() : session.startListening()}
            onEndSession={handleEndConversation}
          />

          {(session.sttError || conversationError) && (
            <div className="flex items-center justify-center gap-2 py-1" role="alert" aria-live="assertive">
              <p className="text-xs text-red-500 text-center">{session.sttError || conversationError}</p>
              <button
                onClick={() => { session.dismissSttError(); setConversationError(null) }}
                aria-label="Dismiss error"
                className="text-xs text-red-400 hover:text-red-600 font-semibold leading-none"
              >
                ✕
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  /* ── RESULTS (v0 redesign) ── */
  if (phase === 'result') {
    const scores = feedback?.scores || {}
    const clinicalAverage = feedback?.clinical_average ?? 0
    const linguisticAverage = feedback?.linguistic_average ?? 0
    const overallBand = feedback?.overall_band ?? 0
    const oetGrade = scoreToGrade(overallBand)
    // criteria_count comes from the API; fall back to key-shape detection for
    // any session restored from localStorage before this field existed.
    const isNineCriteria = feedback?.criteria_count === 9 || 'empathy' in scores
    const isPremiumTrial = !!feedback?.is_premium_trial

    // Results previously stacked up to three upgrade prompts at once (premium-trial
    // banner, locked-criteria card, Elite pronunciation card). Only one is contextually
    // relevant at a time, so pick a single winner by priority and suppress the rest.
    const activeUpsell: 'pro-retention' | 'pro-unlock' | 'elite-pronunciation' | null = isPremiumTrial
      ? 'pro-retention'
      : !isNineCriteria
      ? 'pro-unlock'
      : pronunciationResult && !isAssessingPronunciation && pronunciationResult.plan_limited
      ? 'elite-pronunciation'
      : null

    // Weakest-scored criterion, used to power the "retry weakest criterion" CTA below.
    const criterionLabels = isNineCriteria ? { ...clinicalLabels, ...linguisticLabels } : basicLabels
    const weakestCriterion = Object.entries(criterionLabels).reduce<{ label: string; score: number } | null>(
      (weakest, [key, label]) => {
        const score = scores[key]?.score
        if (typeof score !== 'number') return weakest
        if (!weakest || score < weakest.score) return { label, score }
        return weakest
      },
      null
    )

    const renderCriterion = (key: string, label: string) => {
      const c = scores[key] || {}
      const score = c.score ?? 0
      const fbText = c.feedback || ''
      return (
        <div key={key} className="rounded-xl bg-white p-4 shadow-sm">
          <div className="flex items-start justify-between gap-2 mb-2">
            <p className="text-sm font-semibold text-[#0F2356] leading-snug">{label}</p>
            <span className={`text-sm font-bold shrink-0 ${scoreColor(score)}`}>
              {score}/6
            </span>
          </div>
          {fbText && <p className="text-xs text-gray-600 leading-relaxed">{fbText}</p>}
        </div>
      )
    }

    return (
      <div className="min-h-screen bg-[#F8FAFC] px-4 py-10">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-center justify-center gap-2 mb-8 flex-wrap">
            {STAGES_NAV.map((stage, i) => (
              <div key={stage.key} className="flex items-center gap-2">
                <div
                  className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-all ${
                    stage.key === 'result'
                      ? 'bg-emerald-500 text-white'
                      : 'bg-gray-100 text-gray-400'
                  }`}
                >
                  {stage.key !== 'select' && stage.key !== 'briefing' && stage.key !== 'conversation' && stage.key === 'result' && <CheckCircle2 className="size-3" />}
                  {stage.label}
                </div>
                {i < STAGES_NAV.length - 1 && (
                  <span className="text-gray-300 text-xs">›</span>
                )}
              </div>
            ))}
          </div>

          {feedback ? (
            <>
              <div className="text-center mb-8">
                <h1 className="text-3xl font-bold text-[#0F2356] text-balance">Session Complete</h1>
                <p className="text-gray-500 mt-2">Here&apos;s how you performed</p>
              </div>

              <PlanUsageBanner />

              {activeUpsell === 'pro-retention' && (
                <div className="rounded-2xl bg-gradient-to-r from-indigo-50 to-emerald-50 border border-indigo-100 p-5 mb-6 text-center">
                  <p className="text-sm font-bold text-indigo-700 flex items-center justify-center gap-1.5">
                    <PartyPopper className="w-4 h-4" aria-hidden="true" /> Your Free Premium Session
                  </p>
                  <p className="text-sm text-gray-600 mt-1">
                    This report used the full 9-criteria examiner breakdown and premium voice — normally a Pro feature.
                    Your next sessions will use standard scoring unless you upgrade.
                  </p>
                  <a
                    href="/upgrade"
                    className="inline-block mt-3 bg-[#0F2356] text-white rounded-lg px-5 py-2 text-sm font-semibold hover:bg-[#0F2356]/90 transition"
                  >
                    Keep Full Reports — Upgrade to Pro →
                  </a>
                </div>
              )}

              <div className="rounded-2xl bg-emerald-50 border border-emerald-100 p-6 mb-6">
                <div className="grid grid-cols-3 divide-x divide-emerald-200">
                  <div className="flex flex-col items-center gap-1 pr-4">
                    <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Clinical Score</p>
                    <p className="text-2xl font-bold text-[#0F2356]">
                      {clinicalAverage}<span className="text-base font-normal text-gray-400">/6</span>
                    </p>
                  </div>
                  <div className="flex flex-col items-center gap-1 px-4">
                    <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">OET Band</p>
                    <div className="relative flex items-center justify-center">
                      <span
                        aria-hidden="true"
                        className="motion-safe:absolute motion-safe:inset-0 motion-safe:rounded-full motion-safe:bg-emerald-300/50 motion-safe:animate-[band-ring_1s_ease-out_1]"
                      />
                      <p className="relative text-4xl font-black text-[#0F2356] motion-safe:animate-[band-reveal_0.5s_cubic-bezier(0.34,1.56,0.64,1)_both]">
                        {oetGrade}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-col items-center gap-1 pl-4">
                    <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Linguistic Score</p>
                    <p className="text-2xl font-bold text-[#0F2356]">
                      {linguisticAverage}<span className="text-base font-normal text-gray-400">/6</span>
                    </p>
                  </div>
                </div>
              </div>

              {isNineCriteria ? (
                <>
                  <div className="mb-6">
                    <h2 className="text-sm font-bold text-[#0F2356] uppercase tracking-wide mb-3">Clinical Communication</h2>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {Object.entries(clinicalLabels).map(([key, label]) => renderCriterion(key, label))}
                    </div>
                  </div>

                  <div className="mb-6">
                    <h2 className="text-sm font-bold text-[#0F2356] uppercase tracking-wide mb-3">Linguistic Performance</h2>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {Object.entries(linguisticLabels).map(([key, label]) => renderCriterion(key, label))}
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="mb-6">
                    <h2 className="text-sm font-bold text-[#0F2356] uppercase tracking-wide mb-3">Your Report</h2>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {Object.entries(basicLabels).map(([key, label]) => renderCriterion(key, label))}
                    </div>
                  </div>

                  <div className="mb-6 rounded-2xl border border-dashed border-gray-300 bg-gray-50 p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-lg">🔒</span>
                      <p className="text-sm font-bold text-gray-500 uppercase tracking-wide">
                        Unlock the Full 9-Criteria Examiner Report
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-2 mb-4 opacity-60 select-none">
                      {LOCKED_CRITERIA_PREVIEW.map((label) => (
                        <div key={label} className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-gray-500 blur-[1.5px]">
                          {label} — ?/6
                        </div>
                      ))}
                    </div>
                    <a
                      href="/upgrade"
                      className="inline-block bg-[#0F2356] text-white rounded-lg px-5 py-2 text-sm font-semibold hover:bg-[#0F2356]/90 transition"
                    >
                      Upgrade to Pro →
                    </a>
                  </div>
                </>
              )}

              <div className="grid grid-cols-1 gap-4 mb-6 sm:grid-cols-2">
                <div className="rounded-2xl bg-emerald-50 border border-emerald-100 p-5">
                  <div className="flex items-center gap-2 mb-2">
                    <Trophy className="size-4 text-emerald-500" />
                    <p className="text-sm font-semibold text-emerald-600">Top Strength</p>
                  </div>
                  <p className="text-sm text-gray-700 leading-relaxed">{feedback.top_strength || 'No specific strength identified'}</p>
                </div>
                <div className="rounded-2xl bg-amber-50 border border-amber-100 p-5">
                  <div className="flex items-center gap-2 mb-2">
                    <Target className="size-4 text-amber-500" />
                    <p className="text-sm font-semibold text-amber-600">Focus Area</p>
                  </div>
                  <p className="text-sm text-gray-700 leading-relaxed">{feedback.top_improvement || 'Keep up the good work!'}</p>
                </div>
              </div>

              {feedback.examiner_summary && (
                <div className="rounded-2xl bg-white border border-gray-200 p-6 mb-6">
                  <h3 className="text-base font-bold text-[#0F2356] mb-3">Examiner Feedback</h3>
                  <p className="text-gray-700 leading-relaxed text-sm">{feedback.examiner_summary}</p>
                </div>
              )}

              {/* Pronunciation Analysis Section */}
              {(pronunciationResult || isAssessingPronunciation || pronunciationError) && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mt-6">

                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
                      <Mic className="w-4 h-4 text-blue-600" />
                    </div>
                    <h3 className="text-lg font-bold text-[#0F2356]">
                      Pronunciation Analysis
                    </h3>
                  </div>

                  {isAssessingPronunciation && (
                    <div className="flex items-center gap-2 text-gray-500 text-sm">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-[#10B981]"/>
                      Analyzing pronunciation...
                    </div>
                  )}

                  {pronunciationError && !isAssessingPronunciation && (
                    <p className="text-sm text-red-500">
                      We couldn't analyze your pronunciation this time. Your speaking score above is unaffected — please try again next session.
                    </p>
                  )}

                  {pronunciationResult && !isAssessingPronunciation && (
                    <>
                      {/* Azure scores if available */}
                      {pronunciationResult.has_azure && 
                       pronunciationResult.azure?.available && (
                        <div className="grid grid-cols-3 gap-4 mb-6">
                          <div className="text-center p-4 bg-gray-50 rounded-xl">
                            <div className="text-2xl font-bold text-[#0F2356]">
                              {pronunciationResult.azure.overall_score}
                            </div>
                            <div className="text-xs text-gray-500 mt-1">
                              Accuracy Score
                            </div>
                          </div>
                          <div className="text-center p-4 bg-gray-50 rounded-xl">
                            <div className="text-2xl font-bold text-[#10B981]">
                              {pronunciationResult.azure.fluency_score}
                            </div>
                            <div className="text-xs text-gray-500 mt-1">
                              Fluency Score
                            </div>
                          </div>
                          <div className="text-center p-4 bg-gray-50 rounded-xl">
                            <div className="text-2xl font-bold text-[#0F2356]">
                              {pronunciationResult.azure.completeness_score}
                            </div>
                            <div className="text-xs text-gray-500 mt-1">
                              Completeness
                            </div>
                          </div>
                        </div>
                      )}
                      
                      {/* Problem words from Azure */}
                      {pronunciationResult.has_azure && pronunciationResult.azure?.available &&
                       pronunciationResult.azure?.problem_words?.length > 0 && (
                        <div className="mb-6">
                          <h4 className="text-sm font-semibold text-gray-700 mb-3">
                            Words to Practice
                          </h4>
                          <div className="flex flex-wrap gap-2">
                            {pronunciationResult.azure.problem_words
                              .map((w: any, i: number) => (
                              <div key={i} 
                                className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm">
                                <span className="font-semibold text-red-700">
                                  {w.word}
                                </span>
                                <span className="text-red-500 ml-2">
                                  {w.accuracy_score}%
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      
                      {/* Indian accent pattern analysis */}
                      {pronunciationResult.pattern_analysis?.length > 0 && (
                        <div>
                          <h4 className="text-sm font-semibold text-gray-700 mb-3">
                            Indian Accent Patterns Detected
                          </h4>
                          <div className="space-y-3">
                            {pronunciationResult.pattern_analysis
                              .map((p: any, i: number) => (
                              <div key={i} 
                                className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                                <div className="flex items-start gap-3">
                                  <div className="w-6 h-6 rounded-full bg-amber-200 flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <span className="text-amber-700 text-xs font-bold">!</span>
                                  </div>
                                  <div>
                                    <p className="text-sm font-semibold text-amber-800">
                                      {p.pattern}
                                    </p>
                                    <p className="text-sm text-amber-700 mt-1">
                                      You said: 
                                      <span className="font-mono bg-amber-100 px-1 rounded mx-1">
                                        {p.word_said}
                                      </span>
                                      → Correct: 
                                      <span className="font-mono bg-emerald-100 text-emerald-700 px-1 rounded mx-1">
                                        {p.word_correct}
                                      </span>
                                    </p>
                                    <p className="text-xs text-amber-600 mt-1">
                                      {p.tip}
                                    </p>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      
                      {/* Only claim "no issues" when Azure actually assessed the audio — an empty text-pattern heuristic alone isn't evidence of clean pronunciation */}
                      {pronunciationResult.has_azure && pronunciationResult.azure?.available &&
                       pronunciationResult.pattern_analysis?.length === 0 &&
                       (!pronunciationResult.azure?.problem_words ||
                        pronunciationResult.azure.problem_words.length === 0) && (
                        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-emerald-200 flex items-center justify-center">
                            <span className="text-emerald-700 font-bold">✓</span>
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-emerald-800">
                              No pronunciation issues detected
                            </p>
                            <p className="text-xs text-emerald-600 mt-0.5">
                              Your speech was clear and easy to understand
                            </p>
                          </div>
                        </div>
                      )}

                      {/* Plan doesn't include phoneme-level scoring */}
                      {pronunciationResult.plan_limited && (
                        <p className="text-xs text-amber-600 mt-4 font-medium">
                          Phoneme-level scoring requires the Elite plan
                        </p>
                      )}

                      {/* Neutral fallback (unconfigured, no speech detected, or a typed turn) — never a fabricated positive result */}
                      {!pronunciationResult.plan_limited &&
                       !(pronunciationResult.has_azure && pronunciationResult.azure?.available) && (
                        <p className="text-xs text-gray-400 mt-4">
                          Pronunciation analysis is currently unavailable for this session.
                        </p>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Elite upgrade prompt for pronunciation — only when it's the page's single active upsell */}
              {activeUpsell === 'elite-pronunciation' && (
                <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5 mb-6">
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-full bg-amber-200 flex items-center justify-center shrink-0 mt-0.5">
                      <span className="text-amber-700 text-sm font-bold">!</span>
                    </div>
                    <div className="flex-1">
                      <h4 className="text-sm font-bold text-amber-800 mb-1">
                        Phoneme-Level Pronunciation Available
                      </h4>
                      <p className="text-sm text-amber-700 mb-3">
                        Upgrade to Elite for word-by-word pronunciation scoring with
                        accuracy, fluency, and completeness metrics.
                      </p>
                      <a
                        href="/upgrade"
                        className="inline-block bg-amber-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-amber-700 transition"
                      >
                        Upgrade to Elite →
                      </a>
                    </div>
                  </div>
                </div>
              )}

              {/* Compare */}
              {canCompare && (
                <div className="mb-6">
                  <button
                    onClick={handleCompare}
                    disabled={isComparing}
                    className="w-full py-3 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isComparing ? 'Comparing...' : 'Compare with Previous Attempt'}
                  </button>
                  {comparisonError && (
                    <p className="text-sm text-amber-600 text-center mt-2">{comparisonError}</p>
                  )}
                </div>
              )}

              {comparisonResult && (
                <div className="bg-white rounded-2xl shadow-lg p-6 border border-gray-200 mb-6">
                  <h2 className="text-2xl font-bold mb-4">
                    Progress: {comparisonResult.overall_trajectory === 'improving' ? '📈 Improving' : comparisonResult.overall_trajectory === 'worse' ? '📉 Declining' : '➡️ Same'}
                  </h2>
                  {comparisonResult.improved?.length > 0 && (
                    <div className="mb-4">
                      <h3 className="font-bold text-green-700 mb-2">Improved</h3>
                      <ul className="list-disc list-inside space-y-1">
                        {comparisonResult.improved.map((item: string, i: number) => (
                          <li key={i} className="text-sm text-green-800">{item}</li>
                        ))}
                      </ul>
                      {comparisonResult.improved_reasons?.map((reason: string, i: number) => (
                        <p key={i} className="mt-1 text-xs text-gray-600 italic">{reason}</p>
                      ))}
                    </div>
                  )}
                  {comparisonResult.declined?.length > 0 && (
                    <div className="mb-4">
                      <h3 className="font-bold text-red-700 mb-2">Declined</h3>
                      <ul className="list-disc list-inside space-y-1">
                        {comparisonResult.declined.map((item: string, i: number) => (
                          <li key={i} className="text-sm text-red-800">{item}</li>
                        ))}
                      </ul>
                      {comparisonResult.declined_reasons?.map((reason: string, i: number) => (
                        <p key={i} className="mt-1 text-xs text-gray-600 italic">{reason}</p>
                      ))}
                    </div>
                  )}
                  {comparisonResult.next_focus?.length > 0 && (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                      <h3 className="font-bold text-amber-800 mb-2">Next Focus</h3>
                      <ul className="list-disc list-inside space-y-1">
                        {comparisonResult.next_focus.map((item: string, i: number) => (
                          <li key={i} className="text-sm text-amber-900">{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Transcript */}
              <div className="mb-8">
                <h3 className="text-base font-bold text-[#0F2356] mb-4">Conversation Transcript</h3>
                <div className="flex flex-col gap-4">
                  {history.map((msg, i) => (
                    <div key={i} className={`flex gap-3 ${msg.role === 'nurse' ? 'flex-row-reverse' : 'flex-row'}`}>
                      <Avatar className="size-8 shrink-0">
                        <AvatarFallback className={`text-xs font-bold text-white ${msg.role === 'nurse' ? 'bg-[#0F2356]' : 'bg-gray-400'}`}>
                          {msg.role === 'nurse' ? 'N' : 'P'}
                        </AvatarFallback>
                      </Avatar>
                      <div className={`flex flex-col gap-1 max-w-[75%] ${msg.role === 'nurse' ? 'items-end' : 'items-start'}`}>
                        <span className="text-xs text-gray-400">
                          {msg.role === 'nurse' ? 'You (Nurse)' : 'Patient'}
                        </span>
                        <div className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                          msg.role === 'nurse' ? 'bg-[#0F2356] text-white' : 'bg-gray-100 text-gray-800'
                        }`}>
                          {msg.content}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="text-center py-16">
              <p className="text-gray-500 mb-4">Scoring is temporarily unavailable</p>
              <div className="mb-8">
                <h3 className="text-base font-bold text-[#0F2356] mb-4">Conversation Transcript</h3>
                <div className="flex flex-col gap-4 max-w-2xl mx-auto">
                  {history.map((msg, i) => (
                    <div key={i} className={`flex gap-3 ${msg.role === 'nurse' ? 'flex-row-reverse' : 'flex-row'}`}>
                      <Avatar className="size-8 shrink-0">
                        <AvatarFallback className={`text-xs font-bold text-white ${msg.role === 'nurse' ? 'bg-[#0F2356]' : 'bg-gray-400'}`}>
                          {msg.role === 'nurse' ? 'N' : 'P'}
                        </AvatarFallback>
                      </Avatar>
                      <div className={`flex flex-col gap-1 max-w-[75%] ${msg.role === 'nurse' ? 'items-end' : 'items-start'}`}>
                        <span className="text-xs text-gray-400">
                          {msg.role === 'nurse' ? 'You (Nurse)' : 'Patient'}
                        </span>
                        <div className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                          msg.role === 'nurse' ? 'bg-[#0F2356] text-white' : 'bg-gray-100 text-gray-800'
                        }`}>
                          {msg.content}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <Separator className="mb-6" />

          {weakestCriterion && selectedScenario && (
            <button
              onClick={handleRetryWeakest}
              className="w-full rounded-xl bg-emerald-500 text-white py-3 text-sm font-semibold hover:bg-emerald-600 transition mb-3 flex items-center justify-center gap-2"
            >
              <Target className="size-4" />
              Retry — Focus on {weakestCriterion.label} ({weakestCriterion.score}/6)
            </button>
          )}

          <div className="flex gap-3 flex-wrap">
            <button
              onClick={handleTryAgain}
              className="flex-1 rounded-xl bg-[#0F2356] text-white py-3 text-sm font-semibold hover:bg-[#0F2356]/90 transition"
            >
              Try Another Scenario
            </button>
            <button
              onClick={() => router.push('/dashboard')}
              className="flex-1 rounded-xl border border-[#0F2356] text-[#0F2356] py-3 text-sm font-semibold hover:bg-[#0F2356]/5 transition"
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
