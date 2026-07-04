'use client'

import { useEffect, useRef, useState } from 'react'

interface VoiceOrbProps {
  isListening: boolean
  isProcessing: boolean
  isEnding: boolean
  canEndSession?: boolean
  onToggle: () => void
  onEndSession: () => void
}

export default function VoiceOrb({ isListening, isProcessing, isEnding, canEndSession = true, onToggle, onEndSession }: VoiceOrbProps) {
  const [orbScale, setOrbScale] = useState(1)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const micStreamRef = useRef<MediaStream | null>(null)
  const animFrameRef = useRef<number | null>(null)
  const orbRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = 'voice-orb-styles'
    if (!document.getElementById(id)) {
      const s = document.createElement('style')
      s.id = id
      s.textContent = `
        @keyframes orb-breathe {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.06); }
        }
        @keyframes orb-pulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.04); }
        }
        @keyframes ripple {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(2.2); opacity: 0; }
        }
        @keyframes spin-arc {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `
      document.head.appendChild(s)
    }
  }, [])

  useEffect(() => {
    if (!isListening) {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current)
        animFrameRef.current = null
      }
      setOrbScale(1)
      return
    }

    const setupMic = async () => {
      try {
        if (!micStreamRef.current) {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
          micStreamRef.current = stream
        }
        if (!audioContextRef.current) {
          const ctx = new AudioContext()
          audioContextRef.current = ctx
        }
        const ctx = audioContextRef.current
        const source = ctx.createMediaStreamSource(micStreamRef.current)
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        source.connect(analyser)
        analyserRef.current = analyser
      } catch {
        // Mic access denied — orb stays at default scale
      }
    }
    setupMic()

    const sampleVolume = () => {
      const analyser = analyserRef.current
      if (analyser) {
        const data = new Uint8Array(analyser.frequencyBinCount)
        analyser.getByteTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < data.length; i++) {
          const val = data[i] / 128 - 1
          sum += val * val
        }
        const rms = Math.sqrt(sum / data.length)
        setOrbScale(1 + rms * 1.3)
      }
      animFrameRef.current = requestAnimationFrame(sampleVolume)
    }

    animFrameRef.current = requestAnimationFrame(sampleVolume)

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current)
        animFrameRef.current = null
      }
    }
  }, [isListening])

  useEffect(() => {
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
      if (audioContextRef.current) audioContextRef.current.close()
      if (micStreamRef.current) {
        micStreamRef.current.getTracks().forEach(t => t.stop())
      }
    }
  }, [])

  const orbColor = isEnding ? '#6B7280' : isProcessing ? '#F59E0B' : isListening ? '#10B981' : '#0F2356'

  let statusText = 'Tap to speak'
  if (isEnding) statusText = 'Ending session...'
  else if (isProcessing) statusText = 'Processing...'
  else if (isListening) statusText = 'Listening...'

  let orbAnimation = ''
  if (isEnding) orbAnimation = 'none'
  else if (isProcessing) orbAnimation = 'none'
  else if (isListening) orbAnimation = 'orb-pulse 1s ease-in-out infinite'
  else orbAnimation = 'orb-breathe 3s ease-in-out infinite'

  return (
    <div className="flex-shrink-0 bg-white border-t border-gray-100 p-4 relative" style={{ height: 140 }}>
      <button
        onClick={onEndSession}
        disabled={isEnding || !canEndSession}
        title={!canEndSession ? 'Speak or type at least one response before ending the session' : undefined}
        className="absolute top-4 right-4 rounded-xl border border-gray-300 text-gray-600 hover:border-red-400 hover:text-red-500 hover:bg-red-50 px-4 py-2 text-sm font-semibold transition disabled:opacity-50"
      >
        {isEnding ? 'Ending...' : 'End Session'}
      </button>

      <div className="flex flex-col items-center justify-center h-full gap-2">
        <div className="relative flex items-center justify-center" style={{ width: 96, height: 96 }}>
          {isListening && (
            <>
              <span
                className="absolute inset-0 rounded-full"
                style={{
                  backgroundColor: orbColor,
                  animation: 'ripple 1.5s ease-out infinite',
                }}
              />
              <span
                className="absolute inset-0 rounded-full"
                style={{
                  backgroundColor: orbColor,
                  animation: 'ripple 1.5s ease-out infinite',
                  animationDelay: '0.75s',
                }}
              />
            </>
          )}

          {isProcessing && (
            <svg
              className="absolute"
              width="80"
              height="80"
              viewBox="0 0 80 80"
              style={{ animation: 'spin-arc 1s linear infinite' }}
            >
              <circle
                cx="40" cy="40" r="36"
                fill="none"
                stroke="#F59E0B"
                strokeWidth="4"
                strokeDasharray="50 150"
                strokeLinecap="round"
              />
            </svg>
          )}

          <div
            ref={orbRef}
            className="rounded-full relative z-10"
            style={{
              width: 64,
              height: 64,
              backgroundColor: orbColor,
              animation: orbAnimation,
              transform: isListening ? `scale(${orbScale})` : undefined,
              transition: 'background-color 0.3s ease',
              cursor: 'pointer',
            }}
            onClick={onToggle}
          />
        </div>

        <p className="text-xs text-gray-400">{statusText}</p>
      </div>
    </div>
  )
}
