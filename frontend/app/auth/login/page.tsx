'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase, signIn, useSupabaseSession, humanizeAuthError } from '@/lib/supabase'
import api from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import { trackMetaEvent } from '@/lib/meta-pixel'
import toast from 'react-hot-toast'
import { Loader2, Eye, EyeOff } from 'lucide-react'
import { AuthLeftPanel } from '@/components/auth/auth-left-panel'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'
import { getSafeReturnTo } from '@/lib/auth-redirect'

function GoogleIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" className="h-4 w-4 shrink-0" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.14 0 5.96 1.08 8.18 2.84l6.08-6.08C34.46 3.17 29.52 1 24 1 14.96 1 7.27 6.48 3.84 14.26l7.08 5.5C12.64 13.62 17.88 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.64-.15-3.22-.42-4.74H24v9h12.74c-.55 2.96-2.2 5.46-4.68 7.14l7.3 5.68C43.46 37.48 46.5 31.4 46.5 24.5z" />
      <path fill="#FBBC05" d="M10.92 28.26A14.52 14.52 0 0 1 9.5 24c0-1.48.26-2.9.72-4.24l-7.08-5.5A23.46 23.46 0 0 0 .5 24c0 3.78.9 7.34 2.5 10.5l7.92-6.24z" />
      <path fill="#34A853" d="M24 47c5.52 0 10.16-1.82 13.54-4.96l-7.3-5.68c-2.02 1.36-4.6 2.14-7.24 2.14-6.12 0-11.36-4.12-13.08-9.74l-7.92 6.24C7.28 41.52 14.96 47 24 47z" />
    </svg>
  )
}

function MicrosoftIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 21" className="h-4 w-4 shrink-0" aria-hidden="true">
      <rect x="1" y="1" width="9" height="9" fill="#F25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
      <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
      <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
    </svg>
  )
}

