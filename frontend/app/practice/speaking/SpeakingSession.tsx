'use client'

import { useCallback, useEffect, useRef, useState, Dispatch, SetStateAction } from 'react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { CheckCircle2, Mic, Trophy, Target, Captions, PartyPopper } from 'lucide-react'
import VoiceOrb from '@/components/VoiceOrb'
import PlanUsageBanner from '@/components/PlanUsageBanner'
import api from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import { useMicrophone } from '@/app/hooks/useMicrophone'
import { useSpeakingSession } from '@/app/hooks/useSpeakingSession'
import { useRealtimeSpeakingSession } from '@/app/hooks/useRealtimeSpeakingSession'
import {
  Scenario,
  ChatMessage,
  Submission,
  Phase,
  sanitizeText,
  scoreColor,
  scoreToGrade,
  STAGES_NAV,
  clinicalLabels,
  linguisticLabels,
  basicLabels,
  LOCKED_CRITERIA_PREVIEW,
  PREP_SECONDS,
  SESSION_RECORDING_MIME_CANDIDATES,
  inRealtimeRollout,
} from './shared'

interface SpeakingSessionProps {
  phase: Phase
  selectedScenario: Scenario | null
  userId: string | undefined
  router: { push: (href: string) => void }
  readingTime: number
  examSeconds: number
  setExamSeconds: Dispatch<SetStateAction<number>>
  convHistory: ChatMessage[]
  setConvHistory: Dispatch<SetStateAction<ChatMessage[]>>
  history: ChatMessage[]
  sessionId: number | null
  setSessionId: Dispatch<SetStateAction<number | null>>
  feedback: any
  onSessionEnd: (chatHistory: ChatMessage[], resultFeedback: any) => void
  typedResponse: string
  setTypedResponse: Dispatch<SetStateAction<string>>
  autoListen: boolean
  setAutoListen: Dispatch<SetStateAction<boolean>>
  captionsOn: boolean
  setCaptionsOn: Dispatch<SetStateAction<boolean>>
  isEnding: boolean
  setIsEnding: Dispatch<SetStateAction<boolean>>
  isScoring: boolean
  setIsScoring: Dispatch<SetStateAction<boolean>>
  conversationError: string | null
  setConversationError: Dispatch<SetStateAction<string | null>>
  pastSubmissions: Submission[]
  setPastSubmissions: Dispatch<SetStateAction<Submission[]>>
  comparisonResult: any
  setComparisonResult: Dispatch<SetStateAction<any>>
  comparisonError: string | null
  setComparisonError: Dispatch<SetStateAction<string | null>>
  isComparing: boolean
  setIsComparing: Dispatch<SetStateAction<boolean>>
  pronunciationResult: any
  setPronunciationResult: Dispatch<SetStateAction<any>>
  isAssessingPronunciation: boolean
  setIsAssessingPronunciation: Dispatch<SetStateAction<boolean>>
  pronunciationError: boolean
  setPronunciationError: Dispatch<SetStateAction<boolean>>
  onTryAgain: () => void
  onRetryWeakest: () => void
  setPhase: Dispatch<SetStateAction<Phase>>
  // Full Mock Test mode: which role play (1 or 2) this session is, or null/undefined
  // outside a mock. Swaps the standalone-practice stepper for exam-style labeling.
  mockRoleplay?: 1 | 2 | null
}

