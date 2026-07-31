'use client'

import { memo, useEffect, useRef, useState, type ReactNode } from 'react'

/**
 * The five things the orb can be doing. Derived from the boolean props below
 * rather than passed in, so callers keep the same API they always had -- but
 * everything visual (colour, glow, which layers are visible) keys off this
 * single value instead of re-deriving from five booleans in six places.
 */
type OrbState = 'idle' | 'connecting' | 'listening' | 'speaking' | 'analysing'

interface OrbTheme {
  /** Mid-tone: the orb's dominant colour. */
  base: string
  /** Highlight, top-left of the sphere gradient. */
  light: string
  /** Terminator, bottom-right of the sphere gradient. */
  dark: string
  /** Blurred wash behind the orb. Needs alpha. */
  glow: string
}

// Emerald/blue/amber carry the three states the student actually needs to
// read at a glance; navy is SpeakOET's own resting colour.
const ORB_THEME: Record<OrbState, OrbTheme> = {
  idle:       { base: '#1E3A6E', light: '#3F63AC', dark: '#0B1A42', glow: 'rgba(15, 35, 86, 0.40)' },
  connecting: { base: '#6366F1', light: '#A5B4FC', dark: '#4338CA', glow: 'rgba(99, 102, 241, 0.45)' },
  listening:  { base: '#10B981', light: '#6EE7B7', dark: '#047857', glow: 'rgba(16, 185, 129, 0.45)' },
  speaking:   { base: '#3B82F6', light: '#93C5FD', dark: '#1D4ED8', glow: 'rgba(59, 130, 246, 0.45)' },
  analysing:  { base: '#F59E0B', light: '#FCD34D', dark: '#B45309', glow: 'rgba(245, 158, 11, 0.45)' },
}

// Every appear/disappear uses the same ease-out curve and duration so layers
// crossfading at the same moment (halo out, waveform in) stay in step.
const TRANSITION = '300ms cubic-bezier(0.22, 1, 0.36, 1)'

const BAR_COUNT = 5
// Frames between the level each bar samples. The bars read a shared history
// buffer at staggered offsets, so a loud syllable visibly travels across them
// instead of every bar jumping together.
const BAR_STRIDE = 4

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(query.matches)
    const onChange = () => setReduced(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return reduced
}

/**
 * Owns the microphone AnalyserNode used to make the orb react to the
 * student's own voice while listening. Returns a getter rather than state:
 * this is read once per animation frame, and putting it in React state would
 * mean ~60 re-renders a second of the whole session screen.
 *
 * Only runs while `active` -- the stream and context are torn down as soon as
 * the orb stops listening, so the browser's mic indicator matches reality.
 */
function useMicLevel(active: boolean): () => number {
  const analyserRef = useRef<AnalyserNode | null>(null)
  // Explicit ArrayBuffer: a bare `Uint8Array` ref widens to ArrayBufferLike,
  // which getByteTimeDomainData won't accept.
  const dataRef = useRef<Uint8Array<ArrayBuffer> | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    if (!active) return
    let cancelled = false

    const setup = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        const ctx = new AudioContext()
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        // Browser-side smoothing on top of our own envelope follower below --
        // raw frame-to-frame RMS on speech is far too twitchy to drive a scale.
        analyser.smoothingTimeConstant = 0.75
        ctx.createMediaStreamSource(stream).connect(analyser)

        streamRef.current = stream
        contextRef.current = ctx
        analyserRef.current = analyser
        dataRef.current = new Uint8Array(analyser.frequencyBinCount)
      } catch {
        // Mic denied or unavailable -- the orb falls back to its idle motion.
      }
    }
    setup()

    return () => {
      cancelled = true
      analyserRef.current = null
      dataRef.current = null
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      contextRef.current?.close().catch(() => {})
      contextRef.current = null
    }
  }, [active])

  return () => readRms(analyserRef.current, dataRef.current)
}

/** RMS of an analyser's time-domain data, scaled so normal speech lands
 *  around 0.4-0.8 rather than the 0.1-0.2 raw RMS actually produces. */
function readRms(analyser: AnalyserNode | null, data: Uint8Array<ArrayBuffer> | null): number {
  if (!analyser || !data) return 0
  analyser.getByteTimeDomainData(data)
  let sum = 0
  for (let i = 0; i < data.length; i++) {
    const v = data[i] / 128 - 1
    sum += v * v
  }
  return Math.min(1, Math.sqrt(sum / data.length) * 2.4)
}

