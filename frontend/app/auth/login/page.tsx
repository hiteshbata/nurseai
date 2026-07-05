'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase, signIn, useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Loader2, Eye, EyeOff } from 'lucide-react'
import { AuthLeftPanel } from '@/components/auth/auth-left-panel'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'

// Only allow same-origin relative paths (e.g. "/practice/speaking") as a
// redirect target — never an absolute URL or protocol-relative "//host" path,
// which would let a crafted returnTo param send the user off-site after login.
function getSafeReturnTo(): string | null {
  if (typeof window === 'undefined') return null
  const returnTo = new URLSearchParams(window.location.search).get('returnTo')
  if (!returnTo || !returnTo.startsWith('/') || returnTo.startsWith('//')) return null
  return returnTo
}

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

export default function LoginPage() {
  const router = useRouter()
  const { session, status: authStatus } = useSupabaseSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (authStatus === 'authenticated') {
      router.push(getSafeReturnTo() || '/dashboard')
    }
  }, [authStatus, router])

  const handleGoogleSignIn = async () => {
    setGoogleLoading(true)
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: window.location.origin + '/auth/callback',
        },
      })
      if (error) throw error
    } catch (error: any) {
      toast.error(error.message || 'Google sign in failed')
      setGoogleLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')
    try {
      await signIn(email, password)
      toast.success('Logged in successfully!')
      const returnTo = getSafeReturnTo()
      if (returnTo) {
        router.push(returnTo)
        return
      }
      const statusRes = await api.get('/onboarding/status')
      const onboardingComplete = statusRes.data?.onboarding_completed === true
      router.push(onboardingComplete ? '/dashboard' : '/onboarding')
    } catch (error: any) {
      setError(error.message || 'Login failed')
      toast.error(error.message || 'Login failed')
    } finally {
      setIsLoading(false)
    }
  }

  if (authStatus === 'loading') {
    return (
      <main className="flex min-h-screen">
        <div className="flex flex-1 items-center justify-center bg-white">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#0F2356]" />
        </div>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen">
      <AuthLeftPanel />

      <div className="flex flex-1 items-center justify-center bg-white px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <SpeakOETLogo height={28} variant="full" theme="dark" />
          </div>

          <div className="flex w-full flex-col gap-6">
            <div className="flex flex-col gap-1">
              <h2 className="text-2xl font-bold text-[#0F2356] text-balance">
                Welcome back
              </h2>
              <p className="text-sm leading-relaxed text-gray-500">
                Sign in to continue your OET practice
              </p>
            </div>

            {error && (
              <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
                {error}
              </div>
            )}

            <button
              type="button"
              onClick={handleGoogleSignIn}
              disabled={googleLoading || isLoading}
              className="h-11 w-full rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 shadow-sm transition-all duration-150 hover:bg-gray-50 hover:shadow-md flex items-center justify-center gap-2"
            >
              {googleLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <GoogleIcon />
              )}
              Continue with Google
            </button>

            <div className="flex items-center gap-3" role="separator" aria-label="or">
              <div className="h-px flex-1 bg-gray-200" />
              <span className="text-xs font-medium text-gray-400">or</span>
              <div className="h-px flex-1 bg-gray-200" />
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="email" className="text-sm font-medium text-[#0F2356]">
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                  className="h-11 w-full rounded-xl border border-gray-200 bg-gray-50/60 px-3.5 text-sm text-[#0F2356] placeholder:text-gray-400 outline-none transition-all duration-150 focus:border-[#0F2356]/40 focus:bg-white focus:ring-3 focus:ring-[#0F2356]/8 hover:border-gray-300"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="password" className="text-sm font-medium text-[#0F2356]">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    required
                    className="h-11 w-full rounded-xl border border-gray-200 bg-gray-50/60 px-3.5 pr-11 text-sm text-[#0F2356] placeholder:text-gray-400 outline-none transition-all duration-150 focus:border-[#0F2356]/40 focus:bg-white focus:ring-3 focus:ring-[#0F2356]/8 hover:border-gray-300"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0F2356]/40 rounded"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
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
                disabled={isLoading || googleLoading}
                className="h-11 w-full rounded-xl bg-emerald-500 text-sm font-semibold text-white shadow-sm transition-all duration-150 hover:bg-emerald-600 hover:shadow-md active:scale-[0.99] disabled:opacity-60 flex items-center justify-center gap-2"
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

            <p className="text-center text-sm text-gray-500">
              Don&apos;t have an account?{' '}
              <Link
                href="/auth/register"
                className="font-semibold text-[#0F2356] transition-colors hover:text-emerald-600 focus-visible:outline-none focus-visible:underline"
              >
                Get Started Free
              </Link>
            </p>
          </div>
        </div>
      </div>
    </main>
  )
}
