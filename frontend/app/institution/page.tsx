'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import { RouteSpinner } from '@/components/RouteSpinner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Users, Mic, Gauge, UserPlus, ClipboardList } from 'lucide-react'

interface OverviewData {
  name: string
  logo_url: string | null
  member_counts: Record<string, number>
  modules: string[]
  sessions_used_this_month: number
  speaking_sessions_per_month: number | null
  active_student_count: number
  role: 'teacher' | 'institution_admin'
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'denied' }
  | { kind: 'multiple' }
  | { kind: 'error' }
  | { kind: 'ready'; data: OverviewData }

const MODULE_LABELS: Record<string, string> = {
  speaking: 'Speaking',
  reading: 'Reading',
  listening: 'Listening',
  writing: 'Writing',
  mock_tests: 'Mock Test',
}

// member_counts keys are "{role}_{status}" (see backend GET /institution/overview)
// -- only active/pending totals are useful on an overview card, not the raw
// per-role/per-status breakdown.
function countByStatusSuffix(counts: Record<string, number>, suffix: string): number {
  return Object.entries(counts)
    .filter(([key]) => key.endsWith(suffix))
    .reduce((sum, [, n]) => sum + n, 0)
}

export default function InstitutionOverviewPage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status !== 'authenticated' || session?.user?.is_anonymous) return

    let cancelled = false
    setState({ kind: 'loading' })
    api
      .get('/institution/overview')
      .then((res) => {
        if (!cancelled) setState({ kind: 'ready', data: res.data })
      })
      .catch((error: any) => {
        if (cancelled) return
        const httpStatus = error.response?.status
        if (httpStatus === 401 || httpStatus === 403) {
          setState({ kind: 'denied' })
        } else if (httpStatus === 409) {
          setState({ kind: 'multiple' })
        } else {
          setState({ kind: 'error' })
        }
      })
    return () => {
      cancelled = true
    }
  }, [status, session, router, retryKey])

  const retry = useCallback(() => setRetryKey((k) => k + 1), [])

  if (status === 'loading' || state.kind === 'loading') {
    return <RouteSpinner message="Loading institution overview..." />
  }

  if (state.kind === 'denied') {
    return (
      <div className="mx-auto max-w-lg py-24 text-center">
        <h1 className="text-lg font-bold text-foreground">Access restricted</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Your account doesn&apos;t have an institution role that can view this page.
        </p>
        <Link
          href="/dashboard"
          className="mt-6 inline-flex min-h-11 items-center rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:opacity-90"
        >
          Go to dashboard
        </Link>
      </div>
    )
  }

  if (state.kind === 'multiple') {
    return (
      <div className="mx-auto max-w-lg py-24 text-center">
        <h1 className="text-lg font-bold text-foreground">Multiple institutions found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Your account is associated with multiple institutions. Please contact support.
        </p>
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <div className="mx-auto max-w-lg py-24 text-center">
        <h1 className="text-lg font-bold text-foreground">Something went wrong.</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          We couldn&apos;t load your institution overview. Please try again.
        </p>
        <button
          onClick={retry}
          className="mt-6 min-h-11 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:opacity-90"
        >
          Try again
        </button>
      </div>
    )
  }

  const { data } = state
  const isAdmin = data.role === 'institution_admin'
  const activeMembers = countByStatusSuffix(data.member_counts, '_active')
  const pendingMembers = countByStatusSuffix(data.member_counts, '_pending')
  const quotaLabel =
    data.speaking_sessions_per_month === null ? 'Unlimited' : String(data.speaking_sessions_per_month)

  return (
    <div className="py-6 sm:py-8">
      <header className="mb-6 flex items-center gap-4 sm:mb-8">
        {data.logo_url && (
          <img
            src={data.logo_url}
            alt={`${data.name} logo`}
            className="h-12 w-12 shrink-0 rounded-lg object-contain"
          />
        )}
        <div>
          <p className="text-sm font-semibold text-muted-foreground">Institution Overview</p>
          <h1 className="text-2xl font-bold text-foreground">{data.name}</h1>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex-row items-center gap-3 space-y-0">
            <Users className="h-5 w-5 text-emerald-700" aria-hidden="true" />
            <CardTitle className="text-sm font-semibold text-muted-foreground">Active students</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold tabular-nums text-foreground">{data.active_student_count}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center gap-3 space-y-0">
            <Mic className="h-5 w-5 text-emerald-700" aria-hidden="true" />
            <CardTitle className="text-sm font-semibold text-muted-foreground">Speaking sessions</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold tabular-nums text-foreground">{data.sessions_used_this_month}</p>
            <p className="text-xs text-muted-foreground">used this month, all students combined</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center gap-3 space-y-0">
            <Gauge className="h-5 w-5 text-emerald-700" aria-hidden="true" />
            <CardTitle className="text-sm font-semibold text-muted-foreground">Per-student monthly quota</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold tabular-nums text-foreground">{quotaLabel}</p>
            <p className="text-xs text-muted-foreground">speaking sessions / month, per student</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center gap-3 space-y-0">
            <ClipboardList className="h-5 w-5 text-emerald-700" aria-hidden="true" />
            <CardTitle className="text-sm font-semibold text-muted-foreground">Memberships</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold tabular-nums text-foreground">{activeMembers}</p>
            <p className="text-xs text-muted-foreground">
              active{pendingMembers > 0 ? ` · ${pendingMembers} pending` : ''}
            </p>
          </CardContent>
        </Card>
      </div>

      <section className="mt-8">
        <h2 className="text-base font-bold text-foreground">Modules</h2>
        {data.modules.length > 0 ? (
          <ul className="mt-3 flex flex-wrap gap-2">
            {data.modules.map((mod) => (
              <li
                key={mod}
                className="rounded-full bg-emerald-50 px-3 py-1 text-sm font-semibold text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
              >
                {MODULE_LABELS[mod] ?? mod}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">No modules enabled yet.</p>
        )}
      </section>

      {data.active_student_count === 0 && (
        <section className="mt-8 rounded-xl border border-dashed border-border p-6 text-center">
          <p className="text-sm font-semibold text-foreground">No students yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Invite your first students to start your OET Speaking program.
          </p>
        </section>
      )}

      <section className="mt-8 flex flex-wrap gap-3">
        {isAdmin && (
          <Link
            href="/institution/invites"
            className="flex min-h-11 items-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:opacity-90"
          >
            <UserPlus className="h-4 w-4" aria-hidden="true" />
            Invite students
          </Link>
        )}
        <Link
          href="/institution/students"
          className="flex min-h-11 items-center gap-2 rounded-lg border border-border px-4 text-sm font-semibold text-foreground hover:bg-muted"
        >
          <Users className="h-4 w-4" aria-hidden="true" />
          View students
        </Link>
      </section>
    </div>
  )
}
