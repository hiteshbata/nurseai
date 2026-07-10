'use client'

import { useCallback, useEffect, useRef, useState, Dispatch, SetStateAction } from 'react'
import api from '@/lib/api'
import { getCurrentSession } from '@/lib/supabase'
import { useMicrophone } from './useMicrophone'
import { useAudioPlayback } from './useAudioPlayback'

export interface SpeakingChatMessage {
  role: 'nurse' | 'patient'
  content: string
}

interface SpeakingScenarioLike {
  id: number
  patient_gender?: string
  voice_config?: {
    voice_name?: string
    speaking_rate?: number
    pitch?: number
    language_code?: string
  }
}

interface UseSpeakingSessionOptions {
  scenario: SpeakingScenarioLike | null
  convHistory: SpeakingChatMessage[]
  setConvHistory: Dispatch<SetStateAction<SpeakingChatMessage[]>>
  sessionId: number | null
  setSessionId: Dispatch<SetStateAction<number | null>>
  /** Blocks starting a new listen while the session is being scored/ended. */
  isEnding: boolean
  /** When true, the mic reopens on its own once the patient's reply finishes playing. */
  autoListen: boolean
}

interface UseSpeakingSessionReturn {
  isListening: boolean
  isConnecting: boolean
  isProcessing: boolean
  isSpeaking: boolean
  interimText: string
  sttError: string | null
  dismissSttError: () => void
  usingFallbackStt: boolean
  startListening: () => void
  stopListening: () => void
  sendTypedMessage: (text: string) => Promise<void>
  stopSpeaking: () => void
}

const STT_MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm']
const STT_TIMESLICE_MS = 250
const INTERIM_THROTTLE_MS = 100
// Deepgram's own endpointing/utterance_end_ms server-side silence detection
// (1500ms) has already elapsed by the time UtteranceEnd/speech_final fires.
// 500ms on top of that was cutting off non-native speakers mid-thought when
// they paused to breathe mid-answer -- widened to 1500ms for more natural
// clinical pacing.
const SILENCE_FINALIZE_MS = 1500
// A bare `is_final` segment only means this chunk of text stabilized -- it
// does NOT mean Deepgram thinks the user stopped talking (no endpointing
// wait backs it). Using the same 500ms here risked cutting people off
// mid-thought between phrases, so this path keeps a larger buffer.
const INTERIM_FINALIZE_MS = 1200