export default function LoginPage() {
  const router = useRouter()
  const { session, status: authStatus } = useSupabaseSession()
  const returnTo = getSafeReturnTo()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [microsoftLoading, setMicrosoftLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({})

  useEffect(() => {
    if (authStatus === 'authenticated') {
      router.push(getSafeReturnTo() || '/dashboard')
    }
  }, [authStatus, router])

  const handleGoogleSignIn = async () => {
    setGoogleLoading(true)
    try {
      const returnTo = getSafeReturnTo()
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: window.location.origin + '/auth/callback' +
            (returnTo ? '?returnTo=' + encodeURIComponent(returnTo) : ''),
        },
      })
      if (error) throw error
    } catch (error: any) {
      toast.error(error.message || 'Google sign in failed')
      setGoogleLoading(false)
    }
  }

  const handleMicrosoftSignIn = async () => {
    setMicrosoftLoading(true)
    try {
      const returnTo = getSafeReturnTo()
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'azure',
        options: {
          redirectTo: window.location.origin + '/auth/callback' +
            (returnTo ? '?returnTo=' + encodeURIComponent(returnTo) : ''),
          scopes: 'email',
        },
      })
      if (error) throw error
    } catch (error: any) {
      toast.error(error.message || 'Microsoft sign in failed')
      setMicrosoftLoading(false)
    }
  }

  const validate = () => {
    const errs: { email?: string; password?: string } = {}
    if (!email.trim()) errs.email = 'Enter your email'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) errs.email = 'Enter a valid email address'
    if (!password) errs.password = 'Enter your password'
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError('')
    if (!validate()) return
    setIsLoading(true)
    try {
      await signIn(email, password)
      trackEvent('login_completed', { method: 'email' })
      trackMetaEvent('UserLoggedIn', { method: 'email' }, { email })
      toast.success('Logged in successfully!')
      const returnTo = getSafeReturnTo()
      router.push(returnTo || '/dashboard')
      if (!returnTo) {
        api.get('/onboarding/status').then((res) => {
          if (res.data?.onboarding_completed !== true) router.replace('/onboarding')
        }).catch(() => null)
      }
    } catch (error: any) {
      if (error.code === 'email_not_confirmed') {
        router.push('/auth/verify?email=' + encodeURIComponent(email))
        return
      }
      const message = humanizeAuthError(error.message)
      setError(message)
      toast.error(message)
    } finally {
      setIsLoading(false)
    }
  }

  if (authStatus === 'loading') {
    return (
      <main className="flex min-h-screen">
        <div className="flex flex-1 items-center justify-center bg-background">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
        </div>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen">
      <AuthLeftPanel />

      <div className="flex flex-1 items-center justify-center bg-background px-6 py-12 sm:px-10">
        <div className="w-full max-w-md motion-safe:animate-[panel-slide-in_0.45s_ease-out_both]">
          <div className="mb-8 flex flex-col gap-2 lg:hidden">
            <SpeakOETLogo height={28} variant="full" theme="dark" priority />
            <p className="text-sm text-muted-foreground">Practice OET Speaking with confidence</p>
          </div>

          <div className="flex w-full flex-col gap-6 sm:rounded-2xl sm:border sm:border-border sm:p-8 sm:shadow-[0_1px_2px_rgba(15,35,86,0.04),0_8px_24px_rgba(15,35,86,0.06)]">
            <div className="flex flex-col gap-1">
              <h2 className="text-2xl font-bold text-foreground text-balance">
                Welcome back
              </h2>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Sign in to continue your OET practice
              </p>
            </div>

            {error && (
              <div role="alert" className="motion-safe:animate-[message-in_0.25s_ease-out_both] rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
                {error}
              </div>
            )}

            <div className="flex flex-col gap-3">
              <button
                type="button"
                onClick={handleGoogleSignIn}
                disabled={googleLoading || microsoftLoading || isLoading}
                className="h-11 w-full rounded-xl border border-border bg-card text-sm font-medium text-foreground/80 shadow-sm transition-all duration-150 hover:bg-muted hover:shadow-md disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {googleLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <GoogleIcon />
                )}
                Continue with Google
              </button>

              <button
                type="button"
                onClick={handleMicrosoftSignIn}
                disabled={googleLoading || microsoftLoading || isLoading}
                className="h-11 w-full rounded-xl border border-border bg-card text-sm font-medium text-foreground/80 shadow-sm transition-all duration-150 hover:bg-muted hover:shadow-md disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {microsoftLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <MicrosoftIcon />
                )}
                Continue with Microsoft
              </button>
            </div>

            <div className="flex items-center gap-3" role="separator" aria-label="or">
              <div className="h-px flex-1 bg-border" />
              <span className="text-xs font-medium tracking-wide text-muted-foreground">OR</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="email" className="text-sm font-medium text-foreground">
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value)
                    if (fieldErrors.email) setFieldErrors((f) => ({ ...f, email: undefined }))
                  }}
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                  aria-invalid={!!fieldErrors.email}
                  aria-describedby={fieldErrors.email ? 'email-error' : undefined}
                  className={`h-11 w-full rounded-xl border bg-muted/60 px-3.5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all duration-150 focus:bg-card hover:border-border ${
                    fieldErrors.email
                      ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
                      : 'border-border focus:border-primary/40 focus:ring-2 focus:ring-primary/10'
                  }`}
                />
                {fieldErrors.email && (
                  <p id="email-error" role="alert" className="text-xs text-red-600">
                    {fieldErrors.email}
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="password" className="text-sm font-medium text-foreground">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value)
                      if (fieldErrors.password) setFieldErrors((f) => ({ ...f, password: undefined }))
                    }}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    required
                    aria-invalid={!!fieldErrors.password}
                    aria-describedby={fieldErrors.password ? 'password-error' : undefined}
                    className={`h-11 w-full rounded-xl border bg-muted/60 px-3.5 pr-11 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all duration-150 focus:bg-card hover:border-border ${
                      fieldErrors.password
                        ? 'border-red-300 focus:border-red-400 focus:ring-2 focus:ring-red-100'
                        : 'border-border focus:border-primary/40 focus:ring-2 focus:ring-primary/10'
                    }`}
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
                {fieldErrors.password && (
                  <p id="password-error" role="alert" className="text-xs text-red-600">
                    {fieldErrors.password}
                  </p>
                )}
              </div>

              <div className="flex justify-end">
                <Link
                  href="/auth/forgot-password"
                  className="text-xs font-medium text-emerald-600 transition-colors hover:text-emerald-700 focus-visible:outline-none focus-visible:underline"
                >
                  Forgot password?
                </Link>
              </div>

              <button
                type="submit"
                disabled={isLoading || googleLoading || microsoftLoading}
                className="h-11 w-full rounded-xl bg-gradient-to-b from-emerald-500 to-emerald-600 text-sm font-semibold text-white shadow-sm transition-all duration-150 hover:from-emerald-600 hover:to-emerald-700 hover:shadow-md active:scale-[0.99] disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    Signing in…
                  </>
                ) : (
                  'Sign In'
                )}
              </button>
            </form>

            <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5" aria-hidden="true">
                <rect x="3" y="11" width="18" height="10" rx="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              Your data is encrypted and never shared
            </p>

            <p className="text-center text-sm text-muted-foreground">
              Don&apos;t have an account?{' '}
              <Link
                href={returnTo ? '/auth/register?returnTo=' + encodeURIComponent(returnTo) : '/auth/register'}
                className="font-semibold text-foreground transition-colors hover:text-emerald-600 focus-visible:outline-none focus-visible:underline"
              >
                Get Started Free
              </Link>
            </p>
          </div>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            By signing in, you agree to our{' '}
            <Link href="/terms" className="underline hover:text-foreground focus-visible:outline-none focus-visible:underline">
              Terms
            </Link>{' '}
            and{' '}
            <Link href="/privacy" className="underline hover:text-foreground focus-visible:outline-none focus-visible:underline">
              Privacy Policy
            </Link>
          </p>
        </div>
      </div>
    </main>
  )
}
