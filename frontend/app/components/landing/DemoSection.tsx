'use client'

import { useEffect, useRef, useState } from 'react'
import { Play, RotateCcw, Check, Lightbulb, Volume2, VolumeX } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  clinicalLabels,
  linguisticLabels,
  scoreColor,
  scoreToGrade,
  type ChatMessage,
} from '@/app/practice/speaking/shared'

// TODO(founder): replace DEMO_TRANSCRIPT + DEMO_SCORES with a transcript and
// report captured from a real session before launch.
//
// What is real here: "Diabetes Insulin Education" is scenario id 6, live in the
// scenarios table, and the turns below stay inside its actual premise — Amit
// Patel, 35, diagnosed a week ago, anxious about self-injection — and cover two
// of its real nurse_card tasks (explain why insulin is needed; address needle
// fear). The criteria, labels and band formula are imported from the product.
//
// What is not real: the turns and scores are a script written by the founder,
// not a recording of a session. That is why every surface says "Demo Session".
// Nothing here may claim a real student said or scored this. If this is ever
// re-anchored to a different scenario, re-check it against that scenario's
// setting and nurse_card first — an earlier draft depicted a UK taxi driver who
// does not exist anywhere in the library.
const DEMO_SCENARIO = 'Diabetes Insulin Education'

const DEMO_TRANSCRIPT: ChatMessage[] = [
  { role: 'patient', content: 'One week ago I was fine. Now they tell me I must inject myself every day. I don’t understand how it came to this.' },
  { role: 'nurse', content: 'That is a great deal to take in one week. Before we open the pen — how have you been feeling since they told you?' },
  { role: 'patient', content: 'Frightened, mostly. My father was on insulin. He lost his foot.' },
  { role: 'nurse', content: 'I am sorry. So when you look at that box, that is what you see. Can I tell you how I see it? What happened to your father came from years of high sugar — not from the insulin. The insulin was what they used to try to stop it. Starting now is what protects you from that.' },
  { role: 'patient', content: 'Nobody explained it that way.' },
  { role: 'nurse', content: 'The pen delivers it into the subcutaneous tissue, so you will need to rotate the sites each time —' },
  { role: 'patient', content: 'The sub— sorry, Sister. I do not follow.' },
  { role: 'nurse', content: 'That is my fault, not yours. I mean the fat just under the skin — your stomach is easiest. And the needle is four millimetres, finer than the one they use for blood tests.' },
]

const DEMO_SCORES: Record<string, { score: number; feedback: string }> = {
  empathy: { score: 5, feedback: "You stayed with the fear about his father instead of moving straight to the pen — 'so when you look at that box, that is what you see'." },
  patient_perspective: { score: 5, feedback: 'You worked out what insulin already meant to him and answered that, rather than only the clinical question.' },
  providing_structure: { score: 4, feedback: 'You checked how he was feeling before teaching. Signposting the steps of the demonstration would lift this further.' },
  information_gathering: { score: 4, feedback: "'How have you been feeling since they told you?' opened up the fear about his father. His diet, monitoring and any previous injection experience went unexplored." },
  information_giving: { score: 3, feedback: "'Subcutaneous tissue' stopped him — he had to interrupt to say he did not follow. The recovery was good; leading with 'the fat just under the skin' would have avoided it." },
  intelligibility: { score: 5, feedback: 'Clear throughout. Every turn was understood on the first attempt.' },
  fluency: { score: 4, feedback: 'Natural pace, with one hesitation mid-demonstration before the self-correction.' },
  appropriateness_of_language: { score: 3, feedback: 'Clinical register slipped in during the demonstration before you self-corrected.' },
  grammar: { score: 4, feedback: 'Accurate structures, with good range in the reassurance about his father.' },
}

const KEY_FEEDBACK = [
  { positive: true, text: 'Clear empathy — you sat with his fear before teaching' },
  { positive: true, text: 'Strong reframe — you separated the insulin from his father’s outcome' },
  { positive: false, text: 'Explain medical terms before using them — “subcutaneous” stopped him' },
]

const average = (keys: string[]) =>
  keys.reduce((sum, key) => sum + DEMO_SCORES[key].score, 0) / keys.length

