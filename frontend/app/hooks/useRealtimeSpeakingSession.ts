'use client'

import { useCallback, useEffect, useRef, useState, Dispatch, SetStateAction } from 'react'
import { getCurrentSession } from '@/lib/supabase'

export interface RealtimeChatMessage {
  role: 'nurse' | 'patient'
  content: string
}

interface RealtimeScenarioLike {
  id: number
  patient_gender?: string
}

interface UseRealtimeSpeakingSessionOptions {
  scenario: RealtimeScenarioLike | null
  convHistory: RealtimeChatMessage[]
  setConvHistory: Dispatch<SetStateAction<RealtimeChatMessage[]>>
  sessionId: number | null
  setSessionId: Dispatch<SetStateAction<number | null>>
  /** Blocks starting a new session while the previous one is being scored/ended. */
  isEnding: boolean
  /**
   * Called when the backend reports the realtime voice provider itself is
   * unusable (connect failure or an unrecoverable mid-session provider
   * error) with `fallback_available: true` -- the quota session_id is still
   * valid, so the caller should switch to useSpeakingSession (the legacy
   * Deepgram/Gemini/TTS pipeline) and keep the conversation going rather
   * than treat this as a dead end.
   */
  onProviderUnavailable?: () => void
}

interface UseRealtimeSpeakingSessionReturn {
  isListening: boolean
  isProcessing: boolean
  isSpeaking: boolean
  /** Always '' — Realtime only gives us the nurse's transcript once it's final, not word-by-word. */
  interimText: string
  sttError: string | null
  dismissSttError: () => void
  /** Always false — kept so this hook is a drop-in replacement for useSpeakingSession's return shape. */
  usingFallbackStt: boolean
  startListening: () => void
  stopListening: () => void
  sendTypedMessage: (text: string) => Promise<void>
  stopSpeaking: () => void
}

// Fallback only used if the backend's session.ready never arrives (should
// never happen in practice -- the router always sends it before either
// side exchanges audio) so audio capture/playback still has a sane rate.
const DEFAULT_SAMPLE_RATE = 24000
// Batch worklet output before sending over the socket -- at 24kHz a single
// 128-sample render quantum is ~5ms of audio; sending one WS frame per
// quantum would be ~200 tiny messages/sec for no benefit. ~40ms per frame
// keeps latency low while cutting message count by ~8x.
const SEND_BATCH_MS = 40

