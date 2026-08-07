'use client'

import { useCallback, useEffect, useRef, useState, Dispatch, SetStateAction } from 'react'
import api, { isUpgradeRequiredError } from '@/lib/api'
import { useSttStream } from './useSttStream'
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
  /**
   * Never provided here. This path plays the patient's reply through an
   * HTMLAudioElement (see useAudioPlayback), which has no analyser to sample,
   * so the orb falls back to synthetic waveform motion. Declared only so
   * SpeakingSession can read it off either hook without a type guard --
   * see useRealtimeSpeakingSession for the implemented version.
   */
  getOutputLevel?: () => number
}

export function useSpeakingSession({
  scenario,
  convHistory,
  setConvHistory,
  sessionId,
  setSessionId,
  isEnding,
  autoListen,
}: UseSpeakingSessionOptions): UseSpeakingSessionReturn {
  const [isProcessing, setIsProcessing] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)

  const audioPlayback = useAudioPlayback()

  const sendToAIRef = useRef<((text: string) => Promise<void>) | null>(null)
  const startListeningRef = useRef<(() => void) | null>(null)
  const autoListenRef = useRef(autoListen)

  useEffect(() => {
    autoListenRef.current = autoListen
  }, [autoListen])

  const handleFinalTranscript = useCallback((text: string) => {
    setConvHistory(prev => [...prev, { role: 'nurse', content: text }])
    sendToAIRef.current?.(text)
  }, [setConvHistory])

  const stt = useSttStream(handleFinalTranscript)

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
        await audioPlayback.speakFallback(text)
        return
      }

      await audioPlayback.playBlob(response.data)
    } catch (err) {
      await audioPlayback.speakFallback(text)
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
      setChatError(
        isUpgradeRequiredError(e)
          ? 'This conversation requires a paid plan — see the upgrade prompt above.'
          : "The patient couldn't respond — please try again."
      )
    } finally {
      setIsProcessing(false)
    }
  }, [convHistory, scenario, sessionId, speakPatientReply, setConvHistory, setSessionId])

  useEffect(() => {
    sendToAIRef.current = sendToAI
  }, [sendToAI])

  const startListening = useCallback(() => {
    if (isProcessing || isEnding) return
    setChatError(null)
    stt.startListening()
  }, [isProcessing, isEnding, stt.startListening])

  useEffect(() => {
    startListeningRef.current = startListening
  }, [startListening])

  const sendTypedMessage = useCallback(async (text: string) => {
    stt.stopListening()
    setConvHistory(prev => [...prev, { role: 'nurse', content: text }])
    await sendToAI(text)
  }, [stt.stopListening, sendToAI, setConvHistory])

  const dismissSttError = useCallback(() => {
    setChatError(null)
    stt.dismissSttError()
  }, [stt.dismissSttError])
  const stopSpeaking = useCallback(() => audioPlayback.stop(), [audioPlayback.stop])

  return {
    isListening: stt.isListening,
    isConnecting: stt.isConnecting,
    isProcessing,
    isSpeaking: audioPlayback.isSpeaking,
    interimText: stt.interimText,
    sttError: stt.sttError || chatError,
    dismissSttError,
    usingFallbackStt: stt.usingFallbackStt,
    startListening,
    stopListening: stt.stopListening,
    sendTypedMessage,
    stopSpeaking,
  }
}
