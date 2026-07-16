'use client'

import { memo, useEffect, useRef, useState } from 'react'

interface VoiceOrbProps {
  isListening: boolean
  isConnecting?: boolean
  isProcessing: boolean
  isSpeaking?: boolean
  isEnding: boolean
  canEndSession?: boolean
  statusOverride?: string
  onToggle: () => void
  onEndSession: () => void
}

function VoiceOrb({ isListening, isConnecting = false, isProcessing, isSpeaking = false, isEnding, canEndSession = true, statusOverride, onToggle, onEndSession }: VoiceOrbProps) {
  const [orbScale, setOrbScale] = useState(1)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const micStreamRef = useRef<MediaStream | null>(null)
  const animFrameRef = useRef<number | null>(null)

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

  const orbColor = isEnding ? '#6B7280' : isConnecting ? '#6366F1' : isProcessing ? '#F59E0B' : isSpeaking ? '#3B82F6' : isListening ? '#10B981' : '#0F2356'
  const orbDisabled = isConnecting || isProcessing || isSpeaking || isEnding

  let statusText = 'Tap to speak'
  if (isEnding) statusText = statusOverride || 'Ending session...'
  else if (isConnecting) statusText = 'Connecting...'
  else if (isProcessing) statusText = 'Processing...'
  else if (isSpeaking) statusText = 'Patient speaking...'
  else if (isListening) statusText = 'Listening...'

  let orbAnimation = ''
  if (isEnding) orbAnimation = 'none'
  else if (isConnecting) orbAnimation = 'none'
  else if (isProcessing) orbAnimation = 'none'
  else if (isSpeaking) orbAnimation = 'orb-pulse 0.6s ease-in-out infinite'
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

          {isSpeaking && (
            <div className="absolute z-20 flex items-end gap-1" style={{ height: 28 }}>
              {[0, 1, 2, 3].map((i) => (
                <span
                  key={i}
                  className="w-1 rounded-full bg-white/90"
                  style={{
                    height: 28,
                    animation: `orb-speak-bar ${0.5 + i * 0.1}s ease-in-out infinite`,
                    animationDelay: `${i * 0.08}s`,
                  }}
                />
              ))}
            </div>
          )}

          {(isProcessing || isConnecting) && (
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
                stroke={isConnecting ? '#6366F1' : '#F59E0B'}
                strokeWidth="4"
                strokeDasharray="50 150"
                strokeLinecap="round"
              />
            </svg>
          )}

          <button
            type="button"
            aria-label="Microphone"
            aria-pressed={isListening}
            aria-disabled={orbDisabled}
            title={orbDisabled ? "You can't respond while this is in progress" : undefined}
            className="rounded-full relative z-10 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
            style={{
              width: 64,
              height: 64,
              backgroundColor: orbColor,
              animation: orbAnimation,
              transform: isListening ? `scale(${orbScale})` : undefined,
              transition: 'background-color 0.3s ease, opacity 0.2s ease',
              opacity: orbDisabled ? 0.5 : 1,
              cursor: orbDisabled ? 'not-allowed' : 'pointer',
            }}
            onClick={() => { if (!orbDisabled) onToggle() }}
          />
        </div>

        <p className="text-xs text-gray-400" role="status" aria-live="polite">{statusText}</p>
      </div>
    </div>
  )
}

export default memo(VoiceOrb)
