'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import { RouteSpinner } from '@/components/RouteSpinner'
import { Input } from '@/components/ui/input'
import { Plus, Copy, Check } from 'lucide-react'
import {
  classifyLoadError,
  deriveDisplayStatus,
  usesLabel,
  formatInviteDate,
  validateMaxUses,
  validateExpiration,
  type DisplayStatus,
} from './helpers'

interface InviteRow {
  id: string
  status: string
  max_uses: number | null
  use_count: number
  remaining_uses: number | null
  expires_at: string | null
  created_at: string
}

interface CreatedInvite {
  id: string
  token: string
  join_url: string
  role: string
  max_uses: number | null
  expires_at: string | null
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'denied' }
  | { kind: 'multiple' }
  | { kind: 'error' }
  | { kind: 'ready'; data: InviteRow[] }

const DISPLAY_STATUS_LABEL: Record<DisplayStatus, string> = { active: 'Active', revoked: 'Revoked', expired: 'Expired' }
const DISPLAY_STATUS_CLASS: Record<DisplayStatus, string> = {
  active: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
  revoked: 'bg-slate-100 text-slate-600 dark:bg-slate-500/10 dark:text-slate-400',
  expired: 'bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
}

export default function InstitutionInvitesPage() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [retryKey, setRetryKey] = useState(0)

  const [showForm, setShowForm] = useState(false)
  const [maxUsesInput, setMaxUsesInput] = useState('')
  const [expiresInput, setExpiresInput] = useState('')
  const [maxUsesError, setMaxUsesError] = useState<string | undefined>()
  const [expirationError, setExpirationError] = useState<string | undefined>()
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<CreatedInvite | null>(null)
  const [copied, setCopied] = useState(false)
  const maxUsesRef = useRef<HTMLInputElement>(null)

  const loadInvites = useCallback(() => {
    let cancelled = false
    api
      .get('/institution/invites')
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
  }, [])

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status !== 'authenticated' || session?.user?.is_anonymous) return

    setState({ kind: 'loading' })
    return loadInvites()
  }, [status, session, router, retryKey, loadInvites])

  const retry = useCallback(() => setRetryKey((k) => k + 1), [])

  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(t)
  }, [copied])

  function openForm() {
    setShowForm(true)
    setTimeout(() => maxUsesRef.current?.focus(), 0)
  }

  function resetForm() {
    setCreated(null)
    setMaxUsesInput('')
    setExpiresInput('')
    setMaxUsesError(undefined)
    setExpirationError(undefined)
  }

  async function handleCreateSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (creating) return
    const maxUsesResult = validateMaxUses(maxUsesInput)
    const expirationResult = validateExpiration(expiresInput)
    setMaxUsesError(maxUsesResult.error)
    setExpirationError(expirationResult.error)
    if (!maxUsesResult.valid || !expirationResult.valid) return

    setCreating(true)
    try {
      const res = await api.post('/institution/invites', {
        max_uses: maxUsesResult.value,
        expires_at: expirationResult.iso,
      })
      setCreated(res.data)
      loadInvites()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Could not create invitation. Please try again.')
    } finally {
      setCreating(false)
    }
  }

  async function handleCopy(joinUrl: string) {
    try {
      await navigator.clipboard.writeText(joinUrl)
      setCopied(true)
    } catch {
      toast.error('Could not copy — copy the link manually.')
    }
  }

  async function handleRevoke(invite: InviteRow) {
    if (!confirm('Revoke this invitation?\n\nStudents who have already joined will not be affected.')) return
    try {
      await api.post(`/institution/invites/${invite.id}/revoke`)
      toast.success('Invitation revoked')
      loadInvites()
    } catch (error: any) {
      const httpStatus = error.response?.status
      if (httpStatus === 404) {
        toast.error('Invitation not found.')
        loadInvites()
      } else if (httpStatus === 403) {
        toast.error("You don't have permission to manage invitations.")
      } else if (httpStatus === 409) {
        toast.error('Your account is associated with multiple institutions. Please contact support.')
      } else {
        toast.error('Something went wrong. Please try again.')
      }
    }
  }

  if (status === 'loading' || state.kind === 'loading') {
    return <RouteSpinner message="Loading invitations..." />
  }

  if (state.kind === 'denied') {
    return (
      <div className="mx-auto max-w-lg py-24 text-center">
        <h1 className="text-lg font-bold text-foreground">Access restricted</h1>
        <p className="mt-2 text-sm text-muted-foreground">You don&apos;t have permission to manage invitations.</p>
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
        <p className="mt-2 text-sm text-muted-foreground">We couldn&apos;t load your invitations. Please try again.</p>
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
      <header className="mb-6 flex items-center justify-between gap-4 sm:mb-8">
        <div>
          <p className="text-sm font-semibold text-muted-foreground">Institution</p>
          <h1 className="text-2xl font-bold text-foreground">Invitations</h1>
        </div>
        {!showForm && !created && (
          <button
            onClick={openForm}
            className="flex min-h-11 items-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:opacity-90"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Create Invitation
          </button>
        )}
      </header>

      {created && (
        <section className="mb-8 rounded-xl border border-emerald-200 bg-emerald-50/60 p-5 dark:border-emerald-500/20 dark:bg-emerald-500/5">
          <h2 className="text-base font-bold text-foreground">Invitation created</h2>
          <p className="mt-1 text-sm text-muted-foreground">Share this link with your students:</p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input
              readOnly
              value={created.join_url}
              onFocus={(e) => e.currentTarget.select()}
              className="h-11 w-full select-all rounded-xl border border-gray-200 bg-white px-3.5 text-sm text-primary outline-none"
            />
            <button
              onClick={() => handleCopy(created.join_url)}
              className="flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-border px-4 text-sm font-semibold text-foreground hover:bg-muted"
            >
              {copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
              {copied ? 'Copied' : 'Copy link'}
            </button>
          </div>
          <button
            onClick={resetForm}
            className="mt-4 text-sm font-semibold text-emerald-700 hover:underline dark:text-emerald-400"
          >
            Create another invitation
          </button>
        </section>
      )}

      {!created && showForm && (
        <form
          onSubmit={handleCreateSubmit}
          className="mb-8 rounded-xl border border-border p-5"
        >
          <h2 className="text-base font-bold text-foreground">Create Invitation</h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="invite-max-uses" className="text-sm font-semibold text-foreground">
                Maximum uses
              </label>
              <Input
                id="invite-max-uses"
                ref={maxUsesRef}
                type="number"
                min={1}
                step={1}
                placeholder="Unlimited"
                value={maxUsesInput}
                onChange={(e) => {
                  setMaxUsesInput(e.target.value)
                  if (maxUsesError) setMaxUsesError(undefined)
                }}
                className="mt-1.5"
              />
              {maxUsesError && <p className="mt-1.5 text-sm text-red-600">{maxUsesError}</p>}
            </div>
            <div>
              <label htmlFor="invite-expires" className="text-sm font-semibold text-foreground">
                Expires
              </label>
              <Input
                id="invite-expires"
                type="datetime-local"
                placeholder="No expiration"
                value={expiresInput}
                onChange={(e) => {
                  setExpiresInput(e.target.value)
                  if (expirationError) setExpirationError(undefined)
                }}
                className="mt-1.5"
              />
              {expirationError && <p className="mt-1.5 text-sm text-red-600">{expirationError}</p>}
            </div>
          </div>
          <div className="mt-5 flex gap-3">
            <button
              type="submit"
              disabled={creating}
              className="min-h-11 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {creating ? 'Creating...' : 'Create Invitation'}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="min-h-11 rounded-lg border border-border px-4 text-sm font-semibold text-foreground hover:bg-muted"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {data.length === 0 ? (
        <section className="rounded-xl border border-dashed border-border p-8 text-center">
          <p className="text-sm font-semibold text-foreground">No invitations yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Create an invitation link and share it with your students.
          </p>
          {!showForm && !created && (
            <button
              onClick={openForm}
              className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:opacity-90"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Create Invitation
            </button>
          )}
        </section>
      ) : (
        <>
          {/* Desktop: table, hidden below md */}
          <div className="hidden overflow-x-auto rounded-xl border border-border md:block">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Uses</th>
                  <th className="px-4 py-3">Remaining</th>
                  <th className="px-4 py-3">Expires</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.map((invite) => {
                  const displayStatus = deriveDisplayStatus(invite.status, invite.expires_at)
                  return (
                    <tr key={invite.id}>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${DISPLAY_STATUS_CLASS[displayStatus]}`}
                        >
                          {DISPLAY_STATUS_LABEL[displayStatus]}
                        </span>
                      </td>
                      <td className="px-4 py-3 tabular-nums text-foreground">{invite.use_count} used</td>
                      <td className="px-4 py-3 tabular-nums text-foreground">
                        {invite.remaining_uses === null ? 'Unlimited' : `${invite.remaining_uses} remaining`}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{formatInviteDate(invite.expires_at)}</td>
                      <td className="px-4 py-3 text-muted-foreground">{formatInviteDate(invite.created_at)}</td>
                      <td className="px-4 py-3">
                        {displayStatus === 'active' && (
                          <button
                            onClick={() => handleRevoke(invite)}
                            className="text-sm font-semibold text-red-600 hover:underline"
                          >
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile: cards, hidden at md and up */}
          <div className="flex flex-col gap-3 md:hidden">
            {data.map((invite) => {
              const displayStatus = deriveDisplayStatus(invite.status, invite.expires_at)
              return (
                <div key={invite.id} className="rounded-xl border border-border p-4">
                  <div className="flex items-center justify-between">
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-semibold ${DISPLAY_STATUS_CLASS[displayStatus]}`}
                    >
                      {DISPLAY_STATUS_LABEL[displayStatus]}
                    </span>
                    {displayStatus === 'active' && (
                      <button
                        onClick={() => handleRevoke(invite)}
                        className="text-sm font-semibold text-red-600 hover:underline"
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                  <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                    <dt className="text-muted-foreground">Uses</dt>
                    <dd className="text-foreground">{usesLabel(invite.use_count, invite.remaining_uses)}</dd>
                    <dt className="text-muted-foreground">Expires</dt>
                    <dd className="text-foreground">{formatInviteDate(invite.expires_at)}</dd>
                    <dt className="text-muted-foreground">Created</dt>
                    <dd className="text-foreground">{formatInviteDate(invite.created_at)}</dd>
                  </dl>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
