'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import { RouteSpinner } from '@/components/RouteSpinner'
import { formatJoined, scoreLabel, sessionsLabel } from '../helpers'
import { classifyLoadError, moduleLabel, formatDateTime, lastActivityLabel } from './helpers'

interface Submission {
  id: string
  module: string
  score: number | null
  created_at: string
}

interface StudentDetail {
  user_id: string
  name: string | null
  email: string
  status: 'active' | 'invited' | 'revoked'
  role: string
  joined_at: string | null
  last_seen_at: string | null
  sessions_used_this_month: number
  sessions_remaining: number | null
  speaking_sessions_per_month: number | null
  latest_speaking_score: number | null
  recent_submissions: Submission[]
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'denied' }
  | { kind: 'multiple' }
  | { kind: 'notFound' }
  | { kind: 'error' }
  | { kind: 'ready'; data: StudentDetail }

const STATUS_LABEL: Record<string, string> = { active: 'Active', invited: 'Invited', revoked: 'Revoked' }
const STATUS_CLASS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
  invited: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
  revoked: 'bg-slate-100 text-slate-600 dark:bg-slate-500/10 dark:text-slate-400',
}

export default function InstitutionStudentDetailPage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const userId = params.id
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
      .get(`/institution/students/${userId}`)
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
  }, [status, session, router, userId, retryKey])

  const retry = useCallback(() => setRetryKey((k) => k + 1), [])

  if (status === 'loading' || state.kind === 'loading') {
    return <RouteSpinner message="Loading student..." />
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

  if (state.kind === 'notFound') {
    return (
      <div className="mx-auto max-w-lg py-24 text-center">
        <h1 className="text-lg font-bold text-foreground">Student not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This student doesn&apos;t exist in your institution.
        </p>
        <Link
          href="/institution/students"
          className="mt-6 inline-flex min-h-11 items-center rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:opacity-90"
        >
          Back to Students
        </Link>
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <div className="mx-auto max-w-lg py-24 text-center">
        <h1 className="text-lg font-bold text-foreground">Something went wrong.</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          We couldn&apos;t load this student. Please try again.
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

  return (
    <div className="py-6 sm:py-8">
      <Link
        href="/institution/students"
        className="mb-6 inline-block text-sm font-semibold text-muted-foreground hover:text-foreground"
      >
        ← Back to Students
      </Link>

      <header className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">{data.name || data.email}</h1>
        {data.name && <p className="text-sm text-muted-foreground">{data.email}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${STATUS_CLASS[data.status] ?? ''}`}>
            {STATUS_LABEL[data.status] ?? data.status}
          </span>
          <span className="rounded-full bg-muted px-3 py-1 text-xs font-semibold text-muted-foreground">
            {data.role === 'student' ? 'Student' : data.role}
          </span>
        </div>
        {data.joined_at && (
          <p className="mt-2 text-sm text-muted-foreground">Joined {formatJoined(data.joined_at)}</p>
        )}
      </header>

      <section className="rounded-xl border border-border p-4 sm:p-6">
        <h2 className="text-sm font-semibold text-foreground">Speaking Usage</h2>
        <dl className="mt-3 grid grid-cols-3 gap-4 text-center">
          <div>
            <dt className="text-xs text-muted-foreground">Sessions used this month</dt>
            <dd className="mt-1 text-xl font-bold tabular-nums text-foreground">
              {data.sessions_used_this_month}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Sessions remaining</dt>
            <dd className="mt-1 text-xl font-bold tabular-nums text-foreground">
              {data.sessions_remaining === null ? '—' : data.sessions_remaining}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Per-student monthly quota</dt>
            <dd className="mt-1 text-xl font-bold tabular-nums text-foreground">
              {data.speaking_sessions_per_month === null ? 'Unlimited' : data.speaking_sessions_per_month}
            </dd>
          </div>
        </dl>
        <p className="sr-only">{sessionsLabel(data.sessions_used_this_month, data.sessions_remaining)}</p>
      </section>

      <div className="mt-6 grid gap-6 sm:grid-cols-2">
        <section className="rounded-xl border border-border p-4 sm:p-6">
          <h2 className="text-sm font-semibold text-foreground">Latest Speaking Score</h2>
          <p className="mt-2 text-2xl font-bold tabular-nums text-foreground">
            {data.latest_speaking_score === null ? (
              <span className="text-base font-normal text-muted-foreground">No speaking score yet</span>
            ) : (
              scoreLabel(data.latest_speaking_score)
            )}
          </p>
        </section>

        <section className="rounded-xl border border-border p-4 sm:p-6">
          <h2 className="text-sm font-semibold text-foreground">Last Activity</h2>
          <p className="mt-2 text-lg font-semibold text-foreground">{lastActivityLabel(data.last_seen_at)}</p>
        </section>
      </div>

      <section className="mt-6">
        <h2 className="mb-3 text-sm font-semibold text-foreground">Recent Activity</h2>
        {data.recent_submissions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border p-8 text-center">
            <p className="text-sm text-muted-foreground">No recent submissions</p>
          </div>
        ) : (
          <>
            <div className="hidden overflow-x-auto rounded-xl border border-border md:block">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3">Module</th>
                    <th className="px-4 py-3">Score</th>
                    <th className="px-4 py-3">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.recent_submissions.map((sub) => (
                    <tr key={sub.id}>
                      <td className="px-4 py-3 font-medium text-foreground">{moduleLabel(sub.module)}</td>
                      <td className="px-4 py-3 tabular-nums text-foreground">{scoreLabel(sub.score)}</td>
                      <td className="px-4 py-3 text-muted-foreground">{formatDateTime(sub.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-col gap-3 md:hidden">
              {data.recent_submissions.map((sub) => (
                <div key={sub.id} className="rounded-xl border border-border p-4">
                  <p className="font-semibold text-foreground">{moduleLabel(sub.module)}</p>
                  <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                    <dt className="text-muted-foreground">Score</dt>
                    <dd className="text-foreground">{scoreLabel(sub.score)}</dd>
                    <dt className="text-muted-foreground">Date</dt>
                    <dd className="text-foreground">{formatDateTime(sub.created_at)}</dd>
                  </dl>
                </div>
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  )
}
