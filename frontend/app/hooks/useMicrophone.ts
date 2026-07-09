'use client'

import { useCallback, useRef, useState, useEffect } from 'react'

// Flat (non-discriminated-union) shape: the project's tsconfig has
// "strict": false, and under strictNullChecks:false TS does not reliably
// narrow a boolean-literal-discriminated union in ternaries/if-else --
// `reason` is simply optional and only meaningful when ok is false.
export interface MicStartResult {
  ok: boolean
  reason?: 'unsupported' | 'permission-denied' | 'unknown'
}

interface UseMicrophoneOptions {
  /** MediaRecorder mimeType candidates, tried in order via MediaRecorder.isTypeSupported. */
  mimeTypeCandidates: string[]
  /** Passed straight through to MediaRecorder.start(timeslice). */
  timesliceMs: number
  /** Called for every chunk as it becomes available (for live-streaming use sites). */
  onDataAvailable?: (chunk: Blob) => void
}

interface UseMicrophoneReturn {
  isRecording: boolean
  stream: MediaStream | null
  start: () => Promise<MicStartResult>
  /** Stops recording and resolves with the full recording as a single Blob. */
  stop: () => Promise<Blob | null>
}

/**
 * Exclusively owns getUserMedia + MediaRecorder mechanics. Chunk routing
 * (stream to a socket vs. accumulate for upload) is the caller's concern —
 * this hook only captures and reports what it captured.
 */
export function useMicrophone({ mimeTypeCandidates, timesliceMs, onDataAvailable }: UseMicrophoneOptions): UseMicrophoneReturn {
  const [isRecording, setIsRecording] = useState(false)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const onDataAvailableRef = useRef(onDataAvailable)
  onDataAvailableRef.current = onDataAvailable

  const start = useCallback(async (): Promise<MicStartResult> => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      return { ok: false, reason: 'unsupported' }
    }

    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = mediaStream
      setStream(mediaStream)

      const mimeType = mimeTypeCandidates.find((t) => MediaRecorder.isTypeSupported(t)) || mimeTypeCandidates[0]
      const mediaRecorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined)
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
          onDataAvailableRef.current?.(event.data)
        }
      }

      mediaRecorder.start(timesliceMs)
      setIsRecording(true)
      return { ok: true }
    } catch (err) {
      console.error('Microphone access failed:', err)
      return { ok: false, reason: 'permission-denied' }
    }
  }, [mimeTypeCandidates, timesliceMs])

  const stop = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const mediaRecorder = mediaRecorderRef.current
      setIsRecording(false)
      if (!mediaRecorder || mediaRecorder.state === 'inactive') {
        resolve(null)
        return
      }

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mediaRecorder.mimeType || mimeTypeCandidates[0] })
        resolve(blob)
      }

      mediaRecorder.stop()
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
      setStream(null)
    })
  }, [mimeTypeCandidates])

  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          mediaRecorderRef.current.stop()
        } catch {}
      }
      streamRef.current?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  return { isRecording, stream, start, stop }
}
