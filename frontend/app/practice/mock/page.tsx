'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useSupabaseSession, linkAnonymousAccount, getCurrentSession, humanizeAuthError } from '@/lib/supabase'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { FOUR_WEEK_PLANS, type OetModule } from '@/lib/oetScoring'

// Phase 1 sitting: Listening -> Reading -> Writing, then Speaking separately.
type Section = 'listening' | 'reading' | 'writing'

interface MockState {
  active: boolean
  id?: string
  status?: 'in_progress' | 'awaiting_speaking' | 'complete'
  current_section?: Section | null
  content_id?: number | null
}

interface SectionResult {
  band?: number
  correct?: number
  total?: number
}

interface WritingResult {
  grade?: string
  overall_score?: number
}

interface SpeakingResult {
  overall_band?: number
}

interface FullResults {
  listening?: SectionResult
  reading?: SectionResult
  writing?: WritingResult
  speaking?: SpeakingResult
}

interface MockTestPack {
  id: number
  label: string
  completed: boolean
}

// Official OET timing, shown on the cover sheet so the sitting reads as the real exam.
const SECTIONS: { key: Section; label: string; time: string; blurb: string }[] = [
  { key: 'listening', label: 'Listening', time: '~40 min', blurb: 'Three parts. Each recording plays once.' },
  { key: 'reading', label: 'Reading', time: '60 min', blurb: 'Part A 15 min, then Parts B & C 45 min.' },
  { key: 'writing', label: 'Writing', time: '40 min', blurb: '5 min reading, then a 40 min letter.' },
]

function sectionRoute(section: Section, contentId: number | null | undefined, mockId: string) {
  const q = `?mock=${mockId}`
  if (section === 'listening') return `/practice/listening/test/${contentId}${q}`
  if (section === 'reading') return `/practice/reading/test/${contentId}${q}`
  return `/practice/writing${q}` // writing reads its scenario id from the mock session
}

