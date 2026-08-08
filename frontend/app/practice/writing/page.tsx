'use client'

import { useState, useEffect, useMemo, useRef } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import { QRCodeSVG } from 'qrcode.react'
import { compressImageToBase64 } from '@/lib/imageCompress'
import api, { isUpgradeRequiredError } from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Search, X, Sparkles } from 'lucide-react'
import { DifficultyBadge, normalizeDifficulty } from '@/components/ui/DifficultyBadge'
import { CompletedBadge } from '@/components/ui/CompletedBadge'
import { WeakSpots } from '@/components/practice/WeakSpots'
import { UpgradeRequired } from '@/components/UpgradeRequired'
import { getMockId, finishMockSection } from '@/lib/mock'
import { WRITING_CRITERIA } from '@/components/SessionFeedback'

interface Scenario {
  id: number
  title: string
  setting: string
  difficulty: string
  nurse_card: {
    role?: string
    tasks?: string[]
  }
}

interface CriterionScore {
  score: number | null
  feedback: string
}

interface Feedback {
  scoring_failed?: boolean
  scores: Record<string, CriterionScore>
  overall_score: number | null
  estimated_oet_grade: string | null
  raw_total?: number | null
  top_strengths: string[]
  top_improvements: string[]
  corrected_version: string
}

interface SkillScore {
  tag: string
  label: string
  score: number
}

interface NextBestAction {
  scenario_id: number
  title: string
  reason: string
}

interface Insights {
  strongest_skill: SkillScore
  weakest_skill: SkillScore
  recommendation_reason: string
  actionable_improvement: string
  confidence_message: string
  next_best_action: NextBestAction | null
  based_on: 'history' | 'session'
}

// Shared with the saved-session view (/sessions/[id]) so the rubric can't drift
// between the live result screen and a session reopened later.
const CRITERIA = WRITING_CRITERIA

const WORD_MIN = 120

// Mock timing: the 45-min cap = 5 min reading (textarea locked) + 40 min writing.
// The textarea unlocks once the remaining time drops to the 40-min write window.
const WRITE_WINDOW_SECONDS = 40 * 60

function countWords(text: string) {
  const trimmed = text.trim()
  return trimmed ? trimmed.split(/\s+/).length : 0
}