// Mirrors backend/app/services/ai_scoring.py: clinical is criteria 1-5,
// linguistic is 6-9, overall_band = clinical × 0.6 + linguistic × 0.4.
const clinicalAverage = average(Object.keys(clinicalLabels))
const linguisticAverage = average(Object.keys(linguisticLabels))
const overallBand = clinicalAverage * 0.6 + linguisticAverage * 0.4
const oetGrade = scoreToGrade(overallBand)

// Pre-generated voice clips, one per turn (public/demo-audio/turn-N.mp3),
// synthesized from DEMO_TRANSCRIPT via the product's Google WaveNet TTS with
// distinct patient (male) and nurse (female) voices. Regenerate with
// frontend/scripts/gen_demo_audio.py if the transcript changes.
const AUDIO_DIR = '/demo-audio'

// Fallback pacing when a clip can't play (offline / autoplay blocked): rough
// read time so the transcript still advances one turn at a time.
const estimateMs = (text: string) =>
  Math.max(1500, text.trim().split(/\s+/).length * 380 + 700)

type Phase = 'idle' | 'playing' | 'scored' | 'feedback'

export default function DemoSection() {
  const [phase, setPhase] = useState<Phase>('idle')
  const [revealed, setRevealed] = useState(0)
  const [muted, setMuted] = useState(false)
  // Bumped on every play() so Replay restarts from turn 0 even if the demo is
  // already on turn 0 (state alone wouldn't change, so the effect wouldn't re-run).
  const [runId, setRunId] = useState(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  // Read live inside the play effect without restarting playback when it flips.
  const mutedRef = useRef(muted)
  mutedRef.current = muted

  // Play the demo turn by turn: reveal a line, voice it with its clip, and move
  // to the next turn when the clip ends -- so text and speech stay in sync. The
  // currently-playing turn is `revealed - 1`.
  useEffect(() => {
    if (phase !== 'playing' || revealed === 0) return
    const i = revealed - 1

    let advanced = false
    const advance = () => {
      if (advanced) return
      advanced = true
      if (i + 1 < DEMO_TRANSCRIPT.length) setRevealed(i + 2)
      else setPhase('scored')
    }

    const audio = new Audio(`${AUDIO_DIR}/turn-${i}.mp3`)
    audio.muted = mutedRef.current
    audioRef.current = audio

    let fallback: ReturnType<typeof setTimeout> | undefined
    const failFallback = () => {
      if (fallback) return
      fallback = setTimeout(advance, estimateMs(DEMO_TRANSCRIPT[i].content))
    }

    audio.onended = advance
    audio.onerror = failFallback
    audio.play().catch(failFallback)

    return () => {
      audio.onended = null
      audio.onerror = null
      audio.pause()
      if (fallback) clearTimeout(fallback)
      if (audioRef.current === audio) audioRef.current = null
    }
  }, [phase, revealed, runId])

  // Mute/unmute the in-flight clip without restarting it, so toggling mid-line
  // keeps the pacing intact.
  useEffect(() => {
    if (audioRef.current) audioRef.current.muted = muted
  }, [muted])

  useEffect(() => {
    if (phase !== 'scored') return
    const toFeedback = setTimeout(() => setPhase('feedback'), 900)
    return () => clearTimeout(toFeedback)
  }, [phase])

  const play = () => {
    audioRef.current?.pause()
    setRunId((n) => n + 1)
    setRevealed(1)
    setPhase('playing')
  }

  const toggleMuted = () => setMuted((m) => !m)

  const started = phase !== 'idle'
  const showScores = phase === 'scored' || phase === 'feedback'

  const renderCriterion = (key: string, label: string) => {
    const { score, feedback } = DEMO_SCORES[key]
    return (
      <div key={key} className="rounded-xl bg-white p-4 shadow-sm">
        <div className="flex items-start justify-between gap-2 mb-2">
          <p className="text-sm font-semibold text-[#0F2356] leading-snug">{label}</p>
          <span className={`text-sm font-bold shrink-0 ${scoreColor(score)}`}>{score}/6</span>
        </div>
        <p className="text-xs text-gray-600 leading-relaxed">{feedback}</p>
      </div>
    )
  }

  return (
    <section id="demo" className="bg-[#F8FAFC] py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-10">
          <h2 className="font-display text-3xl md:text-4xl font-semibold text-[#0F2356] mb-3 text-balance">
            See What a Practice Session Looks Like
          </h2>
          <p className="text-gray-500 text-lg max-w-2xl mx-auto text-balance">
            Practice a realistic OET Speaking role-play and receive detailed AI feedback immediately after your session.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-6">
            <button
              type="button"
              onClick={play}
              aria-describedby="demo-disclaimer"
              className="inline-flex items-center justify-center gap-2 bg-[#047857] text-white font-semibold px-6 py-3 rounded-lg hover:bg-[#036546] transition-colors"
            >
              {phase === 'idle' ? (
                <>
                  <Play className="w-4 h-4 fill-current" aria-hidden="true" />
                  Play Demo
                </>
              ) : (
                <>
                  <RotateCcw className="w-4 h-4" aria-hidden="true" />
                  Replay Demo
                </>
              )}
            </button>
            {started && (
              <button
                type="button"
                onClick={toggleMuted}
                aria-pressed={muted}
                aria-label={muted ? 'Unmute demo voice' : 'Mute demo voice'}
                className="inline-flex items-center justify-center w-11 h-11 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors"
              >
                {muted ? <VolumeX className="w-4 h-4" aria-hidden="true" /> : <Volume2 className="w-4 h-4" aria-hidden="true" />}
              </button>
            )}
            <p id="demo-disclaimer" className="text-xs text-gray-500">
              A scripted demo session — not a recording of a real student.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          {/* Left — Transcript. Sticks on desktop so the turns stay visible
              beside the per-criterion feedback that quotes them. */}
          <div className="rounded-2xl bg-white shadow-premium border border-gray-100 p-6 flex flex-col lg:sticky lg:top-24">
            <div className="flex items-center justify-between gap-3 mb-1">
              <h3 className="text-lg font-bold text-[#0F2356]">Transcript</h3>
              <span className="bg-amber-100 text-amber-800 text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full border border-amber-200">
                Demo Session
              </span>
            </div>
            <p className="text-xs text-gray-400 mb-5">{DEMO_SCENARIO}</p>

            <div className="flex flex-col gap-4 min-h-[20rem]" aria-live="polite" aria-atomic="false">
              {!started && (
                <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center py-12">
                  <p className="font-semibold text-gray-700">Ready to begin</p>
                  <p className="text-sm text-gray-400 max-w-xs">
                    Press Play Demo to watch a role-play unfold turn by turn
                  </p>
                </div>
              )}

              {DEMO_TRANSCRIPT.slice(0, revealed).map((msg, i) => (
                <div
                  key={i}
                  className={`flex gap-3 motion-safe:animate-[message-in_0.35s_ease-out_both] ${
                    msg.role === 'nurse' ? 'flex-row-reverse' : 'flex-row'
                  }`}
                >
                  <Avatar className="size-8 shrink-0">
                    <AvatarFallback
                      className={`text-xs font-bold text-white ${
                        msg.role === 'nurse' ? 'bg-[#0F2356]' : 'bg-gray-400'
                      }`}
                    >
                      {msg.role === 'nurse' ? 'N' : 'P'}
                    </AvatarFallback>
                  </Avatar>
                  <div
                    className={`flex flex-col gap-1 max-w-[75%] ${
                      msg.role === 'nurse' ? 'items-end' : 'items-start'
                    }`}
                  >
                    <span className="text-xs text-gray-400">
                      {msg.role === 'nurse' ? 'You (Nurse)' : 'Patient'}
                    </span>
                    <div
                      className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                        msg.role === 'nurse' ? 'bg-[#0F2356] text-white' : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                </div>
              ))}

              {phase === 'playing' && revealed < DEMO_TRANSCRIPT.length && (
                <div className="flex gap-3" aria-hidden="true">
                  <Avatar className="size-8 shrink-0">
                    <AvatarFallback className="text-xs font-bold text-white bg-gray-300">…</AvatarFallback>
                  </Avatar>
                  <div className="rounded-2xl bg-gray-100 px-4 py-3 flex items-center gap-1">
                    {[0, 150, 300].map((delay) => (
                      <span
                        key={delay}
                        className="w-1.5 h-1.5 rounded-full bg-gray-400 motion-safe:animate-[orb-pulse_1s_ease-in-out_infinite]"
                        style={{ animationDelay: `${delay}ms` }}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right — AI feedback */}
          <div className="rounded-2xl bg-white shadow-premium border border-gray-100 p-6">
            <div className="flex items-center justify-between gap-3 mb-5">
              <h3 className="text-lg font-bold text-[#0F2356]">Your AI Feedback</h3>
              <span className="bg-amber-100 text-amber-800 text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full border border-amber-200">
                Demo Session
              </span>
            </div>

            {!showScores ? (
              <div className="min-h-[20rem] flex flex-col items-center justify-center gap-2 text-center rounded-xl border border-dashed border-gray-200 bg-[#F8FAFC] py-12 px-6">
                <p className="font-semibold text-gray-700">Your report appears here</p>
                <p className="text-sm text-gray-400 max-w-xs">
                  All 9 criteria are scored as soon as the role-play ends
                </p>
              </div>
            ) : (
              <div className="motion-safe:animate-[message-in_0.4s_ease-out_both]">
                <div className="rounded-2xl bg-emerald-50 border border-emerald-100 p-6 mb-6">
                  <div className="grid grid-cols-3 divide-x divide-emerald-200">
                    <div className="flex flex-col items-center gap-1 pr-4">
                      <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Clinical</p>
                      <p className="text-2xl font-bold text-[#0F2356]">
                        {clinicalAverage.toFixed(1)}
                        <span className="text-base font-normal text-gray-400">/6</span>
                      </p>
                    </div>
                    <div className="flex flex-col items-center gap-1 px-4">
                      <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">OET Band</p>
                      <div className="relative flex items-center justify-center">
                        <span
                          aria-hidden="true"
                          className="motion-safe:absolute motion-safe:inset-0 motion-safe:rounded-full motion-safe:bg-emerald-300/50 motion-safe:animate-[band-ring_1s_ease-out_1]"
                        />
                        <p className="font-display relative text-4xl font-bold text-[#0F2356] motion-safe:animate-[band-reveal_0.5s_cubic-bezier(0.16,1,0.3,1)_both]">
                          {oetGrade}
                        </p>
                      </div>
                    </div>
                    <div className="flex flex-col items-center gap-1 pl-4">
                      <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Linguistic</p>
                      <p className="text-2xl font-bold text-[#0F2356]">
                        {linguisticAverage.toFixed(1)}
                        <span className="text-base font-normal text-gray-400">/6</span>
                      </p>
                    </div>
                  </div>
                </div>

                <div className="mb-6">
                  <h4 className="text-sm font-bold text-[#0F2356] uppercase tracking-wide mb-3">
                    Clinical Communication
                  </h4>
                  <div className="grid grid-cols-1 gap-3">
                    {Object.entries(clinicalLabels).map(([key, label]) => renderCriterion(key, label))}
                  </div>
                </div>

                <div className="mb-6">
                  <h4 className="text-sm font-bold text-[#0F2356] uppercase tracking-wide mb-3">
                    Linguistic Performance
                  </h4>
                  <div className="grid grid-cols-1 gap-3">
                    {Object.entries(linguisticLabels).map(([key, label]) => renderCriterion(key, label))}
                  </div>
                </div>

                {phase === 'feedback' && (
                  <div className="motion-safe:animate-[panel-slide-in_0.45s_ease-out_both]">
                    <div className="rounded-2xl bg-[#0F2356] p-5 text-white">
                      <h4 className="text-sm font-bold uppercase tracking-wide mb-3">Key Feedback</h4>
                      <ul className="flex flex-col gap-2.5 mb-5">
                        {KEY_FEEDBACK.map(({ positive, text }) => (
                          <li key={text} className="flex items-start gap-2.5 text-sm text-white/90 leading-relaxed">
                            {positive ? (
                              <Check className="w-4 h-4 text-[#10B981] shrink-0 mt-0.5" aria-hidden="true" />
                            ) : (
                              <Lightbulb className="w-4 h-4 text-amber-300 shrink-0 mt-0.5" aria-hidden="true" />
                            )}
                            <span>{text}</span>
                          </li>
                        ))}
                      </ul>
                      <a
                        href="/auth/register"
                        className="inline-flex w-full items-center justify-center bg-[#047857] text-white font-semibold px-6 py-3 rounded-lg hover:bg-[#036546] transition-colors"
                      >
                        Start Free — Get Your Own Feedback
                      </a>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Rubric strip */}
        <div className="mt-10 border-y border-gray-200 py-5 text-center">
          <p className="text-sm font-medium text-[#0F2356]">
            Scored using all 9 public OET Speaking assessment criteria.
          </p>
          <p className="text-xs text-gray-500 mt-1">
            SpeakOET is an independent study tool and is not affiliated with OET.
          </p>
        </div>
      </div>
    </section>
  )
}
