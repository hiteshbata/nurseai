'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useSupabaseSession, getCurrentSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { CheckCircle2, Mic, Trophy, Target, ArrowLeft } from 'lucide-react'
import VoiceOrb from '@/components/VoiceOrb'
import { trackEvent } from '@/lib/analytics'

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
const PREP_SECONDS = 180

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
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const [pronunciationResult, setPronunciationResult] = useState<any>(null)
  const [isAssessingPronunciation, setIsAssessingPronunciation] = useState(false)
  const [pronunciationError, setPronunciationError] = useState(false)
  const [hasRestoredSession, setHasRestoredSession] = useState(false)

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
              setSelectedScenario(savedScenario)
              setPhase(parsed.phase)
              setReadingTime(typeof parsed.readingTime === 'number' ? parsed.readingTime : PREP_SECONDS)
              setExamSeconds(typeof parsed.examSeconds === 'number' ? parsed.examSeconds : 0)
              setConvHistory(Array.isArray(parsed.convHistory) ? parsed.convHistory : [])
              setHistory(Array.isArray(parsed.history) ? parsed.history : [])
              setSessionId(typeof parsed.sessionId === 'number' ? parsed.sessionId : null)
              setFeedback(parsed.feedback ?? null)
              setComparisonResult(null)
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
    setPhase('briefing')
  }

  const handleStartConversation = async () => {
    setExamSeconds(0)
    await startAudioRecording()
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

  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [isEnding, setIsEnding] = useState(false)
  const [interimText, setInterimText] = useState('')
  const [sttError, setSttError] = useState<string | null>(null)
  const [usingFallbackStt, setUsingFallbackStt] = useState(false)
  const sttWsRef = useRef<WebSocket | null>(null)
  const sttMediaRecorderRef = useRef<MediaRecorder | null>(null)
  const sttStreamRef = useRef<MediaStream | null>(null)
  const sttRecognitionRef = useRef<any>(null)
  const deepgramEverConnectedRef = useRef(false)
  const accumulatedTranscriptRef = useRef('')
  const silenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sendToAIRef = useRef<((text: string) => Promise<void>) | null>(null)
  const startListeningRef = useRef<(() => void) | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const lastInterimUpdate = useRef(0)
  const interimThrottleMs = 100

  const setInterimTextThrottled = (text: string) => {
    const now = Date.now()
    if (text === '' || now - lastInterimUpdate.current > interimThrottleMs) {
      lastInterimUpdate.current = now
      setInterimText(text)
    }
  }

  const stopListening = useCallback(() => {
    if (sttMediaRecorderRef.current && sttMediaRecorderRef.current.state !== 'inactive') {
      sttMediaRecorderRef.current.stop()
    }
    if (sttWsRef.current) {
      sttWsRef.current.close()
      sttWsRef.current = null
    }
    if (sttStreamRef.current) {
      sttStreamRef.current.getTracks().forEach(t => t.stop())
      sttStreamRef.current = null
    }
    if (sttRecognitionRef.current) {
      try { sttRecognitionRef.current.stop() } catch {}
      sttRecognitionRef.current = null
    }
    if (silenceTimeoutRef.current) {
      clearTimeout(silenceTimeoutRef.current)
      silenceTimeoutRef.current = null
    }
    setIsListening(false)
    setInterimText('')
  }, [])

  // Unmount cleanup: without this, navigating away mid-conversation leaves
  // the mic, MediaRecorder, and STT WebSocket running in the background
  // (browser recording indicator stays lit), and a pending silence timer
  // can still fire finalizeSilence afterward -- which calls sendToAIRef,
  // firing a stray /speaking/chat request for a conversation the user
  // already left.
  useEffect(() => {
    return () => {
      stopListening()
      if (mediaRecorderRef.current) {
        try {
          if (mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.stop()
          }
          mediaRecorderRef.current.stream?.getTracks().forEach(track => track.stop())
        } catch {}
      }
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel()
      }
    }
  }, [stopListening])

  useEffect(() => {
    if (sttError) {
      const timer = setTimeout(() => setSttError(null), 4000)
      return () => clearTimeout(timer)
    }
  }, [sttError])

  const fallbackTTS = useCallback((text: string) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.95
    window.speechSynthesis.speak(utterance)
  }, [])

  const speakPatientReply = useCallback(async (text: string, sessionIdForCall: number | null) => {
    const voiceConfig = selectedScenario?.voice_config ?? {
      voice_name: "en-GB-Wavenet-A",
      speaking_rate: 0.95,
      pitch: 0.0,
      language_code: "en-GB",
    }

    try {
      const response = await api.post(
        "/speaking/tts",
        { text, session_id: sessionIdForCall, gender: selectedScenario?.patient_gender, ...voiceConfig },
        { responseType: "blob" }
      )

      const contentType = String(response.headers["content-type"] || "")

      if (contentType.includes("application/json")) {
        fallbackTTS(text)
        return
      }

      const blob = response.data
      const audioUrl = URL.createObjectURL(blob)
      const audio = new Audio(audioUrl)

      setIsSpeaking(true)
      audio.onended = () => {
        setIsSpeaking(false)
        URL.revokeObjectURL(audioUrl)
      }
      audio.onerror = () => {
        setIsSpeaking(false)
        fallbackTTS(text)
      }

      await audio.play()
    } catch (err) {
      setIsSpeaking(false)
      fallbackTTS(text)
    }
  }, [selectedScenario, fallbackTTS])

  const sendToAI = useCallback(async (nurseText: string) => {
    if (!selectedScenario) return
    setIsProcessing(true)
    try {
      const res = await api.post('/speaking/chat', {
        scenario_id: selectedScenario.id,
        message: nurseText,
        history: convHistory.map(m => ({ role: m.role, content: m.content })),
        session_id: sessionId,
      })
      const patientReply = res.data.patient_reply
      const updatedHistory = (res.data.updated_history || []).map((m: any) => ({
        role: m.role as 'nurse' | 'patient',
        content: m.content,
      }))
      setConvHistory(updatedHistory)
      const effectiveSessionId = typeof res.data.session_id === 'number' ? res.data.session_id : sessionId
      if (typeof res.data.session_id === 'number') {
        setSessionId(res.data.session_id)
      }
      speakPatientReply(patientReply, effectiveSessionId)
      setTimeout(() => startListeningRef.current?.(), 300)
    } catch (e: any) {
      console.error('Chat error:', e)
      setSttError("The patient couldn't respond — please try again.")
    } finally {
      setIsProcessing(false)
    }
  }, [convHistory, selectedScenario, sessionId, speakPatientReply])

  useEffect(() => {
    sendToAIRef.current = sendToAI
  }, [sendToAI])

  const handleTypedSubmit = useCallback(async () => {
    const text = typedResponse.trim()
    if (!text || isProcessing || isEnding) return
    setTypedResponse('')
    stopListening()
    setConvHistory(prev => [...prev, { role: 'nurse', content: text }])
    await sendToAI(text)
  }, [typedResponse, isProcessing, isEnding, stopListening, sendToAI])

  const finalizeSilence = useCallback(() => {
    const text = accumulatedTranscriptRef.current.trim()
    if (!text) return
    accumulatedTranscriptRef.current = ''
    setInterimText('')
    stopListening()
    setConvHistory(prev => [...prev, { role: 'nurse', content: text }])
    sendToAIRef.current?.(text)
  }, [stopListening])

  const startFallbackListening = useCallback(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      setSttError('Speech recognition not available in this browser')
      return
    }
    stopListening()
    const recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'

    recognition.onresult = (event: any) => {
      let finalText = ''
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalText += event.results[i][0].transcript + ' '
        } else {
          interim += event.results[i][0].transcript
        }
      }
      setInterimTextThrottled(interim)
      if (finalText.trim()) {
        recognition.stop()
        setIsListening(false)
        setInterimText('')
        const trimmed = finalText.trim()
        setConvHistory(prev => [...prev, { role: 'nurse', content: trimmed }])
        sendToAI(trimmed)
      }
    }

    recognition.onend = () => {
      setIsListening(false)
    }

    recognition.onerror = (event: any) => {
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        console.error('Fallback STT error:', event.error)
      }
      setIsListening(false)
    }

    sttRecognitionRef.current = recognition
    recognition.start()
    setIsListening(true)
  }, [isProcessing, isEnding, stopListening, sendToAI])

  const startListening = useCallback(() => {
    if (isProcessing || isEnding) return
    setSttError(null)
    deepgramEverConnectedRef.current = false
    accumulatedTranscriptRef.current = ''

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setSttError('Audio recording is not supported in this browser. Type your response below to continue.')
      return
    }

    if (usingFallbackStt) {
      startFallbackListening()
      return
    }

    stopListening()

    const wsUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}`
      .replace(/^http:/, 'ws:')
      .replace(/^https:/, 'wss:') + '/speaking/stt/stream'

    const ws = new WebSocket(wsUrl)
    sttWsRef.current = ws

    ws.onopen = async () => {
      deepgramEverConnectedRef.current = true
      try {
        const session = await getCurrentSession()
        if (!session?.access_token) {
          setSttError('Your session has expired. Please sign in again.')
          ws.close()
          return
        }
        ws.send(JSON.stringify({ token: session.access_token }))

        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        sttStreamRef.current = stream

        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm'
        const mediaRecorder = new MediaRecorder(stream, { mimeType })
        sttMediaRecorderRef.current = mediaRecorder

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0 && sttWsRef.current?.readyState === WebSocket.OPEN) {
            sttWsRef.current.send(event.data)
          }
        }

        mediaRecorder.start(250)
        setIsListening(true)
      } catch (err) {
        console.error('Failed to start recording:', err)
        setSttError('Please allow microphone access to record')
        ws.close()
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.error) {
          console.error('STT error:', data.error)
          setUsingFallbackStt(true)
          setSttError('Using browser speech recognition as fallback')
          stopListening()
          startFallbackListening()
          return
        }

        const msgType = data.type || 'Results'

        if (msgType === 'UtteranceEnd' || data.speech_final === true) {
          if (data.transcript) {
            accumulatedTranscriptRef.current += (accumulatedTranscriptRef.current ? ' ' : '') + data.transcript.trim()
          }
          setInterimText('')
          if (silenceTimeoutRef.current) clearTimeout(silenceTimeoutRef.current)
          silenceTimeoutRef.current = setTimeout(finalizeSilence, 2000)
          return
        }

        if (data.transcript) {
          if (data.is_final) {
            accumulatedTranscriptRef.current += (accumulatedTranscriptRef.current ? ' ' : '') + data.transcript.trim()
            setInterimText('')
            if (silenceTimeoutRef.current) clearTimeout(silenceTimeoutRef.current)
            silenceTimeoutRef.current = setTimeout(finalizeSilence, 2000)
          } else {
            setInterimTextThrottled(data.transcript)
          }
        }
      } catch (e) {
        // ignore non-JSON messages
      }
    }

    ws.onerror = () => {
      if (!deepgramEverConnectedRef.current) {
        setUsingFallbackStt(true)
        setSttError('Using browser speech recognition as fallback')
        ws.close()
        startFallbackListening()
      } else {
        setSttError('Connection lost. Please try again.')
        setIsListening(false)
      }
    }

    ws.onclose = () => {
      if (!deepgramEverConnectedRef.current && !usingFallbackStt) {
        setSttError('Could not connect to speech service. Please try again.')
      }
      setIsListening(false)
      setInterimText('')
    }
  }, [isProcessing, isEnding, stopListening, sendToAI, startFallbackListening, usingFallbackStt])

  useEffect(() => {
    startListeningRef.current = startListening
  }, [startListening])

  const startAudioRecording = async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
        setSttError('Audio recording is not supported in this browser. Use typed practice below or switch browsers.')
        return false
      }
      const stream = await navigator.mediaDevices.getUserMedia(
        { audio: true }
      )
      
      // Determine supported format
      const mimeType = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/ogg')
        ? 'audio/ogg'
        : 'audio/mp4'
      
      const mediaRecorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }
      
      mediaRecorder.start(1000) // collect chunks every 1 second
      setSttError(null)
      return true
    } catch (err) {
      console.error('Audio recording failed:', err)
      setSttError('Microphone is unavailable. You can continue with typed practice or allow microphone access.')
      return false
    }
  }

  const stopAudioRecording = (): Promise<Blob | null> => {
    return new Promise((resolve) => {
      if (!mediaRecorderRef.current) {
        resolve(null)
        return
      }
      
      mediaRecorderRef.current.onstop = () => {
        const audioBlob = new Blob(
          audioChunksRef.current,
          { type: mediaRecorderRef.current?.mimeType || 'audio/webm' }
        )
        resolve(audioBlob)
      }
      
      mediaRecorderRef.current.stop()
      mediaRecorderRef.current.stream
        .getTracks()
        .forEach(track => track.stop())
    })
  }

  const handleEndConversation = useCallback(async () => {
    if (!selectedScenario) return
    const nurseTurns = convHistory.filter(m => m.role === 'nurse')
    if (nurseTurns.length === 0) {
      setSttError('Speak or type at least one response before ending the session.')
      return
    }
    setIsEnding(true)
    stopListening()
    window.speechSynthesis.cancel()
    setIsProcessing(true)
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
        const audioBlob = await stopAudioRecording()
        
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
            setPronunciationResult(pronRes.data.pronunciation)
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
      setIsProcessing(false)
    }
  }, [selectedScenario, convHistory, sessionId, stopListening])

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
  }, [convHistory, interimText])

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
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading scenarios...</div>
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

          {scenarios.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-xl shadow">
              <p className="text-xl text-gray-500 mb-2">No scenarios available</p>
              <p className="text-gray-400">Ask an admin to create speaking scenarios</p>
            </div>
          ) : (
            <>
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
                      className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
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
                        className={`px-3 py-1.5 rounded-full text-xs font-semibold transition ${
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

              <div className="grid md:grid-cols-2 gap-6">
              {scenarios
                .filter((s) => filterSpecialty === 'all' || (s.specialty || 'Uncategorized') === filterSpecialty)
                .map((s) => {
                const card = s.nurse_card || {}
                const tasks = card.tasks || []
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
                    className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 flex flex-col gap-4 hover:shadow-md hover:scale-[1.01] transition-all duration-200 cursor-pointer"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
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
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-[#0F2356]">Conversation</p>
              {isSpeaking && (
                <span className="text-xs text-blue-500 animate-pulse">Patient speaking…</span>
              )}
            </div>
            <p className="font-mono text-base font-bold text-[#0F2356]">
              {String(Math.floor(examSeconds / 60)).padStart(2, '0')}:{String(examSeconds % 60).padStart(2, '0')}
            </p>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
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
                {interimText && (
                  <div className="flex gap-3 flex-row-reverse">
                    <Avatar className="size-8 shrink-0">
                      <AvatarFallback className="text-xs font-bold text-white bg-[#0F2356]">N</AvatarFallback>
                    </Avatar>
                    <div className="flex flex-col gap-1 items-end max-w-[70%]">
                      <span className="text-xs text-gray-400">You (Nurse)</span>
                      <div className="rounded-2xl px-4 py-2.5 text-sm leading-relaxed bg-[#0F2356]/80 text-white/80">
                        {interimText}...
                      </div>
                    </div>
                  </div>
                )}
                {isProcessing && (
                  <div className="flex gap-3 flex-row">
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
          </div>

          <VoiceOrb
            isListening={isListening}
            isProcessing={isProcessing}
            isEnding={isEnding}
            canEndSession={convHistory.some(m => m.role === 'nurse')}
            onToggle={() => isListening ? stopListening() : startListening()}
            onEndSession={handleEndConversation}
          />

          {sttError && (
            <p className="text-xs text-red-500 text-center py-1">{sttError}</p>
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

              {isPremiumTrial && (
                <div className="rounded-2xl bg-gradient-to-r from-indigo-50 to-emerald-50 border border-indigo-100 p-5 mb-6 text-center">
                  <p className="text-sm font-bold text-indigo-700">🎉 Your Free Premium Session</p>
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
                    <p className="text-4xl font-black text-[#0F2356]">{oetGrade}</p>
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
                      {pronunciationResult.azure?.problem_words?.length > 0 && (
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
                      
                      {/* No issues found */}
                      {pronunciationResult.pattern_analysis?.length === 0 && 
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
                      
                      {/* Azure not configured message */}
                      {!pronunciationResult.has_azure && !pronunciationResult.plan_limited && (
                        <p className="text-xs text-gray-400 mt-4">
                          Add AZURE_SPEECH_KEY to .env for 
                          word-level pronunciation scoring
                        </p>
                      )}
                      {!pronunciationResult.has_azure && pronunciationResult.plan_limited && (
                        <p className="text-xs text-amber-600 mt-4 font-medium">
                          Phoneme-level scoring requires the Elite plan
                        </p>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Elite upgrade prompt for pronunciation */}
              {pronunciationResult && !isAssessingPronunciation && pronunciationResult.plan_limited && (
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