function fmtClock(sec: number) {
  const m = Math.floor(Math.max(0, sec) / 60)
  const s = Math.max(0, sec) % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function scoreColor(score: number | null, max: number) {
  if (score === null) return 'text-muted-foreground'
  const ratio = score / max
  if (ratio >= 0.66) return 'text-emerald-600'
  if (ratio >= 0.5) return 'text-amber-500'
  return 'text-red-500'
}

type Phase = 'select' | 'write' | 'result'

export default function WritingPracticePage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [phase, setPhase] = useState<Phase>('select')
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [completedScenarioIds, setCompletedScenarioIds] = useState<Set<number>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [filterDifficulty, setFilterDifficulty] = useState<'all' | 'beginner' | 'intermediate' | 'advanced'>('all')
  const [filterStatus, setFilterStatus] = useState<'all' | 'completed' | 'not_tried'>('all')
  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [upgradeRequired, setUpgradeRequired] = useState(false)
  const [writingText, setWritingText] = useState('')
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [insights, setInsights] = useState<Insights | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [inputMode, setInputMode] = useState<'type' | 'upload'>('type')
  const [photos, setPhotos] = useState<{ file: File; url: string; ocrd?: boolean }[]>([])
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrDone, setOcrDone] = useState(false)
  const [phoneUrl, setPhoneUrl] = useState<string | null>(null)
  const phonePollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Full Mock Test mode: fixed scenario, strict 5-min-read + 40-min-write timer,
  // type-only, and the score is hidden — the section is reported to the mock.
  const [mockId, setMockId] = useState<string | null>(null)
  const [deadlineMs, setDeadlineMs] = useState<number | null>(null)
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null)
  const autoSubmitted = useRef(false)
  const writeLocked = !!mockId && secondsLeft !== null && secondsLeft > WRITE_WINDOW_SECONDS

  const stopPhonePoll = () => {
    if (phonePollRef.current) {
      clearInterval(phonePollRef.current)
      phonePollRef.current = null
    }
  }

  // Clean up the polling interval if the student leaves the page mid-handoff.
  useEffect(() => stopPhonePoll, [])

  const clearPhotos = () => {
    photos.forEach((p) => URL.revokeObjectURL(p.url))
    setPhotos([])
    setWritingText('')
    setOcrDone(false)
  }

  const resetInput = () => {
    setWritingText('')
    setInputMode('type')
    clearPhotos()
    stopPhonePoll()
    setPhoneUrl(null)
  }

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }

    if (status === 'authenticated') {
      const mid = getMockId()
      setMockId(mid)
      if (mid) { loadMockWriting(mid); return }
      loadScenarios()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  const loadScenarios = async () => {
    try {
      const response = await api.get('/writing/scenarios')
      setScenarios(response.data || [])
    } catch (error) {
      console.error('Failed to fetch scenarios:', error)
      if (isUpgradeRequiredError(error)) setUpgradeRequired(true)
      else toast.error('Failed to load writing scenarios')
    } finally {
      setIsLoading(false)
    }
    api.get('/submissions', { params: { module: 'writing' } })
      .then((res) => setCompletedScenarioIds(new Set((res.data || []).map((sub: { scenario_id: number }) => sub.scenario_id))))
      .catch(() => {})
  }

  const filteredScenarios = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    return scenarios.filter((s) => {
      if (filterDifficulty !== 'all' && normalizeDifficulty(s.difficulty) !== filterDifficulty) return false
      const isCompleted = completedScenarioIds.has(s.id)
      if (filterStatus === 'completed' && !isCompleted) return false
      if (filterStatus === 'not_tried' && isCompleted) return false
      if (query && !s.title.toLowerCase().includes(query) && !s.setting.toLowerCase().includes(query)) return false
      return true
    })
  }, [scenarios, filterDifficulty, filterStatus, searchQuery, completedScenarioIds])

  // Mock: load the one scenario the mock froze in and drop straight into the timed
  // writing sitting — no scenario picker.
  const loadMockWriting = async (mid: string) => {
    try {
      const cur = await api.get('/mock/current')
      if (cur.data?.current_section !== 'writing' || !cur.data?.content_id) {
        router.replace('/practice/mock')
        return
      }
      const sc = await api.get(`/writing/scenarios/${cur.data.content_id}`)
      setSelectedScenario(sc.data)
      if (cur.data.deadline) setDeadlineMs(new Date(cur.data.deadline).getTime())
      setInputMode('type')
      setPhase('write')
    } catch (error) {
      if (!isUpgradeRequiredError(error)) toast.error('Could not load your mock writing task.')
      router.replace('/practice/mock')
    } finally {
      setIsLoading(false)
    }
  }

  // Mock countdown to the server-anchored deadline; auto-submits at 0.
  useEffect(() => {
    if (!deadlineMs) return
    const tick = () => setSecondsLeft(Math.max(0, Math.round((deadlineMs - Date.now()) / 1000)))
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [deadlineMs])

  useEffect(() => {
    if (mockId && phase === 'write' && secondsLeft === 0 && !isSubmitting && !autoSubmitted.current) {
      autoSubmitted.current = true
      handleSubmit(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mockId, phase, secondsLeft, isSubmitting])

  const handleSelectScenario = (scenario: Scenario) => {
    setSelectedScenario(scenario)
    resetInput()
    setFeedback(null)
    setInsights(null)
    setPhase('write')
  }

  const handleBackToScenarios = () => {
    setSelectedScenario(null)
    resetInput()
    setFeedback(null)
    setInsights(null)
    setPhase('select')
  }

  const addPhotos = (files: FileList | null) => {
    if (!files) return
    const picked = Array.from(files).slice(0, 3 - photos.length)
    setPhotos((prev) => [...prev, ...picked.map((file) => ({ file, url: URL.createObjectURL(file) }))])
    setOcrDone(false)
  }

  // Browsers return multi-selected files in filename order, not tap order, so
  // let the student fix page order themselves rather than guessing it.
  const movePhoto = (from: number, dir: -1 | 1) => {
    setPhotos((prev) => {
      const to = from + dir
      if (to < 0 || to >= prev.length) return prev
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })
    setOcrDone(false)
  }

  const handleReadPhotos = async () => {
    if (!photos.length) {
      toast.error('Add a photo of your letter first')
      return
    }
    // Only read pages not already read, and append — so a second page never
    // wipes the first (or the student's manual edits), and we don't re-charge
    // OCR on pages already done.
    // ponytail: append order follows read order, not thumbnail order after a
    // late reorder; the text is editable so that's a rare, user-fixable edge.
    const pending = photos.filter((p) => !p.ocrd)
    if (!pending.length) {
      toast('All photos already read — add another page, or edit below.')
      return
    }
    setOcrLoading(true)
    try {
      const images = await Promise.all(pending.map((p) => compressImageToBase64(p.file)))
      const res = await api.post('/writing/ocr', { images })
      const newText = res.data.text || ''
      setWritingText((prev) => (prev.trim() ? `${prev.trimEnd()}\n\n${newText}` : newText))
      setPhotos((prev) => prev.map((p) => ({ ...p, ocrd: true })))
      setOcrDone(true)
      toast.success('Read your handwriting — check it for mistakes below')
    } catch (error: any) {
      if (!isUpgradeRequiredError(error)) {
        const errData = error.response?.data?.detail
        toast.error(typeof errData === 'string' ? errData : 'Could not read the photos — try clearer, well-lit images.')
      }
    } finally {
      setOcrLoading(false)
    }
  }

  const startPhoneSession = async () => {
    try {
      const res = await api.post('/writing/phone-session', {})
      const token = res.data.token
      // NEXT_PUBLIC_LAN_ORIGIN lets local dev point the QR at the laptop's LAN
      // address (the phone can't reach 'localhost'); in prod it's unset and the
      // QR uses the real domain the laptop is already on.
      const base = process.env.NEXT_PUBLIC_LAN_ORIGIN || window.location.origin
      setPhoneUrl(`${base}/practice/writing/phone-upload/${token}`)

      stopPhonePoll()
      phonePollRef.current = setInterval(async () => {
        try {
          const poll = await api.get(`/writing/phone-session/${token}`)
          if (poll.data.status === 'done') {
            stopPhonePoll()
            // Append, not replace — a second QR handoff (page 2) must not wipe
            // the text from the first.
            const newText = poll.data.text || ''
            setWritingText((prev) => (prev.trim() ? `${prev.trimEnd()}\n\n${newText}` : newText))
            setOcrDone(true)
            setPhoneUrl(null)
            toast.success('Got your letter from your phone — check it for mistakes below')
          } else if (poll.data.status === 'expired') {
            stopPhonePoll()
            setPhoneUrl(null)
            toast.error('The phone link expired — please try again.')
          }
        } catch {
          // transient poll error — keep trying until the student closes it
        }
      }, 3000)
    } catch (error: any) {
      if (!isUpgradeRequiredError(error)) toast.error('Could not start the phone link — please try again.')
    }
  }

  const closePhoneSession = () => {
    stopPhonePoll()
    setPhoneUrl(null)
  }

  const handleSubmit = async (auto = false) => {
    if (!selectedScenario) return
    const hasText = !!writingText.trim()

    // Mock: time up (or finish) with nothing written — record the section and move
    // on rather than trapping the student on an empty letter.
    if (mockId && auto && !hasText) {
      await finishMockSection(mockId, 'writing', { skipped: true })
      router.replace('/practice/mock')
      return
    }
    if (!hasText) {
      toast.error('Please write something before submitting')
      return
    }
    // The exam lets you submit whatever you have; only nudge on length outside a mock.
    if (!mockId && countWords(writingText) < WORD_MIN) {
      toast.error(`Your letter is too short — aim for 180–200 words (at least ${WORD_MIN}).`)
      return
    }

    setIsSubmitting(true)
    try {
      const response = await api.post('/writing/submit', {
        scenario_id: selectedScenario.id,
        content: writingText,
      })

      if (mockId) {
        // Score stays hidden in a mock — report the section, back to the controller.
        // Free-tier mock: backend skipped AI scoring entirely (see /writing/submit's
        // locked branch) -- record that instead of a grade so the report screen
        // shows an upgrade prompt rather than a blank dash.
        if (response.data.locked) {
          await finishMockSection(mockId, 'writing', { locked: true })
        } else {
          const fb = response.data.feedback
          await finishMockSection(mockId, 'writing', {
            grade: fb?.estimated_oet_grade ?? null,
            overall_score: fb?.overall_score ?? null,
          })
        }
        router.replace('/practice/mock')
        return
      }

      setFeedback(response.data.feedback)
      setInsights(response.data.insights || null)
      setPhase('result')
      if (response.data.feedback?.scoring_failed) {
        toast.error('Scoring is temporarily unavailable — please try again shortly.')
      } else {
        toast.success('Response scored successfully!')
        trackEvent('score_viewed', {
          module: 'writing',
          scenario_id: selectedScenario.id,
          overall_score: response.data.feedback?.overall_score,
        })
      }
    } catch (error: any) {
      console.error('Failed to submit:', error)
      if (!isUpgradeRequiredError(error)) {
        const errData = error.response?.data?.detail
        toast.error(errData?.error || errData?.message || error.response?.data?.detail || 'Failed to submit response')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading writing scenarios...</div>
      </div>
    )
  }

  if (phase === 'select') {
    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-3xl font-bold text-[#0F2356]">Writing Practice</h1>
          <p className="text-gray-500 mt-1">Choose a scenario to write an OET-style letter</p>

          <WeakSpots endpoint="/writing/weakness" />

          {upgradeRequired ? (
            <UpgradeRequired
              className="mt-8"
              title="Writing practice is a Pro/Elite feature"
              message="Upgrade your plan to unlock full OET writing scenarios."
            />
          ) : scenarios.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-lg shadow mt-8">
              <p className="text-xl text-gray-500 mb-2">No writing scenarios available</p>
              <p className="text-muted-foreground">Ask an admin to create writing scenarios</p>
            </div>
          ) : (
            <>
              <div className="flex flex-col sm:flex-row gap-3 mt-8">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search scenarios by title or setting..."
                    aria-label="Search scenarios"
                    className="pl-10 pr-9"
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery('')}
                      aria-label="Clear search"
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
                <Select
                  value={filterDifficulty}
                  onChange={(e) => setFilterDifficulty(e.target.value as typeof filterDifficulty)}
                  aria-label="Filter by difficulty"
                  className="sm:w-48"
                >
                  <option value="all">All difficulties</option>
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                </Select>
                <Select
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value as typeof filterStatus)}
                  aria-label="Filter by completion status"
                  className="sm:w-48"
                >
                  <option value="all">All scenarios</option>
                  <option value="completed">Completed</option>
                  <option value="not_tried">Not yet tried</option>
                </Select>
              </div>

              {filteredScenarios.length === 0 ? (
                <div className="text-center py-16 bg-white rounded-lg shadow mt-4">
                  <p className="text-lg font-semibold text-gray-500 mb-1">No scenarios match your filters</p>
                  <p className="text-muted-foreground text-sm">Try a different search term or clear a filter</p>
                </div>
              ) : (
                <div className="grid md:grid-cols-2 gap-6 mt-4">
                  {filteredScenarios.map((s) => {
                    const tasks = s.nurse_card?.tasks || []
                    return (
                      <Card
                        key={s.id}
                        className="relative p-6 flex flex-col gap-4 hover:shadow-md transition-all"
                      >
                        {completedScenarioIds.has(s.id) && <CompletedBadge />}
                        <DifficultyBadge difficulty={s.difficulty} />
                        <h3 className="text-xl font-bold text-primary">{s.title}</h3>
                        <p className="text-gray-600 text-sm line-clamp-3 leading-relaxed">{s.setting}</p>
                        {tasks.length > 0 && (
                          <p className="text-sm text-gray-500">{tasks.length} writing tasks</p>
                        )}
                        <Button onClick={() => handleSelectScenario(s)} className="w-full">
                          Start Writing →
                        </Button>
                      </Card>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    )
  }

  if (phase === 'write' && selectedScenario) {
    const task = selectedScenario.nurse_card?.role || ''
    const words = countWords(writingText)
    const wordTone = words === 0 ? 'text-muted-foreground' : words < WORD_MIN ? 'text-amber-600' : words > 200 ? 'text-amber-600' : 'text-emerald-600'
    return (
      <div className="min-h-screen bg-gray-50 py-8 px-4">
        <div className="max-w-6xl mx-auto">
          {!mockId && (
            <button onClick={handleBackToScenarios} className="text-sm text-gray-500 hover:text-gray-700 mb-4">
              ← Back to scenarios
            </button>
          )}

          {/* Exam header. In a mock it carries the live timer + reading-lock state. */}
          <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
            <div className="min-w-0">
              <p className="text-xs font-semibold tracking-widest text-primary uppercase">{mockId ? 'Full Mock Test · Writing (3 of 3)' : 'OET Writing sub-test · Nursing'}</p>
              <h2 className="text-2xl font-bold text-gray-900">{selectedScenario.title}</h2>
              <p className="text-sm text-gray-500 mt-1">Reading time 5 minutes · Writing time 40 minutes · Body approximately 180–200 words</p>
            </div>
            {mockId && secondsLeft !== null && (
              <div
                role="timer"
                aria-live="off"
                aria-atomic="true"
                aria-label={`${writeLocked ? 'Reading' : 'Writing'} time remaining: ${fmtClock(secondsLeft)}`}
                className={`px-4 py-2 rounded-xl font-bold tabular-nums flex items-center gap-2 shrink-0 ${
                secondsLeft <= 0 ? 'bg-red-100 text-red-700'
                : secondsLeft <= 300 ? 'bg-amber-100 text-amber-700'
                : 'bg-[#0F2356]/5 text-[#0F2356]'}`}>
                <span aria-hidden>⏱</span>
                <span className="text-[11px] font-semibold uppercase tracking-wide">{writeLocked ? 'Reading' : 'Writing'}</span>
                <span className="text-base">{fmtClock(secondsLeft)}</span>
              </div>
            )}
          </div>

          {writeLocked && (
            <div className="mb-6 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 text-sm">
              Reading time — study the case notes now. Writing unlocks in {fmtClock(secondsLeft! - WRITE_WINDOW_SECONDS)}.
            </div>
          )}

          <div className="grid lg:grid-cols-2 gap-6 items-start">
            {/* Case notes — styled like the exam paper */}
            <Card className="p-0 overflow-hidden lg:sticky lg:top-6">
              <div className="bg-gray-900 text-white text-xs font-bold px-4 py-2 tracking-widest">NOTES</div>
              <div className="p-6 max-h-[65vh] overflow-y-auto">
                <p className="text-[15px] text-gray-800 leading-relaxed whitespace-pre-wrap">{selectedScenario.setting}</p>
              </div>
            </Card>

            {/* Task + answer */}
            <div className="space-y-6">
              <Card className="p-6">
                <p className="text-xs font-bold tracking-widest text-gray-500 uppercase mb-2">Writing Task</p>
                <p className="text-gray-800 leading-relaxed whitespace-pre-wrap">{task}</p>
                <ul className="mt-4 space-y-1.5 text-sm text-gray-600">
                  <li className="flex gap-2"><span className="text-primary">•</span> Expand the relevant notes into complete sentences</li>
                  <li className="flex gap-2"><span className="text-primary">•</span> Do not use note form</li>
                  <li className="flex gap-2"><span className="text-primary">•</span> Use letter format</li>
                </ul>
              </Card>

              <Card className="p-6">
                {/* Input mode toggle — hidden in a mock (typed answers only, like the exam). */}
                {!mockId && (
                  <div className="inline-flex rounded-lg border border-gray-200 p-1 mb-4">
                    <button
                      onClick={() => setInputMode('type')}
                      className={`px-4 py-1.5 text-sm font-semibold rounded-md transition ${inputMode === 'type' ? 'bg-primary text-white' : 'text-gray-600 hover:text-gray-900'}`}
                    >
                      Type
                    </button>
                    <button
                      onClick={() => setInputMode('upload')}
                      className={`px-4 py-1.5 text-sm font-semibold rounded-md transition ${inputMode === 'upload' ? 'bg-primary text-white' : 'text-gray-600 hover:text-gray-900'}`}
                    >
                      Upload handwritten
                    </button>
                  </div>
                )}

                {/* Upload panel */}
                {inputMode === 'upload' && (
                  <div className="mb-4 rounded-xl border border-dashed border-gray-300 p-4">
                    <div className="flex flex-wrap gap-3 mb-3">
                      {photos.map((p, i) => (
                        <div key={i} className="relative">
                          <img src={p.url} alt={`Page ${i + 1}`} className="h-24 w-20 object-cover rounded-lg border" />
                          <button
                            onClick={() => setPhotos((prev) => { URL.revokeObjectURL(prev[i].url); return prev.filter((_, j) => j !== i) })}
                            className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full w-5 h-5 text-xs flex items-center justify-center"
                            aria-label={`Remove page ${i + 1}`}
                          >
                            ×
                          </button>
                          {photos.length > 1 && (
                            <div className="flex items-center justify-between mt-1 px-0.5">
                              <button
                                onClick={() => movePhoto(i, -1)}
                                disabled={i === 0}
                                aria-label={`Move page ${i + 1} earlier`}
                                className="text-gray-500 disabled:opacity-30 text-sm leading-none"
                              >
                                ◀
                              </button>
                              <span className="text-[10px] text-muted-foreground">Page {i + 1}</span>
                              <button
                                onClick={() => movePhoto(i, 1)}
                                disabled={i === photos.length - 1}
                                aria-label={`Move page ${i + 1} later`}
                                className="text-gray-500 disabled:opacity-30 text-sm leading-none"
                              >
                                ▶
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                      {photos.length < 3 && (
                        <label className="h-24 w-20 rounded-lg border-2 border-dashed border-gray-300 flex flex-col items-center justify-center text-muted-foreground cursor-pointer hover:border-primary hover:text-primary text-xs text-center">
                          + Photo
                          <input
                            type="file"
                            accept="image/*"
                            multiple
                            className="hidden"
                            onChange={(e) => { addPhotos(e.target.files); e.target.value = '' }}
                          />
                        </label>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mb-3">Photograph your handwritten letter — up to 3 pages, clear and well-lit.</p>
                    <div className="flex gap-2">
                      <Button onClick={handleReadPhotos} disabled={ocrLoading || photos.length === 0} className="flex-1">
                        {ocrLoading ? 'Reading…' : `Read my handwriting${photos.length ? ` (${photos.length})` : ''}`}
                      </Button>
                      {photos.length > 0 && (
                        <Button variant="outline" onClick={clearPhotos} disabled={ocrLoading}>
                          Retake
                        </Button>
                      )}
                    </div>
                    <div className="mt-3 pt-3 border-t border-gray-100 text-center">
                      <button onClick={startPhoneSession} className="text-sm font-semibold text-primary hover:underline">
                        📱 On a laptop? Use your phone instead
                      </button>
                    </div>
                  </div>
                )}

                {ocrDone && inputMode === 'upload' && (
                  <div className="mb-2 text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
                    ✎ Read from your photos. Check it for mistakes and fix any misreads before submitting. If it looks wrong, tap <strong>Retake</strong> and photograph it again.
                  </div>
                )}

                <label htmlFor="writing" className="block text-sm font-semibold text-gray-700 mb-2">
                  {inputMode === 'upload' ? 'Your Letter (read from photos — edit as needed)' : 'Your Letter'}
                </label>
                <textarea
                  id="writing"
                  value={writingText}
                  onChange={(e) => setWritingText(e.target.value)}
                  disabled={writeLocked}
                  className="w-full h-80 px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-emerald-100 focus:border-emerald-500 outline-none resize-y leading-relaxed disabled:bg-gray-50 disabled:cursor-not-allowed"
                  placeholder={writeLocked ? 'Reading time — writing is locked for now.' : inputMode === 'upload' ? 'Your letter text will appear here after reading your photos.' : 'Dear ...,\n\nWrite your letter here.'}
                />
                <div className={`text-sm mt-2 ${wordTone}`}>
                  {words} words {words === 0 ? '' : words < WORD_MIN ? '— aim for 180–200' : words > 200 ? '— a little long, aim for 180–200' : '✓'}
                </div>

                <Button onClick={() => handleSubmit(false)} disabled={isSubmitting || writeLocked} className="w-full mt-4">
                  {isSubmitting ? (mockId ? 'Submitting…' : 'Scoring...') : writeLocked ? 'Reading time…' : mockId ? 'Finish Writing →' : 'Submit for Scoring'}
                </Button>
              </Card>
            </div>
          </div>

          {phoneUrl && (
            <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={closePhoneSession}>
              <div className="bg-white rounded-2xl p-8 max-w-sm w-full text-center" onClick={(e) => e.stopPropagation()}>
                <h3 className="text-xl font-bold text-gray-900 mb-1">Scan with your phone</h3>
                <p className="text-sm text-gray-500 mb-6">Open your phone&apos;s camera and point it at this code to photograph your letter.</p>
                <div className="flex justify-center mb-6">
                  <div className="p-4 bg-white rounded-xl border">
                    <QRCodeSVG value={phoneUrl} size={200} />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mb-6 flex items-center justify-center gap-2">
                  <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  Waiting for your phone — the text will appear here automatically.
                </p>
                <Button variant="outline" onClick={closePhoneSession} className="w-full">Cancel</Button>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  if (phase === 'result' && feedback) {
    if (feedback.scoring_failed) {
      return (
        <div className="min-h-screen bg-gray-50 py-12 px-4">
          <Card className="max-w-2xl mx-auto text-center p-8">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Scoring is temporarily unavailable</h2>
            <p className="text-gray-500 mb-6">Your letter was saved, but we couldn&apos;t generate feedback right now. Please try again shortly.</p>
            <div className="flex gap-4 justify-center">
              <Button onClick={() => setPhase('write')}>
                Try Again
              </Button>
              <Button variant="outline" onClick={handleBackToScenarios}>
                Back to Scenarios
              </Button>
            </div>
          </Card>
        </div>
      )
    }

    return (
      <div className="min-h-screen bg-gray-50 py-12 px-4">
        <div className="max-w-4xl mx-auto">
          <Card className="p-8 mb-6">
            <div className="text-center mb-8">
              <div className="text-5xl font-bold text-emerald-600">Grade {feedback.estimated_oet_grade}</div>
              <div className="text-lg font-semibold text-emerald-700 mt-2">
                Estimated OET score: {feedback.overall_score}/500
              </div>
              <div className="text-xs text-muted-foreground mt-1">Approximate — for practice guidance only</div>
            </div>

            <div className="grid md:grid-cols-2 gap-4 mb-8">
              {CRITERIA.map(({ key, label, max }) => {
                const c = feedback.scores[key] || { score: null, feedback: '' }
                return (
                  <div key={key} className="rounded-xl bg-gray-50 p-4">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <p className="text-sm font-semibold text-[#0F2356]">{label}</p>
                      <span className={`text-sm font-bold shrink-0 ${scoreColor(c.score, max)}`}>
                        {c.score ?? '—'}/{max}
                      </span>
                    </div>
                    {c.feedback && <p className="text-xs text-gray-600 leading-relaxed">{c.feedback}</p>}
                  </div>
                )
              })}
            </div>

            {feedback.top_strengths?.length > 0 && (
              <div className="bg-emerald-50 p-4 rounded-lg mb-4">
                <h4 className="font-bold text-emerald-700 mb-2">Top Strengths</h4>
                <ul className="list-disc list-inside space-y-1">
                  {feedback.top_strengths.map((s, i) => (
                    <li key={i} className="text-sm text-emerald-800">{s}</li>
                  ))}
                </ul>
              </div>
            )}

            {feedback.top_improvements?.length > 0 && (
              <div className="bg-amber-50 p-4 rounded-lg mb-4">
                <h4 className="font-bold text-amber-700 mb-2">Areas to Improve</h4>
                <ul className="list-disc list-inside space-y-1">
                  {feedback.top_improvements.map((s, i) => (
                    <li key={i} className="text-sm text-amber-800">{s}</li>
                  ))}
                </ul>
              </div>
            )}

            {feedback.corrected_version && (
              <div className="bg-gray-50 p-4 rounded-lg">
                <h4 className="font-bold text-gray-700 mb-2">Improved Version</h4>
                <p className="text-gray-700 whitespace-pre-line text-sm leading-relaxed">{feedback.corrected_version}</p>
              </div>
            )}
          </Card>

          {insights && (
            <div className="rounded-2xl bg-indigo-50 border border-indigo-100 p-6 mb-6">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="size-4 text-indigo-500" aria-hidden="true" />
                <h3 className="text-base font-bold text-[#0F2356]">Today&apos;s Writing Insights</h3>
              </div>
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Strongest</p>
                  <p className="text-sm font-semibold text-emerald-700">
                    {insights.strongest_skill.label} ({insights.strongest_skill.score}/6)
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Weakest</p>
                  <p className="text-sm font-semibold text-amber-700">
                    {insights.weakest_skill.label} ({insights.weakest_skill.score}/6)
                  </p>
                </div>
              </div>
              <p className="text-sm text-gray-700 leading-relaxed mb-3">{insights.recommendation_reason}</p>
              <div className="rounded-xl bg-white border border-indigo-100 px-4 py-3 mb-3">
                <p className="text-xs text-indigo-500 font-semibold uppercase tracking-wide mb-1">Try This Next</p>
                <p className="text-sm text-gray-700 leading-relaxed">{insights.actionable_improvement}</p>
              </div>
              <p className="text-xs text-gray-500 italic mb-4">{insights.confidence_message}</p>
              {insights.next_best_action && (
                <button
                  onClick={() => {
                    const scenario = scenarios.find((s) => s.id === insights.next_best_action!.scenario_id)
                    if (scenario) handleSelectScenario(scenario)
                  }}
                  className="flex w-full items-center justify-between gap-3 rounded-xl bg-white border border-indigo-200 px-4 py-3 hover:border-indigo-400 transition text-left"
                >
                  <div>
                    <p className="text-xs text-indigo-500 font-semibold uppercase tracking-wide">Recommended Next</p>
                    <p className="text-sm font-semibold text-[#0F2356]">{insights.next_best_action.title}</p>
                    <p className="text-xs text-gray-500">{insights.next_best_action.reason}</p>
                  </div>
                  <span className="text-indigo-500 text-sm font-semibold shrink-0">Start →</span>
                </button>
              )}
            </div>
          )}

          <div className="flex gap-4">
            <Button className="flex-1" onClick={handleBackToScenarios}>
              Try Another Scenario
            </Button>
            <Button variant="outline" className="flex-1" onClick={() => router.push('/dashboard')}>
              Go to Dashboard
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return null
}