export function useSpeakingSession({
  scenario,
  convHistory,
  setConvHistory,
  sessionId,
  setSessionId,
  isEnding,
  autoListen,
}: UseSpeakingSessionOptions): UseSpeakingSessionReturn {
  const [isListening, setIsListening] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [interimText, setInterimText] = useState('')
  const [sttError, setSttError] = useState<string | null>(null)
  const [usingFallbackStt, setUsingFallbackStt] = useState(false)

  const audioPlayback = useAudioPlayback()

  const sttWsRef = useRef<WebSocket | null>(null)
  const sttRecognitionRef = useRef<any>(null)
  const deepgramEverConnectedRef = useRef(false)
  const accumulatedTranscriptRef = useRef('')
  const silenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sendToAIRef = useRef<((text: string) => Promise<void>) | null>(null)
  const startListeningRef = useRef<(() => void) | null>(null)
  const lastInterimUpdate = useRef(0)
  const autoListenRef = useRef(autoListen)

  useEffect(() => {
    autoListenRef.current = autoListen
  }, [autoListen])

  const sttMic = useMicrophone({
    mimeTypeCandidates: STT_MIME_CANDIDATES,
    timesliceMs: STT_TIMESLICE_MS,
    onDataAvailable: (chunk) => {
      if (sttWsRef.current?.readyState === WebSocket.OPEN) {
        sttWsRef.current.send(chunk)
      }
    },
  })

  const setInterimTextThrottled = useCallback((text: string) => {
    const now = Date.now()
    if (text === '' || now - lastInterimUpdate.current > INTERIM_THROTTLE_MS) {
      lastInterimUpdate.current = now
      setInterimText(text)
    }
  }, [])

  const stopListening = useCallback(() => {
    sttMic.stop()
    if (sttWsRef.current) {
      sttWsRef.current.close()
      sttWsRef.current = null
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
    setIsConnecting(false)
    setInterimText('')
    // Depend on sttMic.stop specifically, not the whole sttMic object --
    // useMicrophone returns a fresh object every render (isRecording/stream
    // are state), which would otherwise recreate stopListening (and every
    // callback that depends on it) on every render instead of only when
    // something it actually uses changes.
  }, [sttMic.stop])

  useEffect(() => {
    return () => {
      stopListening()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (sttError) {
      const timer = setTimeout(() => setSttError(null), 8000)
      return () => clearTimeout(timer)
    }
  }, [sttError])

  const speakPatientReply = useCallback(async (text: string, sessionIdForCall: number | null) => {
    const voiceConfig = scenario?.voice_config ?? {
      voice_name: 'en-GB-Wavenet-A',
      speaking_rate: 0.95,
      pitch: 0.0,
      language_code: 'en-GB',
    }

    try {
      const response = await api.post(
        '/speaking/tts',
        { text, session_id: sessionIdForCall, gender: scenario?.patient_gender, ...voiceConfig },
        { responseType: 'blob' }
      )

      const contentType = String(response.headers['content-type'] || '')
      if (contentType.includes('application/json')) {
        audioPlayback.speakFallback(text)
        return
      }

      await audioPlayback.playBlob(response.data)
    } catch (err) {
      audioPlayback.speakFallback(text)
    }
    // audioPlayback.speakFallback/playBlob are individually stable (both are
    // useCallback with empty deps in useAudioPlayback); depending on the
    // whole audioPlayback object would recreate this every render instead,
    // since isSpeaking state makes that object fresh each render.
  }, [scenario, audioPlayback.speakFallback, audioPlayback.playBlob])

  const sendToAI = useCallback(async (nurseText: string) => {
    if (!scenario) return
    setIsProcessing(true)
    try {
      const res = await api.post('/speaking/chat', {
        scenario_id: scenario.id,
        message: nurseText,
        history: convHistory.map(m => ({ role: m.role, content: m.content })),
        session_id: sessionId,
      })
      const patientReply = res.data.patient_reply
      const updatedHistory = (res.data.updated_history || []).map((m: any) => ({
        role: m.role as 'nurse' | 'patient',
        content: m.content,
      }))
      const effectiveSessionId = typeof res.data.session_id === 'number' ? res.data.session_id : sessionId

      // Fire the TTS request as soon as we have text -- ahead of the
      // non-essential history/session-id state updates below -- so audio
      // fetch+playback starts at the earliest possible moment.
      const speakingDone = speakPatientReply(patientReply, effectiveSessionId)

      setConvHistory(updatedHistory)
      if (typeof res.data.session_id === 'number') {
        setSessionId(res.data.session_id)
      }
      // Reopen the mic once the patient's audio actually finishes (not a
      // fixed delay guessed from text length) -- only when the user hasn't
      // turned auto-listen off in favor of tapping the orb each turn.
      if (autoListenRef.current) {
        speakingDone.finally(() => startListeningRef.current?.())
      }
    } catch (e: any) {
      console.error('Chat error:', e)
      setSttError("The patient couldn't respond — please try again.")
    } finally {
      setIsProcessing(false)
    }
  }, [convHistory, scenario, sessionId, speakPatientReply, setConvHistory, setSessionId])

  useEffect(() => {
    sendToAIRef.current = sendToAI
  }, [sendToAI])

  const finalizeSilence = useCallback(() => {
    const text = accumulatedTranscriptRef.current.trim()
    if (!text) return
    accumulatedTranscriptRef.current = ''
    setInterimText('')
    stopListening()
    setConvHistory(prev => [...prev, { role: 'nurse', content: text }])
    sendToAIRef.current?.(text)
  }, [stopListening, setConvHistory])

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
  }, [stopListening, sendToAI, setConvHistory, setInterimTextThrottled])

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
    setIsConnecting(true)

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
          setIsConnecting(false)
          ws.close()
          return
        }
        ws.send(JSON.stringify({ token: session.access_token }))

        const result = await sttMic.start()
        if (!result.ok) {
          setSttError('Please allow microphone access to record')
          setIsConnecting(false)
          ws.close()
          return
        }
        setIsListening(true)
        setIsConnecting(false)
      } catch (err) {
        console.error('Failed to start recording:', err)
        setSttError('Please allow microphone access to record')
        setIsConnecting(false)
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
          setIsConnecting(false)
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
          silenceTimeoutRef.current = setTimeout(finalizeSilence, SILENCE_FINALIZE_MS)
          return
        }

        if (data.transcript) {
          if (data.is_final) {
            accumulatedTranscriptRef.current += (accumulatedTranscriptRef.current ? ' ' : '') + data.transcript.trim()
            setInterimText('')
            if (silenceTimeoutRef.current) clearTimeout(silenceTimeoutRef.current)
            silenceTimeoutRef.current = setTimeout(finalizeSilence, INTERIM_FINALIZE_MS)
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
        setIsConnecting(false)
        ws.close()
        startFallbackListening()
      } else {
        setSttError('Connection lost. Please try again.')
        setIsListening(false)
        setIsConnecting(false)
      }
    }

    ws.onclose = () => {
      if (!deepgramEverConnectedRef.current && !usingFallbackStt) {
        setSttError('Could not connect to speech service. Please try again.')
      }
      setIsListening(false)
      setIsConnecting(false)
      setInterimText('')
    }
    // sttMic.start specifically (not the whole sttMic object) -- see the
    // stopListening dependency comment above for why.
  }, [isProcessing, isEnding, stopListening, startFallbackListening, usingFallbackStt, sttMic.start, finalizeSilence, setInterimTextThrottled])

  useEffect(() => {
    startListeningRef.current = startListening
  }, [startListening])

  const sendTypedMessage = useCallback(async (text: string) => {
    stopListening()
    setConvHistory(prev => [...prev, { role: 'nurse', content: text }])
    await sendToAI(text)
  }, [stopListening, sendToAI, setConvHistory])

  const dismissSttError = useCallback(() => setSttError(null), [])
  const stopSpeaking = useCallback(() => audioPlayback.stop(), [audioPlayback.stop])

  return {
    isListening,
    isConnecting,
    isProcessing,
    isSpeaking: audioPlayback.isSpeaking,
    interimText,
    sttError,
    dismissSttError,
    usingFallbackStt,
    startListening,
    stopListening,
    sendTypedMessage,
    stopSpeaking,
  }
}
