'use client'

import { useEffect, useState } from 'react'
import { Play, RotateCcw, Check, Lightbulb } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  clinicalLabels,
  linguisticLabels,
  scoreColor,
  scoreToGrade,
  type ChatMessage,
} from '@/app/practice/speaking/shared'

// TODO(founder): replace DEMO_TRANSCRIPT + DEMO_SCORES with a transcript and
// report captured from a real session before launch. "Chest Pain in Emergency
// Department" is scenario id 4 and is live in the scenarios table, but the
// turns and scores below are written by hand, not recorded — which is why every
// surface here is labelled "Demo Session". Nothing on this page may claim a
// real student said or scored this.
const DEMO_SCENARIO = 'Chest Pain in Emergency Department'

const DEMO_TRANSCRIPT: ChatMessage[] = [
  { role: 'patient', content: "Sister, the pain started yesterday evening. It's like something heavy sitting on my chest." },
  { role: 'nurse', content: 'That sounds frightening. Can you show me exactly where you feel it?' },
  { role: 'patient', content: 'Here, in the middle. And it goes into my left arm also.' },
  { role: 'nurse', content: 'Thank you. Your ECG shows some changes we call an arrhythmia.' },
  { role: 'patient', content: 'A what? Is my heart going to stop?' },
  { role: 'nurse', content: "I'm sorry — let me explain that more simply. Your heart is beating in an uneven rhythm. It is not stopping, and we are watching it closely." },
]

const DEMO_SCORES: Record<string, { score: number; feedback: string }> = {
  empathy: { score: 5, feedback: "You named the fear directly — 'that sounds frightening' — instead of moving straight to the assessment." },
  patient_perspective: { score: 4, feedback: 'You picked up the panic behind “is my heart going to stop?” and answered the worry, not just the question.' },
  providing_structure: { score: 4, feedback: 'The assessment followed a clear order. Signposting the next step would lift this further.' },
  information_gathering: { score: 5, feedback: 'Asking the patient to locate the pain drew out the radiation to the left arm.' },
  information_giving: { score: 3, feedback: "You used 'arrhythmia' before explaining it. The patient had to interrupt to ask what it meant." },
  intelligibility: { score: 5, feedback: 'Clear throughout. Every turn was understood on the first attempt.' },
  fluency: { score: 4, feedback: 'Natural pace with only brief hesitation before the ECG explanation.' },
  appropriateness_of_language: { score: 3, feedback: 'Clinical register slipped in at the ECG explanation before you self-corrected.' },
  grammar: { score: 4, feedback: 'Accurate structures. Range was slightly narrow when reassuring the patient.' },
}

const KEY_FEEDBACK = [
  { positive: true, text: 'Clear empathy — you named the fear before assessing' },
  { positive: true, text: 'Good questioning — locating the pain found the radiation' },
  { positive: false, text: 'Explain medical terms more simply before using them' },
]

const average = (keys: string[]) =>
  keys.reduce((sum, key) => sum + DEMO_SCORES[key].score, 0) / keys.length

// Mirrors backend/app/services/ai_scoring.py: clinical is criteria 1-5,
// linguistic is 6-9, overall_band = clinical × 0.6 + linguistic × 0.4.
const clinicalAverage = average(Object.keys(clinicalLabels))
const linguisticAverage = average(Object.keys(linguisticLabels))
const overallBand = clinicalAverage * 0.6 + linguisticAverage * 0.4
const oetGrade = scoreToGrade(overallBand)

const MESSAGE_MS = 1600

type Phase = 'idle' | 'playing' | 'scored' | 'feedback'

export default function DemoSection() {
  const [phase, setPhase] = useState<Phase>('idle')
  const [revealed, setRevealed] = useState(0)

  // Advance the transcript one turn at a time, then the score card, then the
  // feedback panel. Anyone who asked the OS for reduced motion gets the whole
  // report at once instead of a timed reveal.
  useEffect(() => {
    if (phase !== 'playing') return

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setRevealed(DEMO_TRANSCRIPT.length)
      setPhase('feedback')
      return
    }

    if (revealed < DEMO_TRANSCRIPT.length) {
      const timer = setTimeout(() => setRevealed((n) => n + 1), MESSAGE_MS)
      return () => clearTimeout(timer)
    }

    const toScored = setTimeout(() => setPhase('scored'), 500)
    return () => clearTimeout(toScored)
  }, [phase, revealed])

  useEffect(() => {
    if (phase !== 'scored') return
    const toFeedback = setTimeout(() => setPhase('feedback'), 900)
    return () => clearTimeout(toFeedback)
  }, [phase])

  const play = () => {
    setRevealed(0)
    setPhase('playing')
  }

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
          <h2 className="text-3xl md:text-4xl font-bold text-[#0F2356] mb-3 text-balance">
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
            <p id="demo-disclaimer" className="text-xs text-gray-500">
              A scripted demo session — not a recording of a real student.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          {/* Left — Transcript. Sticks on desktop so the turns stay visible
              beside the per-criterion feedback that quotes them. */}
          <div className="rounded-2xl bg-white shadow-sm border border-gray-100 p-6 flex flex-col lg:sticky lg:top-24">
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
          <div className="rounded-2xl bg-white shadow-sm border border-gray-100 p-6">
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
                  All 9 criteria are scored within 30 seconds of the role-play ending
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
                        <p className="relative text-4xl font-black text-[#0F2356] motion-safe:animate-[band-reveal_0.5s_cubic-bezier(0.34,1.56,0.64,1)_both]">
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
