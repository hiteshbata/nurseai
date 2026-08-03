'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Loader2 } from 'lucide-react'
import { useSupabaseSession, signInAnonymously } from '@/lib/supabase'
import api, { isUpgradeRequiredError } from '@/lib/api'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'

// Entry point only -- once a mock is running, the existing Elite product page
// (/practice/mock) drives the whole sitting (section order, timers, resume,
// sealed screen, report). An anonymous Supabase session is a real session as
// far as that page's auth check is concerned, so it needs zero changes to
// host a signed-in-anonymously visitor; the report screen there is what
// grew the "sign up for your full report" gate (see ReportView there).
export function StartFreeMock() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [blocked, setBlocked] = useState<string | null>(null)

  const begin = async () => {
    setBusy(true)
    try {
      if (status === 'unauthenticated') {
        await signInAnonymously()
      }

      // A returning visitor (or one who reloaded mid-sitting) already has a
      // mock underway or finished -- send them straight there instead of
      // trying to start a second one.
      const current = await api.get('/mock/current')
      if (current.data?.active) {
        router.push('/practice/mock')
        return
      }

      const packsRes = await api.get('/mock/tests')
      const packs: { id: number }[] = packsRes.data || []
      if (!packs.length) {
        toast.error('No mock tests are available right now — check back soon.')
        return
      }
      await api.post('/mock/start', { mock_test_id: packs[0].id })
      router.push('/practice/mock')
    } catch (err: any) {
      if (isUpgradeRequiredError(err)) {
        setBlocked("You've used your free mock test — sign up to keep practising.")
        return
      }
      const detail = err?.response?.data?.detail
      const message = typeof detail === 'string' ? detail : detail?.error
      if (message) {
        setBlocked(message)
      } else {
        toast.error('Could not start your free mock test — please try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  if (blocked) {
    return (
      <div className="rounded-2xl bg-white shadow-[0_24px_60px_-24px_rgba(15,35,86,0.45)] ring-1 ring-black/5 px-7 py-8 text-center">
        <p className="text-gray-700">{blocked}</p>
        <Link
          href="/auth/register"
          className="mt-4 inline-flex h-11 items-center justify-center rounded-xl bg-[#0F2356] px-6 text-sm font-semibold text-white motion-safe:transition-colors hover:bg-[#0F2356]/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
        >
          Create a free account →
        </Link>
      </div>
    )
  }

  return (
    <div className="rounded-2xl bg-white shadow-[0_24px_60px_-24px_rgba(15,35,86,0.45)] ring-1 ring-black/5 px-7 py-8 text-center">
      <Button onClick={begin} disabled={busy || status === 'loading'} className="h-12 w-full text-base">
        {busy && <Loader2 className="w-4 h-4 motion-safe:animate-spin" aria-hidden="true" />}
        {busy ? 'Preparing your test…' : 'Begin Free Mock Test'}
      </Button>
      <p className="mt-3 text-xs text-muted-foreground">
        No signup required to take it. Set aside about 2½ hours.
      </p>
    </div>
  )
}