export default function MockTestPage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [view, setView] = useState<'loading' | 'picker' | 'landing' | 'entering' | 'sealed' | 'report'>('loading')
  const [mockId, setMockId] = useState<string | null>(null)
  const [packs, setPacks] = useState<MockTestPack[]>([])
  const [selectedPack, setSelectedPack] = useState<MockTestPack | null>(null)
  const [starting, setStarting] = useState(false)
  const enteredRef = useRef(false) // guard against a double redirect in strict-mode remounts

  const routeInto = (s: MockState) => {
    if (enteredRef.current) return
    enteredRef.current = true
    setView('entering')
    router.replace(sectionRoute(s.current_section as Section, s.content_id, s.id!))
  }

  const showPicker = () => {
    setSelectedPack(null)
    setView('picker')
    api.get('/mock/tests').then((res) => setPacks(res.data || [])).catch(() => setPacks([]))
  }

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status !== 'authenticated') return

    api.get('/mock/current')
      .then((res) => {
        const s: MockState = res.data
        if (s.id) setMockId(s.id)
        if (s.active && s.status === 'in_progress' && s.current_section) return routeInto(s)
        if (s.active && s.status === 'awaiting_speaking') return setView('sealed')
        if (s.active && s.status === 'complete') return setView('report')
        showPicker()
      })
      .catch(() => showPicker())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  const pickPack = (pack: MockTestPack) => {
    setSelectedPack(pack)
    setView('landing')
  }

  const begin = async () => {
    if (!selectedPack) return showPicker()
    setStarting(true)
    try {
      const res = await api.post('/mock/start', { mock_test_id: selectedPack.id })
      const s: MockState = { active: true, ...res.data }
      if (s.id) setMockId(s.id)
      if (s.current_section) return routeInto(s)
      setView('sealed') // already past LRW somehow — show the sealed screen
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Could not start your mock test. Please try again.')
      setStarting(false)
    }
  }

  if (view === 'picker') {
    return (
      <PickerScreen
        packs={packs}
        onSelect={pickPack}
        onDashboard={() => router.push('/dashboard')}
      />
    )
  }

  if (view === 'loading' || view === 'entering') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#0F2356] text-white gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-white/30 border-t-white animate-spin" />
        <p className="text-sm text-blue-100 tracking-wide">
          {view === 'entering' ? 'Entering your test room…' : 'Preparing…'}
        </p>
      </div>
    )
  }

  if (view === 'sealed') {
    return (
      <SealedScreen
        mockId={mockId}
        onDashboard={() => router.push('/dashboard')}
        onStartSpeaking={() => router.push(`/practice/speaking?mock=${mockId}`)}
        onStartNew={showPicker}
        starting={starting}
      />
    )
  }

  if (view === 'report' && mockId) {
    return <ReportView mockId={mockId} onDashboard={() => router.push('/dashboard')} onStartNew={showPicker} starting={starting} />
  }

  // ── LANDING: exam cover sheet for the chosen pack ──
  return (
    <div className="min-h-screen bg-gray-100 py-10 px-4 sm:py-16">
      <div className="mx-auto w-full max-w-2xl mock-rise">
        {/* The cover sheet — styled like the real OET booklet front page */}
        <div className="rounded-2xl bg-white shadow-[0_24px_60px_-24px_rgba(15,35,86,0.45)] overflow-hidden ring-1 ring-black/5">
          {/* Official header bar */}
          <div className="bg-[#0F2356] px-7 py-6 sm:px-9 sm:py-7">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-300">Occupational English Test · Nursing</p>
            <h1 className="mt-1.5 text-2xl sm:text-3xl font-bold text-white">{selectedPack?.label || 'Full Mock Test'}</h1>
            <p className="mt-2 text-sm text-blue-100/90 leading-relaxed">
              One timed sitting under real exam conditions. Sections run in order and lock behind you — just like the day itself.
            </p>
          </div>

          <div className="px-7 py-7 sm:px-9">
            {/* The three written sub-tests, as an exam order-of-play, not a card grid */}
            <ol className="divide-y divide-gray-100">
              {SECTIONS.map((s, i) => (
                <li key={s.key} className="flex items-center gap-4 py-3.5 first:pt-0">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#0F2356]/5 text-sm font-bold text-[#0F2356]">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-gray-900">{s.label}</p>
                    <p className="text-[13px] text-gray-500">{s.blurb}</p>
                  </div>
                  <span className="shrink-0 tabular-nums text-sm font-semibold text-gray-700">{s.time}</span>
                </li>
              ))}
              {/* Speaking sits apart, scheduled after — mirrors the real OET */}
              <li className="flex items-center gap-4 py-3.5 opacity-60">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-dashed border-gray-300 text-sm font-bold text-gray-400">
                  4
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-gray-700">Speaking</p>
                  <p className="text-[13px] text-gray-500">Two role plays — taken separately, after the written test.</p>
                </div>
                <span className="shrink-0 text-xs font-medium text-gray-400">later</span>
              </li>
            </ol>

            {/* Instructions to candidate */}
            <div className="mt-6 rounded-xl bg-gray-50 px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-gray-500">Before you begin</p>
              <ul className="mt-2.5 space-y-2 text-[13px] text-gray-600">
                <li className="flex gap-2.5"><Check /> Each section is timed and submits automatically when time runs out.</li>
                <li className="flex gap-2.5"><Check /> You cannot return to a section once it is done.</li>
                <li className="flex gap-2.5"><Check /> Your results stay sealed until you complete the Speaking test.</li>
                <li className="flex gap-2.5"><Check /> Set aside about <strong className="font-semibold text-gray-800">2½ hours</strong> and a quiet room.</li>
              </ul>
            </div>

            <Button onClick={begin} disabled={starting} className="mt-6 w-full h-12 text-base">
              {starting ? 'Assembling your paper…' : 'Begin Full Mock Test'}
            </Button>
            <p className="mt-3 text-center text-xs text-muted-foreground">
              Starting begins the timer. Treat it like the real exam.
            </p>
          </div>
        </div>

        <button onClick={() => router.push('/dashboard')} className="mt-6 block w-full text-center text-sm text-muted-foreground hover:text-gray-600 transition">
          Not now — back to dashboard
        </button>
      </div>

      <style jsx>{`
        .mock-rise { animation: mockRise 0.5s cubic-bezier(0.16, 1, 0.3, 1) both; }
        @keyframes mockRise {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  )
}

// Numbered packs an admin has generated (/admin/mock-tests). Each is a fixed,
// pre-built bundle -- picking one skips the old per-attempt random assembly,
// so there's no "Assembling your paper…" wait once a pack exists.
function PickerScreen({
  packs,
  onSelect,
  onDashboard,
}: {
  packs: MockTestPack[]
  onSelect: (pack: MockTestPack) => void
  onDashboard: () => void
}) {
  return (
    <div className="min-h-screen bg-gray-100 py-10 px-4 sm:py-16">
      <div className="mx-auto w-full max-w-2xl mock-rise">
        <div className="rounded-2xl bg-white shadow-[0_24px_60px_-24px_rgba(15,35,86,0.45)] overflow-hidden ring-1 ring-black/5">
          <div className="bg-[#0F2356] px-7 py-6 sm:px-9 sm:py-7">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-300">Occupational English Test · Nursing</p>
            <h1 className="mt-1.5 text-2xl sm:text-3xl font-bold text-white">Full Mock Test</h1>
            <p className="mt-2 text-sm text-blue-100/90 leading-relaxed">Choose a mock test to begin.</p>
          </div>

          <div className="px-7 py-7 sm:px-9">
            {packs.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-6">
                No mock tests are available yet. Check back soon.
              </p>
            ) : (
              <ul className="divide-y divide-gray-100">
                {packs.map((p) => (
                  <li key={p.id}>
                    <button
                      onClick={() => onSelect(p)}
                      className="w-full flex items-center justify-between gap-4 py-4 text-left hover:bg-gray-50 transition rounded-lg px-2 -mx-2"
                    >
                      <div>
                        <p className="font-semibold text-gray-900">{p.label}</p>
                        <p className="text-[13px] text-gray-500">{p.completed ? 'Completed — retake anytime' : 'Not started yet'}</p>
                      </div>
                      <span className="shrink-0 text-sm font-semibold text-blue-600">
                        {p.completed ? 'Retake →' : 'Start →'}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <button onClick={onDashboard} className="mt-6 block w-full text-center text-sm text-muted-foreground hover:text-gray-600 transition">
          Not now — back to dashboard
        </button>
      </div>

      <style jsx>{`
        .mock-rise { animation: mockRise 0.5s cubic-bezier(0.16, 1, 0.3, 1) both; }
        @keyframes mockRise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  )
}

