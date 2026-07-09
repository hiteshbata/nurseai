'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

interface UseAudioPlaybackReturn {
  isSpeaking: boolean
  /** Plays a Blob returned from the TTS endpoint via an HTMLAudioElement. */
  playBlob: (blob: Blob) => Promise<void>
  /** Browser SpeechSynthesis fallback for when the TTS endpoint is unavailable. */
  speakFallback: (text: string) => void
  /** Mirrors the app's existing "stop" behavior: cancels any in-flight SpeechSynthesis utterance. */
  stop: () => void
}

/**
 * Exclusively owns playing audio returned from the server (or the browser
 * SpeechSynthesis fallback when it isn't available). Fetching the audio is
 * the caller's concern.
 */
export function useAudioPlayback(): UseAudioPlaybackReturn {
  const [isSpeaking, setIsSpeaking] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const playBlob = useCallback((blob: Blob): Promise<void> => {
    return new Promise((resolve, reject) => {
      const audioUrl = URL.createObjectURL(blob)
      const audio = new Audio(audioUrl)
      audioRef.current = audio

      setIsSpeaking(true)
      audio.onended = () => {
        setIsSpeaking(false)
        URL.revokeObjectURL(audioUrl)
        resolve()
      }
      audio.onerror = () => {
        setIsSpeaking(false)
        URL.revokeObjectURL(audioUrl)
        reject(new Error('Audio playback failed'))
      }

      audio.play().catch((err) => {
        setIsSpeaking(false)
        URL.revokeObjectURL(audioUrl)
        reject(err)
      })
    })
  }, [])

  const speakFallback = useCallback((text: string) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    // Strip *stage direction* markup (e.g. "*starts to tear up*") before
    // reading aloud -- it's written for the transcript, not to be spoken.
    // Keeps the original if stripping would leave nothing to say.
    const spoken = text.replace(/\*[^*\n]{1,80}\*/g, '').replace(/[ \t]{2,}/g, ' ').trim() || text
    const utterance = new SpeechSynthesisUtterance(spoken)
    utterance.rate = 0.95
    window.speechSynthesis.speak(utterance)
  }, [])

  const stop = useCallback(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
  }, [])

  useEffect(() => {
    return () => stop()
  }, [stop])

  return { isSpeaking, playBlob, speakFallback, stop }
}
