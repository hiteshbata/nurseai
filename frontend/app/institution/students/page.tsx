'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import { RouteSpinner } from '@/components/RouteSpinner'
import { useSessionUsage } from '@/components/AppShell'
import { UserPlus } from 'lucide-react'
import { classifyLoadError, formatJoined, scoreLabel, sessionsLabel, mobileSessionsLabel } from './helpers'

interface StudentRow {
  name: string | null
  email: string
  status: 'active' | 'invited' | 'revoked'
  joined_at: string | null
  sessions_used_this_month: number
  sessions_remaining: number | null
  latest_speaking_score: number | null
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'denied' }
  | { kind: 'multiple' }
  | { kind: 'error' }
  | { kind: 'ready'; data: StudentRow[] }

const STATUS_LABEL: Record<string, string> = { active: 'Active', invited: 'Invited', revoked: 'Revoked' }
const STATUS_CLASS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
  invited: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
  revoked: 'bg-slate-100 text-slate-600 dark:bg-slate-500/10 dark:text-slate-400',
}

export default function InstitutionStudentsPage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const { usage } = useSessionUsage()
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
      .get('/institution/students')
      .then((res) => {
        if (!cancelled) setState({ kind: 'ready', data: res.data })
      })
      .catch((error: any) => {
        if (cancelled) return
        setState({ kind: classifyLoadError(error.response?.status) })
      })
    return () => {
      cancelled = true
    }
  }, [status, session, router, retryKey])

  const retry = useCallback(() => setRetryKey((k) => k + 1), [])

  if (status === 'loading' || state.kind === 'loading') {
    return <RouteSpinner message="Loading students..." />
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
          We couldn&apos;t load your students. Please try again.
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
  const isAdmin = usage?.institution_admin_role === 'institution_admin'

  return (
    <div className="py-6 sm:py-8">
      <header className="mb-6 sm:mb-8">
        <p className="text-sm font-semibold text-muted-foreground">Institution</p>
        <h1 className="text-2xl font-bold text-foreground">Students</h1>
      </header>

      {data.length === 0 ? (
        <section className="rounded-xl border border-dashed border-border p-8 text-center">
          <p className="text-sm font-semibold text-foreground">No students yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Invite your students to start your OET Speaking program.
          </p>
          {isAdmin && (
            <Link
              href="/institution/invites"
              className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:opacity-90"
            >
              <UserPlus className="h-4 w-4" aria-hidden="true" />
              Invite Students
            </Link>
          )}
        </section>
      ) : (
        <>
          {/* Desktop: table, hidden below md */}
          <div className="hidden overflow-x-auto rounded-xl border border-border md:block">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Joined</th>
                  <th className="px-4 py-3">Sessions</th>
                  <th className="px-4 py-3">Latest Speaking</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.map((s, i) => (
                  <tr key={i}>
                    <td className="px-4 py-3 font-medium text-foreground">{s.name || '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{s.email}</td>
                    <td className="px-4 py-3 text-muted-foreground">{formatJoined(s.joined_at)}</td>
                    <td className="px-4 py-3 tabular-nums text-foreground">
                      {sessionsLabel(s.sessions_used_this_month, s.sessions_remaining)}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-foreground">{scoreLabel(s.latest_speaking_score)}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-3 py-1 text-xs font-semibold ${STATUS_CLASS[s.status] ?? ''}`}>
                        {STATUS_LABEL[s.status] ?? s.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile: cards, hidden at md and up */}
          <div className="flex flex-col gap-3 md:hidden">
            {data.map((s, i) => (
              <div key={i} className="rounded-xl border border-border p-4">
                <p className="font-semibold text-foreground">{s.name || s.email}</p>
                {s.name && <p className="text-sm text-muted-foreground">{s.email}</p>}
                <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  <dt className="text-muted-foreground">Joined</dt>
                  <dd className="text-foreground">{formatJoined(s.joined_at)}</dd>
                  <dt className="text-muted-foreground">Sessions</dt>
                  <dd className="text-foreground">
                    {mobileSessionsLabel(s.sessions_used_this_month, s.sessions_remaining)}
                  </dd>
                  <dt className="text-muted-foreground">Latest score</dt>
                  <dd className="text-foreground">{scoreLabel(s.latest_speaking_score)}</dd>
                  <dt className="text-muted-foreground">Status</dt>
                  <dd>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${STATUS_CLASS[s.status] ?? ''}`}>
                      {STATUS_LABEL[s.status] ?? s.status}
                    </span>
                  </dd>
                </dl>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