export default function SpeakingSession({
  phase,
  selectedScenario,
  userId,
  router,
  readingTime,
  examSeconds,
  setExamSeconds,
  convHistory,
  setConvHistory,
  history,
  sessionId,
  setSessionId,
  feedback,
  onSessionEnd,
  typedResponse,
  setTypedResponse,
  autoListen,
  setAutoListen,
  captionsOn,
  setCaptionsOn,
  isEnding,
  setIsEnding,
  isScoring,
  setIsScoring,
  conversationError,
  setConversationError,
  pastSubmissions,
  setPastSubmissions,
  comparisonResult,
  setComparisonResult,
  comparisonError,
  setComparisonError,
  isComparing,
  setIsComparing,
  pronunciationResult,
  setPronunciationResult,
  isAssessingPronunciation,
  setIsAssessingPronunciation,
  pronunciationError,
  setPronunciationError,
  onTryAgain,
  onRetryWeakest,
  setPhase,
  mockRoleplay,
}: SpeakingSessionProps) {
  const [scoringElapsed, setScoringElapsed] = useState(0)
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
  const useRealtime = inRealtimeRollout(userId) && !useLegacyFallback
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

  const handleTypedSubmit = useCallback(async () => {
    const text = typedResponse.trim()
    if (!text || isProcessing || isEnding) return
    setTypedResponse('')
    await session.sendTypedMessage(text)
    // session.sendTypedMessage specifically, not the whole session object --
    // useSpeakingSession returns a fresh object every render (isListening/
    // interimText/etc. are state), which would otherwise recreate this on
    // every render instead of only when the message-sending logic changes.
  }, [typedResponse, isProcessing, isEnding, session.sendTypedMessage, setTypedResponse])

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
      onSessionEnd(convHistory, {
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
      onSessionEnd(convHistory, null)
    } finally {
      setIsScoring(false)
    }
    // session.stopListening/stopSpeaking and sessionMic.stop specifically,
    // not the whole session/sessionMic objects -- both hooks return a fresh
    // object every render (their internal state changes), which would
    // otherwise recreate this on every render instead of only when
    // selectedScenario/convHistory/sessionId/examSeconds actually change.
  }, [selectedScenario, convHistory, sessionId, examSeconds, session.stopListening, session.stopSpeaking, sessionMic.stop, onSessionEnd, setConversationError, setIsEnding, setIsScoring, setIsAssessingPronunciation, setPronunciationError, setPronunciationResult])

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

  const handleToggleListening = useCallback(() => {
    if (session.isListening) session.stopListening()
    else session.startListening()
  }, [session.isListening, session.stopListening, session.startListening])

  const canCompare = pastSubmissions.length > 1

  const fetchSubmissions = useCallback(async () => {
    if (!selectedScenario) return
    try {
      const res = await api.get('/submissions', {
        params: { module: 'speaking', scenario_id: selectedScenario.id }
      })
      setPastSubmissions(res.data || [])
    } catch (e) {
      console.error('Failed to fetch submissions:', e)
    }
  }, [selectedScenario, setPastSubmissions])

  useEffect(() => {
    if (phase === 'result' && selectedScenario) {
      fetchSubmissions()
    }
  }, [phase, selectedScenario, fetchSubmissions])

  const handleCompare = useCallback(async () => {
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
  }, [selectedScenario, pastSubmissions, setIsComparing, setComparisonError, setComparisonResult])

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
          {mockRoleplay ? (
            <div className="flex justify-center mb-8">
              <div className="rounded-2xl bg-[#0F2356] text-white px-5 py-2.5 shadow-md">
                <p className="text-[11px] font-semibold uppercase tracking-widest text-blue-200">Full Mock Test</p>
                <p className="text-sm font-semibold">Speaking · Role play {mockRoleplay} of 2</p>
              </div>
            </div>
          ) : (
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
          )}

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
              {/* No escape hatch back to the scenario picker in a mock -- role plays
                  lock behind you, same as every other section once it's started. */}
              {!mockRoleplay && (
                <button
                  onClick={onTryAgain}
                  className="flex-1 rounded-xl py-2.5 text-sm font-semibold text-gray-600 hover:bg-gray-100 transition"
                >
                  Back to Scenarios
                </button>
              )}
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
            isConnecting={session.isConnecting}
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
            onToggle={handleToggleListening}
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
              onClick={onRetryWeakest}
              className="w-full rounded-xl bg-emerald-500 text-white py-3 text-sm font-semibold hover:bg-emerald-600 transition mb-3 flex items-center justify-center gap-2"
            >
              <Target className="size-4" />
              Retry — Focus on {weakestCriterion.label} ({weakestCriterion.score}/6)
            </button>
          )}

          <div className="flex gap-3 flex-wrap">
            <button
              onClick={onTryAgain}
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