export function useRealtimeSpeakingSession({
  scenario,
  convHistory,
  setConvHistory,
  sessionId,
  setSessionId,
  isEnding,
  onProviderUnavailable,
}: UseRealtimeSpeakingSessionOptions): UseRealtimeSpeakingSessionReturn {
  const [isListening, setIsListening] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [sttError, setSttError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const micStreamRef = useRef<MediaStream | null>(null)
  const workletNodeRef = useRef<AudioWorkletNode | null>(null)
  const micSourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const silentGainRef = useRef<GainNode | null>(null)

  // Audio config the active provider requires, from session.ready --
  // OpenAI and Gemini Live do not use the same input sample rate. See
  // backend/app/services/realtime/capabilities.py.
  const inputSampleRateRef = useRef(DEFAULT_SAMPLE_RATE)
  const outputSampleRateRef = useRef(DEFAULT_SAMPLE_RATE)
  const sendBatchSamplesRef = useRef(Math.round((DEFAULT_SAMPLE_RATE * SEND_BATCH_MS) / 1000))

  // Mic-capture batching (main thread) -- see sendBatchSamplesRef above.
  const pendingSamplesRef = useRef<Int16Array[]>([])
  const pendingSampleCountRef = useRef(0)

  // Gapless playback scheduling.
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([])
  const nextPlaybackTimeRef = useRef(0)
  const suppressPlaybackRef = useRef(false)

  // Streaming patient transcript -- true while the current response's text
  // is still being appended to the last convHistory bubble.
  const patientTurnActiveRef = useRef(false)

  const flushPendingAudio = useCallback(() => {
    const chunks = pendingSamplesRef.current
    if (chunks.length === 0) return
    const totalSamples = pendingSampleCountRef.current
    const merged = new Int16Array(totalSamples)
    let offset = 0
    for (const chunk of chunks) {
      merged.set(chunk, offset)
      offset += chunk.length
    }
    pendingSamplesRef.current = []
    pendingSampleCountRef.current = 0

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(merged.buffer)
    }
  }, [])

  const interruptPlayback = useCallback(() => {
    for (const src of activeSourcesRef.current) {
      try {
        src.onended = null
        src.stop()
      } catch {
        // already stopped
      }
    }
    activeSourcesRef.current = []
    nextPlaybackTimeRef.current = audioContextRef.current?.currentTime ?? 0
    setIsSpeaking(false)
  }, [])

  const playPcm16Chunk = useCallback((bytes: ArrayBuffer) => {
    const ctx = audioContextRef.current
    if (!ctx || suppressPlaybackRef.current) return

    const int16 = new Int16Array(bytes)
    const float32 = new Float32Array(int16.length)
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / (int16[i] < 0 ? 0x8000 : 0x7fff)
    }

    const buffer = ctx.createBuffer(1, float32.length, outputSampleRateRef.current)
    buffer.copyToChannel(float32, 0)

    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(ctx.destination)

    const startAt = Math.max(ctx.currentTime, nextPlaybackTimeRef.current)
    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source)
      if (activeSourcesRef.current.length === 0) setIsSpeaking(false)
    }
    activeSourcesRef.current.push(source)
    setIsSpeaking(true)
    source.start(startAt)
    nextPlaybackTimeRef.current = startAt + buffer.duration
  }, [])

  const teardown = useCallback(() => {
    workletNodeRef.current?.port.close()
    workletNodeRef.current?.disconnect()
    workletNodeRef.current = null

    micSourceRef.current?.disconnect()
    micSourceRef.current = null

    silentGainRef.current?.disconnect()
    silentGainRef.current = null

    micStreamRef.current?.getTracks().forEach((t) => t.stop())
    micStreamRef.current = null

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(() => {})
    }
    audioContextRef.current = null

    if (wsRef.current) {
      wsRef.current.onopen = null
      wsRef.current.onmessage = null
      wsRef.current.onerror = null
      wsRef.current.onclose = null
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close()
      }
      wsRef.current = null
    }

    pendingSamplesRef.current = []
    pendingSampleCountRef.current = 0
    interruptPlayback()
    patientTurnActiveRef.current = false
    suppressPlaybackRef.current = false
  }, [interruptPlayback])

  const stopListening = useCallback(() => {
    teardown()
    setIsListening(false)
    setIsProcessing(false)
  }, [teardown])

  useEffect(() => {
    return () => {
      teardown()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (sttError) {
      const timer = setTimeout(() => setSttError(null), 8000)
      return () => clearTimeout(timer)
    }
  }, [sttError])

  const appendPatientDelta = useCallback((delta: string) => {
    setConvHistory((prev) => {
      if (patientTurnActiveRef.current && prev.length > 0 && prev[prev.length - 1].role === 'patient') {
        const updated = [...prev]
        updated[updated.length - 1] = {
          role: 'patient',
          content: updated[updated.length - 1].content + delta,
        }
        return updated
      }
      // A fresh patient turn started -- release any suppression stopSpeaking()
      // left behind for the *previous* turn, so muting one reply doesn't
      // silently mute every reply for the rest of the session.
      patientTurnActiveRef.current = true
      suppressPlaybackRef.current = false
      return [...prev, { role: 'patient', content: delta }]
    })
  }, [setConvHistory])

  const handleServerEvent = useCallback((event: any) => {
    switch (event.type) {
      case 'transcript.delta':
        setIsProcessing(true)
        appendPatientDelta(event.delta || '')
        break
      case 'transcript.final':
        setConvHistory((prev) => [...prev, { role: 'nurse', content: event.transcript || '' }])
        break
      case 'response.done':
        patientTurnActiveRef.current = false
        setIsProcessing(false)
        break
      case 'interrupted':
        interruptPlayback()
        break
      case 'session.warning':
        // Backend-enforced 5-minute cap is about to close the connection --
        // purely informational today (no dedicated UI), surfaced via the
        // same error banner other transient session copy uses.
        setSttError(`Voice session ending in ${event.seconds_remaining ?? 30}s.`)
        break
      case 'session.ended':
        if (event.reason === 'timeout') {
          setSttError('Voice session time limit reached.')
        }
        stopListening()
        break
      case 'error':
        // Every server-side error path in the backend proxy closes the
        // socket, so there's no "recoverable" error to leave the mic/
        // AudioContext running for -- always tear down alongside it. When
        // the provider itself is down (fallback_available), hand off to
        // the legacy pipeline instead of just dead-ending the student.
        setSttError(event.error || 'Voice session error')
        stopListening()
        if (event.fallback_available) {
          onProviderUnavailable?.()
        }
        break
      default:
        break
    }
  }, [appendPatientDelta, setConvHistory, interruptPlayback, stopListening, onProviderUnavailable])

  const startListening = useCallback(async () => {
    if (isListening || isProcessing || isEnding || !scenario) return
    setSttError(null)

    if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === 'undefined') {
      setSttError('Live voice mode is not supported in this browser.')
      return
    }

    try {
      const session = await getCurrentSession()
      if (!session?.access_token) {
        setSttError('Your session has expired. Please sign in again.')
        return
      }

      const wsUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}`
        .replace(/^http:/, 'ws:')
        .replace(/^https:/, 'wss:') + '/speaking/realtime/stream'

      const ws = new WebSocket(wsUrl)
      ws.binaryType = 'arraybuffer'
      wsRef.current = ws

      // Wait specifically for the backend's session.ready -- not just the
      // socket opening -- because it carries the audio sample rates the
      // active provider requires (OpenAI and Gemini Live differ), and the
      // AudioWorklet below must be constructed with the correct input rate
      // from the start; it can't be changed after the fact.
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => {
          ws.send(JSON.stringify({
            token: session.access_token,
            scenario_id: scenario.id,
            session_id: sessionId,
          }))
        }
        ws.onerror = () => reject(new Error('connection_failed'))
        ws.onmessage = (event) => {
          if (typeof event.data !== 'string') return
          try {
            const parsed = JSON.parse(event.data)
            if (parsed.type === 'error') {
              setSttError(parsed.error === 'session_limit_reached'
                ? 'You have used all your sessions this month.'
                : parsed.error === 'Unauthorized or missing scenario_id'
                  ? 'Your session has expired. Please sign in again.'
                  : (parsed.error || 'Voice session error'))
              reject(new Error('handled'))
              return
            }
            if (parsed.type === 'session.ready' && typeof parsed.session_id === 'number') {
              setSessionId(parsed.session_id)
              inputSampleRateRef.current = parsed.input_sample_rate || DEFAULT_SAMPLE_RATE
              outputSampleRateRef.current = parsed.output_sample_rate || DEFAULT_SAMPLE_RATE
              sendBatchSamplesRef.current = Math.round((inputSampleRateRef.current * SEND_BATCH_MS) / 1000)
              resolve()
            }
          } catch {
            // ignore non-JSON text frames
          }
        }
      })

      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          try {
            handleServerEvent(JSON.parse(event.data))
          } catch {
            // ignore non-JSON text frames
          }
        } else {
          setIsProcessing(true)
          playPcm16Chunk(event.data as ArrayBuffer)
        }
      }

      ws.onerror = () => {
        setSttError('Connection lost. Please try again.')
        stopListening()
      }

      ws.onclose = () => {
        setIsListening(false)
      }

      const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext
      const audioContext = new AudioContextCtor({ sampleRate: inputSampleRateRef.current })
      audioContextRef.current = audioContext
      nextPlaybackTimeRef.current = audioContext.currentTime

      const micStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      micStreamRef.current = micStream

      await audioContext.audioWorklet.addModule('/worklets/pcm-processor.js')
      const workletNode = new AudioWorkletNode(audioContext, 'pcm-processor', {
        processorOptions: { targetSampleRate: inputSampleRateRef.current },
      })
      workletNodeRef.current = workletNode

      workletNode.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
        const chunk = new Int16Array(e.data)
        pendingSamplesRef.current.push(chunk)
        pendingSampleCountRef.current += chunk.length
        if (pendingSampleCountRef.current >= sendBatchSamplesRef.current) {
          flushPendingAudio()
        }
      }

      const micSource = audioContext.createMediaStreamSource(micStream)
      micSourceRef.current = micSource

      // Route through a silent gain node (not straight to destination) so
      // the worklet stays part of an active graph -- some browsers stop
      // calling process() on nodes that never reach the destination -- while
      // never letting the user hear their own raw mic input back.
      const silentGain = audioContext.createGain()
      silentGain.gain.value = 0
      silentGainRef.current = silentGain

      micSource.connect(workletNode)
      workletNode.connect(silentGain)
      silentGain.connect(audioContext.destination)

      setIsListening(true)
    } catch (err) {
      console.error('Failed to start realtime session:', err)
      if (!(err instanceof Error) || err.message !== 'handled') {
        setSttError('Please allow microphone access to start the live conversation.')
      }
      teardown()
    }
    // stopListening/teardown/handleServerEvent/playPcm16Chunk/flushPendingAudio
    // are all useCallback-stable given their own deps, so this list only
    // reflects the values that actually change what startListening does.
  }, [isListening, isProcessing, isEnding, scenario, sessionId, setSessionId, handleServerEvent, playPcm16Chunk, flushPendingAudio, stopListening, teardown])

  const sendTypedMessage = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || wsRef.current?.readyState !== WebSocket.OPEN) return
    setConvHistory((prev) => [...prev, { role: 'nurse', content: trimmed }])
    // Typed input still has to reach OpenAI through the same socket, but the
    // backend proxy only forwards binary frames to input_audio_buffer.append
    // today -- there's no text-turn path yet. Surfacing that plainly beats
    // silently doing nothing.
    setSttError('Typed messages are not yet supported in live voice mode — please speak your response.')
  }, [setConvHistory])

  const stopSpeaking = useCallback(() => {
    suppressPlaybackRef.current = true
    interruptPlayback()
  }, [interruptPlayback])

  const dismissSttError = useCallback(() => setSttError(null), [])

  return {
    isListening,
    isProcessing,
    isSpeaking,
    interimText: '',
    sttError,
    dismissSttError,
    usingFallbackStt: false,
    startListening,
    stopListening,
    sendTypedMessage,
    stopSpeaking,
  }
}
