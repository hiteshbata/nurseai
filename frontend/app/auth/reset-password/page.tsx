'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase, updatePassword, signOut } from '@/lib/supabase'
import toast from 'react-hot-toast'
import { Loader2, Eye, EyeOff, Check } from 'lucide-react'
import { AuthLeftPanel } from '@/components/auth/auth-left-panel'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'
import { hasUrlError as hasUrlErrorParams, hasRecoveryParams as hasRecoveryParamsParams, isInviteFlow as isInviteFlowParams } from './helpers'

type LinkStatus = 'verifying' | 'valid' | 'invalid'

function currentParams(): { search: URLSearchParams; hash: URLSearchParams } | null {
  if (typeof window === 'undefined') return null
  return {
    search: new URLSearchParams(window.location.search),
    hash: new URLSearchParams(window.location.hash.replace(/^#/, '')),
  }
}

function hasUrlError(): boolean {
  const params = currentParams()
  return params ? hasUrlErrorParams(params.search, params.hash) : false
}

function hasRecoveryParams(): boolean {
  const params = currentParams()
  return params ? hasRecoveryParamsParams(params.search, params.hash) : false
}

function isInviteFlow(): boolean {
  const params = currentParams()
  return params ? isInviteFlowParams(params.search) : false
}

export default function ResetPasswordPage() {
  const router = useRouter()
  const [linkStatus, setLinkStatus] = useState<LinkStatus>('verifying')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    // Supabase redirects expired/invalid recovery links back here with an
    // `error` param instead of establishing a session.
    if (hasUrlError()) {
      setLinkStatus('invalid')
      return
    }

    let cancelled = false

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
      if (cancelled) return
      if (event === 'PASSWORD_RECOVERY') {
        setLinkStatus('valid')
      }
    })

    if (hasRecoveryParams()) {
      // Fallback in case the PASSWORD_RECOVERY event fired before this
      // listener was attached (the recovery session is already active by
      // the time this effect runs). Only trusted when the URL itself
      // carries a recovery token -- otherwise an unrelated pre-existing
      // session (e.g. someone already logged in on a shared computer who
      // navigates here directly) would be mistaken for a valid reset link,
      // letting them change that account's password without knowing it.
      supabase.auth.getSession().then(({ data: { session } }: any) => {
        if (cancelled) return
        setLinkStatus((current) => (current === 'valid' ? current : session ? 'valid' : 'invalid'))
      })
    } else {
      setLinkStatus((current) => (current === 'valid' ? current : 'invalid'))
    }

    return () => {
      cancelled = true
      subscription?.unsubscribe()
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError('')

    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setIsSubmitting(true)
    try {
      await updatePassword(password)
      setDone(true)
      if (isInviteFlow()) {
        // Invite acceptance, unlike recovery, should land the user straight
        // in their institution dashboard on the session /auth/confirm
        // already established -- not force a second login.
        toast.success('Password set. Taking you to your dashboard…')
        setTimeout(() => router.push('/auth/callback'), 1200)
      } else {
        // The recovery link only grants a temporary session for this one
        // action. Sign it out and send the user through a normal login with
        // their new password rather than leaving them implicitly signed in.
        await signOut()
        toast.success('Password updated. Please sign in with your new password.')
        setTimeout(() => router.push('/auth/login'), 2000)
      }
    } catch (err: any) {
      setError(err.message || 'Could not update your password. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen">
      <AuthLeftPanel />

      <div className="flex flex-1 items-center justify-center bg-background px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <SpeakOETLogo height={28} variant="full" theme="dark" priority />
          </div>

          <div className="flex w-full flex-col gap-6">
            {linkStatus === 'verifying' && (
              <div className="flex flex-col items-center gap-3 py-8">
                <Loader2 className="h-8 w-8 animate-spin text-foreground" aria-hidden="true" />
                <p className="text-sm text-muted-foreground">Verifying your reset link…</p>
              </div>
            )}

            {linkStatus === 'invalid' && (
              <>
                <div className="flex flex-col gap-1">
                  <h2 className="text-2xl font-bold text-foreground text-balance">
                    Link expired or invalid
                  </h2>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    This password reset link is no longer valid. Links expire after a short
                    time and can only be used once.
                  </p>
                </div>
                <Link
                  href="/auth/forgot-password"
                  className="h-11 w-full rounded-xl bg-emerald-500 text-sm font-semibold text-white shadow-sm transition-all duration-150 hover:bg-emerald-600 hover:shadow-md flex items-center justify-center"
                >
                  Request a new link
                </Link>
              </>
            )}

            {linkStatus === 'valid' && !done && (
              <>
                <div className="flex flex-col gap-1">
                  <h2 className="text-2xl font-bold text-foreground text-balance">
                    Set a new password
                  </h2>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    Choose a new password for your account.
                  </p>
                </div>

                {error && (
                  <div role="alert" className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="password" className="text-sm font-medium text-foreground">
                      New password
                    </label>
                    <div className="relative">
                      <input
                        id="password"
                        type={showPassword ? 'text' : 'password'}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="Create a new password"
                        autoComplete="new-password"
                        required
                        className="h-11 w-full rounded-xl border border-border bg-muted/60 px-3.5 pr-11 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all duration-150 focus:border-primary/40 focus:bg-card focus:ring-2 focus:ring-primary/10 hover:border-border"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        className="absolute right-0 top-0 h-11 w-11 flex items-center justify-center text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded-xl"
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="confirmPassword" className="text-sm font-medium text-foreground">
                      Confirm new password
                    </label>
                    <input
                      id="confirmPassword"
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Confirm your new password"
                      autoComplete="new-password"
                      required
                      className="h-11 w-full rounded-xl border border-border bg-muted/60 px-3.5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all duration-150 focus:border-primary/40 focus:bg-card focus:ring-2 focus:ring-primary/10 hover:border-border"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="h-11 w-full rounded-xl bg-emerald-500 text-sm font-semibold text-white shadow-sm transition-all duration-150 hover:bg-emerald-600 hover:shadow-md active:scale-[0.99] disabled:opacity-60 flex items-center justify-center gap-2"
                  >
                    {isSubmitting ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                        Updating…
                      </>
                    ) : (
                      'Update password'
                    )}
                  </button>
                </form>
              </>
            )}

            {done && (
              <div className="flex flex-col items-center gap-3 py-8 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100">
                  <Check className="h-6 w-6 text-emerald-600" aria-hidden="true" />
                </div>
                <h2 className="text-xl font-bold text-foreground">Password updated</h2>
                <p className="text-sm text-muted-foreground">Redirecting you to sign in…</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  )
}