function Check() {
  return (
    <svg viewBox="0 0 20 20" className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" fill="currentColor" aria-hidden>
      <path fillRule="evenodd" d="M16.7 5.3a1 1 0 0 1 0 1.4l-7.5 7.5a1 1 0 0 1-1.4 0L3.3 10.7a1 1 0 1 1 1.4-1.4l3.3 3.3 6.8-6.8a1 1 0 0 1 1.4 0Z" clipRule="evenodd" />
    </svg>
  )
}

// Written test done, Speaking pending — results held back until the mock is whole.
function SealedScreen({
  mockId,
  onDashboard,
  onStartSpeaking,
  onStartNew,
  starting,
}: {
  mockId: string | null
  onDashboard: () => void
  onStartSpeaking: () => void
  onStartNew: () => void
  starting: boolean
}) {
  return (
    <div className="min-h-screen bg-gray-100 py-16 px-4 flex items-start justify-center">
      <div className="w-full max-w-lg mock-rise">
        <div className="rounded-2xl bg-white shadow-[0_24px_60px_-24px_rgba(15,35,86,0.45)] overflow-hidden ring-1 ring-black/5 text-center">
          <div className="bg-[#0F2356] px-8 py-9">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/10 ring-1 ring-white/20">
              <svg viewBox="0 0 24 24" className="h-7 w-7 text-blue-200" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                <rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white">Written test complete</h1>
            <p className="mt-2 text-sm text-blue-100/90">Listening, Reading and Writing are done and recorded.</p>
          </div>
          <div className="px-8 py-8">
            <p className="text-gray-700 leading-relaxed">
              Your results stay <strong className="font-semibold text-gray-900">sealed</strong> until you finish the Speaking test — the
              same way the real OET reports every sub-test together.
            </p>
            <div className="mt-6 rounded-xl border border-dashed border-gray-300 px-5 py-5">
              <p className="font-semibold text-gray-800">Speaking mock</p>
              <p className="mt-1 text-[13px] text-gray-500">Two live role plays with an AI patient. Take it whenever you're ready.</p>
              <Button onClick={onStartSpeaking} disabled={!mockId} className="mt-4 w-full">Start Speaking mock →</Button>
            </div>
            <Button onClick={onStartNew} disabled={starting} variant="outline" className="mt-6 w-full">
              {starting ? 'Assembling your paper…' : 'Start another mock test'}
            </Button>
            <button onClick={onDashboard} className="mt-4 text-sm text-muted-foreground hover:text-gray-600 transition">
              Back to dashboard
            </button>
          </div>
        </div>
      </div>
      <style jsx>{`
        .mock-rise { animation: mockRise 0.5s cubic-bezier(0.16, 1, 0.3, 1) both; }
        @keyframes mockRise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  )
}

// The full mock is complete -- every sub-test reports in its own native scale,
// same as the real OET results letter: Listening/Reading/Speaking as a 0-6 band,
// Writing as a letter grade + /500.
function ReportView({
  mockId,
  onDashboard,
  onStartNew,
  starting,
}: {
  mockId: string
  onDashboard: () => void
  onStartNew: () => void
  starting: boolean
}) {
  const [results, setResults] = useState<FullResults | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/mock/${mockId}/result`)
      .then((res) => setResults(res.data.results || {}))
      .catch(() => setResults({}))
      .finally(() => setLoading(false))
  }, [mockId])

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#0F2356] text-white gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-white/30 border-t-white animate-spin" />
        <p className="text-sm text-blue-100 tracking-wide">Preparing your results…</p>
      </div>
    )
  }

  const cards: { label: string; value: string; sub: string }[] = [
    {
      label: 'Listening',
      value: results?.listening?.band != null ? `${results.listening.band}/6` : '—',
      sub: results?.listening ? `${results.listening.correct ?? 0}/${results.listening.total ?? 0} correct` : '',
    },
    {
      label: 'Reading',
      value: results?.reading?.band != null ? `${results.reading.band}/6` : '—',
      sub: results?.reading ? `${results.reading.correct ?? 0}/${results.reading.total ?? 0} correct` : '',
    },
    {
      label: 'Writing',
      value: results?.writing?.grade ? `Grade ${results.writing.grade}` : '—',
      sub: results?.writing?.overall_score != null ? `${results.writing.overall_score}/500` : '',
    },
    {
      label: 'Speaking',
      value: results?.speaking?.overall_band != null ? `${results.speaking.overall_band}/6` : '—',
      sub: results?.speaking ? 'Average of 2 role plays' : '',
    },
  ]

  return (
    <div className="min-h-screen bg-gray-100 py-10 px-4 sm:py-16">
      <div className="mx-auto w-full max-w-2xl mock-rise">
        <div className="rounded-2xl bg-white shadow-[0_24px_60px_-24px_rgba(15,35,86,0.45)] overflow-hidden ring-1 ring-black/5">
          <div className="bg-[#0F2356] px-7 py-7 sm:px-9 text-center">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-300">Occupational English Test · Nursing</p>
            <h1 className="mt-1.5 text-2xl sm:text-3xl font-bold text-white">Full Mock Test — Results</h1>
            <p className="mt-2 text-sm text-blue-100/90">All four sub-tests are in. Here's your full report.</p>
          </div>

          <div className="px-7 py-7 sm:px-9">
            <div className="grid grid-cols-2 gap-4">
              {cards.map((c) => (
                <div key={c.label} className="rounded-xl bg-gray-50 px-4 py-5 text-center">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">{c.label}</p>
                  <p className="mt-1.5 text-xl font-bold text-[#0F2356]">{c.value}</p>
                  {c.sub && <p className="mt-1 text-[11px] text-muted-foreground">{c.sub}</p>}
                </div>
              ))}
            </div>

            <FreeReportGate results={results || {}} />

            <Button onClick={onStartNew} disabled={starting} className="mt-6 w-full">
              {starting ? 'Assembling your paper…' : 'Start another mock test'}
            </Button>
            <button onClick={onDashboard} className="mt-4 block w-full text-center text-sm text-muted-foreground hover:text-gray-600 transition">
              Back to dashboard
            </button>
          </div>
        </div>
      </div>
      <style jsx>{`
        .mock-rise { animation: mockRise 0.5s cubic-bezier(0.16, 1, 0.3, 1) both; }
        @keyframes mockRise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  )
}

// Weakest of the four sub-tests by fraction of its own scale -- band/6 for
// Listening/Reading/Speaking, overall_score/500 for Writing. Not a fabricated
// combined band (the app doesn't put all four on one comparable numeric
// scale), just "which one is relatively furthest behind."
function weakestModule(results: FullResults): { module: OetModule; label: string } | null {
  const entries: { module: OetModule; label: string; fraction: number }[] = []
  if (results.listening?.band != null) entries.push({ module: 'listening', label: 'Listening', fraction: results.listening.band / 6 })
  if (results.reading?.band != null) entries.push({ module: 'reading', label: 'Reading', fraction: results.reading.band / 6 })
  if (results.speaking?.overall_band != null) entries.push({ module: 'speaking', label: 'Speaking', fraction: results.speaking.overall_band / 6 })
  if (results.writing?.overall_score != null) entries.push({ module: 'writing', label: 'Writing', fraction: results.writing.overall_score / 500 })
  if (!entries.length) return null
  return entries.reduce((min, e) => (e.fraction < min.fraction ? e : min))
}

// The free-mock-test lead magnet (see /tools/oet-mock-test-free): raw scores
// above are already free for everyone. This panel only renders anything
// extra while the viewer is still on an anonymous Supabase session -- the
// moment they create a real account (same user_id, no data migration), it
// swaps to the unlocked report in place.
function FreeReportGate({ results }: { results: FullResults }) {
  const { session } = useSupabaseSession()
  const [linked, setLinked] = useState(false)
  const [pendingConfirm, setPendingConfirm] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!session?.user?.is_anonymous) return null // paid/regular accounts always see the free score cards, no gate at all

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    setSubmitting(true)
    try {
      await linkAnonymousAccount(email, password, name)
      const fresh = await getCurrentSession()
      if (fresh && !fresh.user.is_anonymous) {
        toast.success('Account created — your full report is unlocked!')
        setLinked(true)
      } else {
        setPendingConfirm(true)
      }
    } catch (err: any) {
      toast.error(humanizeAuthError(err?.message))
    } finally {
      setSubmitting(false)
    }
  }

  if (linked) {
    const weak = weakestModule(results)
    return (
      <div className="mt-6 rounded-xl border border-emerald-100 bg-emerald-50 px-5 py-5">
        <p className="text-sm font-semibold text-emerald-900">Your full band report</p>
        {weak ? (
          <>
            <p className="mt-2 text-sm text-emerald-800">
              Your comparatively weakest sub-test is <strong>{weak.label}</strong> — here's a free 4-week plan for it.
            </p>
            <ol className="mt-3 space-y-2">
              {FOUR_WEEK_PLANS[weak.module].map((step) => (
                <li key={step.title} className="text-[13px] text-emerald-900">
                  <span className="font-semibold">{step.title}:</span> {step.body}
                </li>
              ))}
            </ol>
          </>
        ) : (
          <p className="mt-2 text-sm text-emerald-800">Complete all four sub-tests to see your weakest-area plan.</p>
        )}
        <Link href="/tools/oet-score-calculator" className="mt-3 inline-block text-sm font-semibold text-emerald-900 underline">
          Check these scores against your regulator →
        </Link>
        <Link
          href="/upgrade"
          className="mt-4 block rounded-lg bg-[#0F2356] px-4 py-2.5 text-center text-sm font-semibold text-white hover:bg-[#0F2356]/90 transition"
        >
          Unlock unlimited mock tests →
        </Link>
      </div>
    )
  }

  if (pendingConfirm) {
    return (
      <div className="mt-6 rounded-xl border border-dashed border-gray-300 px-5 py-5 text-center">
        <p className="text-sm text-gray-700">
          Check your email to confirm your account, then reopen this page to see your full report.
        </p>
      </div>
    )
  }

  return (
    <div className="mt-6 rounded-xl border border-dashed border-gray-300 px-5 py-5">
      <p className="font-semibold text-gray-800">Get your full band report</p>
      <p className="mt-1 text-[13px] text-gray-500">
        Create a free account to see your weakest sub-test, a targeted 4-week study plan, and a regulator pass/fail check.
      </p>
      <form onSubmit={handleSubmit} className="mt-4 space-y-2.5">
        <input
          type="text"
          required
          placeholder="Full name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-[#0F2356]/40"
        />
        <input
          type="email"
          required
          placeholder="Email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-[#0F2356]/40"
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="Create a password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="h-10 w-full rounded-lg border border-gray-200 px-3 text-sm outline-none focus:border-[#0F2356]/40"
        />
        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? 'Creating account…' : 'Unlock my full report →'}
        </Button>
      </form>
    </div>
  )
}
