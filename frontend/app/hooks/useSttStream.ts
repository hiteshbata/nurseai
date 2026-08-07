'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { getCurrentSession } from '@/lib/supabase'
import { useMicrophone } from './useMicrophone'

export interface UseSttStreamReturn {
  isListening: boolean
  isConnecting: boolean
  interimText: string
  sttError: string | null
  dismissSttError: () => void
  usingFallbackStt: boolean
  startListening: () => void
  stopListening: () => void
}

const STT_MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm']
const STT_TIMESLICE_MS = 250
const INTERIM_THROTTLE_MS = 100
// See useSpeakingSession's original comment: Deepgram's own endpointing
// (1500ms) has already elapsed by the time UtteranceEnd/speech_final fires.
const SILENCE_FINALIZE_MS = 1500
const INTERIM_FINALIZE_MS = 1200

/**
 * Deepgram streaming STT: mic capture -> /speaking/stt/stream websocket ->
 * accumulated transcript -> onFinalTranscript once silence is detected.
 * Falls back to the browser's built-in SpeechRecognition if the websocket
 * never connects. No AI/TTS concerns here -- extracted out of
 * useSpeakingSession so callers that just need "did the mic pick up speech"
 * (e.g. the onboarding warm-up check) don't have to pull in the whole
 * chat/scoring pipeline.
 */
export function useSttStream(onFinalTranscript: (text: string) => void): UseSttStreamReturn {
  const [isListening, setIsListening] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [interimText, setInterimText] = useState('')
  const [sttError, setSttError] = useState<string | null>(null)
  const [usingFallbackStt, setUsingFallbackStt] = useState(false)

  const sttWsRef = useRef<WebSocket | null>(null)
  const sttRecognitionRef = useRef<any>(null)
  const deepgramEverConnectedRef = useRef(false)
  const accumulatedTranscriptRef = useRef('')
  const silenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastInterimUpdate = useRef(0)
  const onFinalTranscriptRef = useRef(onFinalTranscript)
  onFinalTranscriptRef.current = onFinalTranscript

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

  const finalizeSilence = useCallback(() => {
    const text = accumulatedTranscriptRef.current.trim()
    if (!text) return
    accumulatedTranscriptRef.current = ''
    setInterimText('')
    stopListening()
    onFinalTranscriptRef.current(text)
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
        onFinalTranscriptRef.current(finalText.trim())
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
  }, [stopListening, setInterimTextThrottled])

  const startListening = useCallback(() => {
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
  }, [stopListening, startFallbackListening, usingFallbackStt, sttMic.start, finalizeSilence, setInterimTextThrottled])

  const dismissSttError = useCallback(() => setSttError(null), [])

  return {
    isListening,
    isConnecting,
    interimText,
    sttError,
    dismissSttError,
    usingFallbackStt,
    startListening,
    stopListening,
  }
}