interface VoiceOrbProps {
  isListening: boolean
  isConnecting?: boolean
  isProcessing: boolean
  isSpeaking?: boolean
  isEnding: boolean
  canEndSession?: boolean
  statusOverride?: string
  /**
   * 'bar' (default) is the compact strip that sits under a visible chat log.
   * 'hero' is the focus-mode layout — a large centred orb that IS the screen,
   * so the student isn't reading scrolling text while trying to hold a
   * natural conversation. Anything extra (timer, captions) is passed as
   * children and renders between the status line and End Session.
   */
  variant?: 'bar' | 'hero'
  /**
   * Amplitude (0-1) of the patient's voice as it plays, sampled once per
   * animation frame to drive the waveform bars. Only the realtime pipeline
   * can supply this (it owns the AudioContext the audio is played through);
   * the legacy TTS path plays through an HTMLAudioElement with no analyser,
   * so when this is absent the bars fall back to a smooth synthetic motion.
   */
  getOutputLevel?: () => number
  children?: ReactNode
  onToggle: () => void
  onEndSession: () => void
}

function VoiceOrb({
  isListening,
  isConnecting = false,
  isProcessing,
  isSpeaking = false,
  isEnding,
  canEndSession = true,
  statusOverride,
  variant = 'bar',
  getOutputLevel,
  children,
  onToggle,
  onEndSession,
}: VoiceOrbProps) {
  const isHero = variant === 'hero'
  const reducedMotion = usePrefersReducedMotion()

  // isEnding wins: once scoring starts the student can't act on the orb, so
  // it should read as "analysing" no matter what the other flags say.
  const state: OrbState = isEnding
    ? 'analysing'
    : isConnecting
    ? 'connecting'
    : isProcessing
    ? 'analysing'
    : isSpeaking
    ? 'speaking'
    : isListening
    ? 'listening'
    : 'idle'

  const theme = ORB_THEME[state]
  const orbDisabled = isConnecting || isProcessing || isSpeaking || isEnding

  let statusText = 'Tap to speak'
  if (isEnding) statusText = statusOverride || 'Analysing your responses...'
  else if (isConnecting) statusText = 'Connecting...'
  else if (isProcessing) statusText = 'Thinking...'
  else if (isSpeaking) statusText = 'Patient speaking...'
  else if (isListening) statusText = 'Listening...'

  const ringSize = isHero ? 176 : 96
  const orbSize = isHero ? 120 : 64
  const barHeight = isHero ? 40 : 24
  const barWidth = isHero ? 5 : 3.5

  const getMicLevel = useMicLevel(isListening && !reducedMotion)

  // Written to directly from the animation loop below -- never through
  // setState, so the loop costs no React work at all.
  const orbRef = useRef<HTMLDivElement>(null)
  const glowRef = useRef<HTMLDivElement>(null)
  const barRefs = useRef<Array<HTMLSpanElement | null>>([])
  const historyRef = useRef<number[]>(new Array(BAR_COUNT * BAR_STRIDE).fill(0))

  const reactive = (state === 'listening' || state === 'speaking') && !reducedMotion

  useEffect(() => {
    if (!reactive) {
      // Settle everything back to rest so the next state change animates from
      // a known position rather than wherever the last frame left it.
      if (orbRef.current) orbRef.current.style.transform = 'scale(1)'
      if (glowRef.current) glowRef.current.style.opacity = '0.55'
      historyRef.current.fill(0)
      return
    }

    let frame = 0
    let level = 0

    const tick = () => {
      const raw = state === 'listening'
        ? getMicLevel()
        : getOutputLevel?.() ?? syntheticLevel()

      // Envelope follower: rise quickly so the orb catches the start of a
      // word, fall slowly so it doesn't strobe between syllables.
      level += (raw - level) * (raw > level ? 0.35 : 0.10)

      const history = historyRef.current
      history.push(level)
      history.shift()

      if (orbRef.current) {
        orbRef.current.style.transform = `scale(${1 + level * 0.09})`
      }
      if (glowRef.current) {
        glowRef.current.style.opacity = String(0.5 + level * 0.45)
      }
      if (state === 'speaking') {
        for (let i = 0; i < BAR_COUNT; i++) {
          const bar = barRefs.current[i]
          if (!bar) continue
          const sampled = history[history.length - 1 - i * BAR_STRIDE] ?? 0
          bar.style.transform = `scaleY(${0.22 + sampled * 0.78})`
        }
      }

      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
    // getMicLevel/getOutputLevel are read through refs inside the loop and are
    // stable for the life of a state; re-running on identity alone would
    // restart the envelope mid-sentence.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reactive, state])

  const orbNode = (
    <div className="relative flex items-center justify-center" style={{ width: ringSize, height: ringSize }}>
      {/* Blurred colour wash. Sits behind everything and is the main thing
          that makes the orb feel lit rather than drawn. */}
      <div
        ref={glowRef}
        aria-hidden="true"
        className="orb-anim pointer-events-none absolute rounded-full"
        style={{
          width: orbSize * 1.5,
          height: orbSize * 1.5,
          background: theme.glow,
          filter: `blur(${isHero ? 34 : 20}px)`,
          opacity: 0.55,
          animation: 'orb-glow-drift 6s ease-in-out infinite',
          transition: `background ${TRANSITION}`,
        }}
      />

      {/* Listening halo. Both rings stay mounted and pause when inactive, so
          switching states crossfades instead of popping. */}
      {[0, 1].map((i) => (
        <span
          key={i}
          aria-hidden="true"
          className="orb-anim pointer-events-none absolute rounded-full"
          style={{
            width: orbSize,
            height: orbSize,
            border: `1.5px solid ${theme.base}`,
            animation: 'orb-ripple-soft 2.6s cubic-bezier(0.22, 1, 0.36, 1) infinite',
            animationDelay: `${i * 1.3}s`,
            animationPlayState: state === 'listening' ? 'running' : 'paused',
            opacity: state === 'listening' ? 1 : 0,
            transition: `opacity ${TRANSITION}`,
          }}
        />
      ))}

      {/* Analysing rings: a segmented outer ring and a slower inner one
          turning the other way. Reads as work in progress, not a spinner. */}
      <svg
        aria-hidden="true"
        className="pointer-events-none absolute"
        width={orbSize * 1.34}
        height={orbSize * 1.34}
        viewBox="0 0 100 100"
        style={{
          opacity: state === 'analysing' ? 1 : 0,
          transform: state === 'analysing' ? 'scale(1)' : 'scale(0.88)',
          transition: `opacity ${TRANSITION}, transform ${TRANSITION}`,
        }}
      >
        <g
          className="orb-anim"
          style={{
            transformOrigin: '50% 50%',
            animation: 'orb-ring-spin 7s linear infinite',
            animationPlayState: state === 'analysing' ? 'running' : 'paused',
          }}
        >
          <circle
            cx="50" cy="50" r="46"
            fill="none"
            stroke={theme.base}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeDasharray="26 14"
            opacity="0.75"
          />
        </g>
        <g
          className="orb-anim"
          style={{
            transformOrigin: '50% 50%',
            animation: 'orb-ring-spin-rev 11s linear infinite',
            animationPlayState: state === 'analysing' ? 'running' : 'paused',
          }}
        >
          <circle
            cx="50" cy="50" r="38"
            fill="none"
            stroke={theme.light}
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeDasharray="8 22"
            opacity="0.6"
          />
        </g>
      </svg>

      {/* Two nested wrappers on purpose: the outer one owns the CSS breathing
          keyframe, the inner one owns the audio-reactive scale. Both animate
          `transform`, so they can't share an element. */}
      <div
        className="orb-anim relative z-10"
        style={{
          animation: `orb-breathe-soft ${state === 'listening' ? '4.5s' : '6s'} ease-in-out infinite`,
          animationPlayState: state === 'speaking' || state === 'analysing' ? 'paused' : 'running',
        }}
      >
        <div ref={orbRef} style={{ transition: `transform ${TRANSITION}` }}>
          <button
            type="button"
            aria-label="Microphone"
            aria-pressed={isListening}
            aria-disabled={orbDisabled}
            title={orbDisabled ? "You can't respond while this is in progress" : undefined}
            className="relative flex items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
            style={{
              width: orbSize,
              height: orbSize,
              // Off-centre highlight is what turns a flat disc into a sphere.
              background: `radial-gradient(circle at 32% 28%, ${theme.light} 0%, ${theme.base} 48%, ${theme.dark} 100%)`,
              boxShadow: `0 ${isHero ? 18 : 10}px ${isHero ? 40 : 22}px -12px ${theme.glow}, inset 0 -8px 18px rgba(0, 0, 0, 0.22), inset 0 6px 14px rgba(255, 255, 255, 0.20)`,
              opacity: orbDisabled ? 0.92 : 1,
              cursor: orbDisabled ? 'not-allowed' : 'pointer',
              transition: `background ${TRANSITION}, box-shadow ${TRANSITION}, opacity ${TRANSITION}`,
            }}
            onClick={() => { if (!orbDisabled) onToggle() }}
          >
            {/* Waveform. Always mounted so it can fade in/out with the state
                rather than appearing from nothing mid-sentence. */}
            <span
              aria-hidden="true"
              className="pointer-events-none absolute flex items-center"
              style={{
                height: barHeight,
                gap: barWidth * 0.9,
                opacity: state === 'speaking' ? 1 : 0,
                transform: state === 'speaking' ? 'scale(1)' : 'scale(0.7)',
                transition: `opacity ${TRANSITION}, transform ${TRANSITION}`,
              }}
            >
              {Array.from({ length: BAR_COUNT }, (_, i) => (
                <span
                  key={i}
                  ref={(el) => { barRefs.current[i] = el }}
                  className="rounded-full bg-white/90"
                  style={{
                    width: barWidth,
                    height: barHeight,
                    // Resting shape when there's no animation frame running
                    // (reduced motion) -- a static waveform, not a flat block.
                    transform: `scaleY(${0.35 + (i === 2 ? 0.4 : i === 1 || i === 3 ? 0.22 : 0)})`,
                  }}
                />
              ))}
            </span>
          </button>
        </div>
      </div>
    </div>
  )

  const statusNode = (
    <p
      className={isHero
        ? 'flex items-center gap-2 text-sm font-semibold text-gray-600'
        : 'flex items-center gap-1.5 text-xs text-gray-400'}
      role="status"
      aria-live="polite"
    >
      <span
        className="size-2 shrink-0 rounded-full"
        style={{ backgroundColor: theme.base, transition: `background-color ${TRANSITION}` }}
        aria-hidden="true"
      />
      {/* Keyed so each new status fades in rather than swapping in place. */}
      <span key={statusText} className="orb-status-in">{statusText}</span>
    </p>
  )

  const endButtonLabel = isEnding ? 'Ending...' : 'End Session'
  const endButtonTitle = !canEndSession
    ? 'Speak or type at least one response before ending the session'
    : undefined

  if (isHero) {
    return (
      <div className="flex flex-col items-center gap-5">
        {orbNode}
        {statusNode}
        {children}
        <button
          onClick={onEndSession}
          disabled={isEnding || !canEndSession}
          title={endButtonTitle}
          className="rounded-xl border border-gray-300 px-6 py-2.5 text-sm font-semibold text-gray-600 transition hover:border-red-400 hover:bg-red-50 hover:text-red-500 disabled:opacity-50"
        >
          {endButtonLabel}
        </button>
      </div>
    )
  }

  return (
    <div className="flex-shrink-0 bg-white border-t border-gray-100 p-4 relative" style={{ height: 140 }}>
      <button
        onClick={onEndSession}
        disabled={isEnding || !canEndSession}
        title={endButtonTitle}
        className="absolute top-4 right-4 rounded-xl border border-gray-300 text-gray-600 hover:border-red-400 hover:text-red-500 hover:bg-red-50 px-4 py-2 text-sm font-semibold transition disabled:opacity-50"
      >
        {endButtonLabel}
      </button>

      <div className="flex flex-col items-center justify-center h-full gap-2">
        {orbNode}
        {statusNode}
      </div>
    </div>
  )
}

/** Smooth, organic-looking motion for when no real amplitude is available
 *  (legacy TTS playback). Two detuned sines so it never visibly loops. */
function syntheticLevel(): number {
  const t = performance.now() / 1000
  return 0.34 + 0.2 * Math.sin(t * 3.1) + 0.12 * Math.sin(t * 1.73)
}

export default memo(VoiceOrb)
