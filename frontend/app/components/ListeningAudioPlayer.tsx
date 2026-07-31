'use client'

import { useRef, useState, useEffect } from 'react'

interface Props {
  /** Ordered extract clips for one part. Played back-to-back, once. */
  srcs: string[]
  /** false (default) = single listen: no seek, no replay-from-start. Pause/resume
   * is always allowed (practice-friendly; the real exam doesn't pause, but students
   * asked to be able to). */
  allowReplay?: boolean
}

function fmt(sec: number) {
  if (!isFinite(sec)) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** Listening player over an ordered list of extract clips. One Play starts the
 * sequence; each clip auto-advances to the next; after the last it locks (no
 * replay unless allowReplay). Pause/resume is allowed, but there's no seek bar —
 * you can't scrub, only pause where you are. Play/resume runs synchronously in
 * the click gesture so the browser doesn't autoplay-block it. */
export default function ListeningAudioPlayer({ srcs, allowReplay = false }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [idx, setIdx] = useState(0)
  const [state, setState] = useState<'idle' | 'playing' | 'paused' | 'ended'>('idle')
  const [cur, setCur] = useState(0)
  const [dur, setDur] = useState(0)
  const [err, setErr] = useState('')

  const total = srcs.length
  const locked = !allowReplay && state === 'ended'

  const attemptPlay = () => {
    const a = audioRef.current
    if (!a) return
    a.play().then(() => setErr('')).catch((e) => {
      // eslint-disable-next-line no-console
      console.error('[ListeningAudioPlayer] play() failed', e)
      setState('paused')
      setErr(e?.name === 'NotAllowedError' ? 'Browser blocked playback — press play again.' : (e?.message || 'Could not play the audio.'))
    })
  }

  // Auto-advance: play the newly-selected clip when idx changes while playing.
  useEffect(() => {
    if (state === 'playing' && audioRef.current) attemptPlay()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx])

  const onToggle = () => {
    if (locked || total === 0) return
    setErr('')
    const a = audioRef.current
    if (!a) return
    if (state === 'playing') { a.pause(); setState('paused'); return }   // pause
    if (state === 'paused') { setState('playing'); attemptPlay(); return } // resume from where it is
    if (state === 'ended' && idx !== 0) { setState('playing'); setIdx(0); return } // replay via effect
    // idle (or single-clip replay): start from the top
    setState('playing')
    a.currentTime = 0
    attemptPlay()
  }

  const onEnded = () => {
    if (idx < total - 1) setIdx((i) => i + 1)
    else setState('ended')
  }

  const pct = dur > 0 ? Math.min(100, (cur / dur) * 100) : 0
  const showPause = state === 'playing'

  if (total === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-4 text-sm text-muted-foreground">
        No audio for this part yet.
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <audio
        ref={audioRef}
        src={srcs[idx]}
        preload="auto"
        onLoadedMetadata={(e) => setDur(e.currentTarget.duration || 0)}
        onTimeUpdate={(e) => setCur(e.currentTarget.currentTime)}
        onEnded={onEnded}
        onError={() => {
          const me = audioRef.current?.error
          // eslint-disable-next-line no-console
          console.error('[ListeningAudioPlayer] audio error', me)
          setState('paused')
          setErr(me ? `Audio failed to load (code ${me.code}).` : 'Audio failed to load.')
        }}
      />
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={onToggle}
          disabled={locked}
          aria-label={showPause ? 'Pause' : locked ? 'Already played' : state === 'paused' ? 'Resume' : 'Play'}
          className={`shrink-0 w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold transition ${
            locked
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-primary text-white hover:bg-primary/90'
          }`}
        >
          {locked ? '✓' : showPause ? '❚❚' : '▶'}
        </button>
        <div className="flex-1 min-w-0">
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-primary transition-all duration-200" style={{ width: `${pct}%` }} />
          </div>
          <div className="flex justify-between text-[11px] text-muted-foreground mt-1 tabular-nums">
            <span>{total > 1 ? `Extract ${idx + 1} of ${total}` : fmt(cur)}</span>
            <span>{fmt(dur)}</span>
          </div>
        </div>
      </div>
      <p className={`text-xs mt-2 ${err ? 'text-red-600' : 'text-muted-foreground'}`}>
        {err
          ? `⚠ ${err}`
          : locked
          ? '🔒 You have listened to this. In the real exam it plays once only.'
          : state === 'playing'
          ? `Listening…${total > 1 ? ' the extracts play one after another.' : ''} Press pause to stop.`
          : state === 'paused'
          ? 'Paused — press play to continue.'
          : `Plays once only${total > 1 ? ` — ${total} extracts, back to back` : ''}. Read the questions first, then press play.`}
      </p>
    </div>
  )
}
