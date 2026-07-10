'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase, signUp } from '@/lib/supabase'
import { trackEvent } from '@/lib/analytics'
import toast from 'react-hot-toast'
import { Loader2, Eye, EyeOff } from 'lucide-react'
import { AuthLeftPanel } from '@/components/auth/auth-left-panel'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'

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

export default function RegisterPage() {
  const router = useRouter()
  const [formData, setFormData] = useState({ name: '', email: '', password: '', confirmPassword: '' })
  const [isLoading, setIsLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  const handleGoogleSignUp = async () => {
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
      toast.error(error.message || 'Google sign up failed')
      setGoogleLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (formData.password !== formData.confirmPassword) { toast.error('Passwords do not match'); return }
    if (formData.password.length < 8) { toast.error('Password must be at least 8 characters'); return }
    setIsLoading(true)
    setError('')
    try {
      const data = await signUp(formData.email, formData.password, formData.name)
      trackEvent('signup_completed', { method: 'email' })
      if (data.session) {
        toast.success('Registration successful! Redirecting to setup...')
        setTimeout(() => router.push('/onboarding'), 2000)
      } else {
        toast.success('Registration successful! Check your email to confirm your account, then sign in.')
      }
    } catch (error: any) {
      setError(error.message || 'Registration failed')
      toast.error(error.message || 'Registration failed')
    } finally {
      setIsLoading(false)
    }
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
                Create your account
              </h2>
              <p className="text-sm leading-relaxed text-gray-500">
                Join nurses already practicing with SpeakOET
              </p>
            </div>

            {error && (
              <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
                {error}
              </div>
            )}

            <button
              type="button"
              onClick={handleGoogleSignUp}
              disabled={googleLoading || isLoading}
              className="h-11 w-full rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 shadow-sm transition-all duration-150 hover:bg-gray-50 hover:shadow-md flex items-center justify-center gap-2"
            >
              {googleLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <GoogleIcon />
              )}
              Sign up with Google
            </button>

            <div className="flex items-center gap-3" role="separator" aria-label="or">
              <div className="h-px flex-1 bg-gray-200" />
              <span className="text-xs font-medium text-gray-400">or</span>
              <div className="h-px flex-1 bg-gray-200" />
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="name" className="text-sm font-medium text-[#0F2356]">
                  Full name
                </label>
                <input
                  id="name"
                  type="text"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  placeholder="Your full name"
                  required
                  className="h-11 w-full rounded-xl border border-gray-200 bg-gray-50/60 px-3.5 text-sm text-[#0F2356] placeholder:text-gray-400 outline-none transition-all duration-150 focus:border-[#0F2356]/40 focus:bg-white focus:ring-3 focus:ring-[#0F2356]/8 hover:border-gray-300"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="email" className="text-sm font-medium text-[#0F2356]">
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
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
                    name="password"
                    value={formData.password}
                    onChange={handleChange}
                    placeholder="Create a password"
                    autoComplete="new-password"
                    required
                    className="h-11 w-full rounded-xl border border-gray-200 bg-gray-50/60 px-3.5 pr-11 text-sm text-[#0F2356] placeholder:text-gray-400 outline-none transition-all duration-150 focus:border-[#0F2356]/40 focus:bg-white focus:ring-3 focus:ring-[#0F2356]/8 hover:border-gray-300"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-0 top-0 h-11 w-11 flex items-center justify-center text-gray-400 transition-colors hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0F2356]/40 rounded-xl"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="text-xs text-gray-400">Must be at least 8 characters</p>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="confirmPassword" className="text-sm font-medium text-[#0F2356]">
                  Confirm password
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  name="confirmPassword"
                  value={formData.confirmPassword}
                  onChange={handleChange}
                  placeholder="Confirm your password"
                  autoComplete="new-password"
                  required
                  className="h-11 w-full rounded-xl border border-gray-200 bg-gray-50/60 px-3.5 text-sm text-[#0F2356] placeholder:text-gray-400 outline-none transition-all duration-150 focus:border-[#0F2356]/40 focus:bg-white focus:ring-3 focus:ring-[#0F2356]/8 hover:border-gray-300"
                />
              </div>

              <p className="text-center text-xs leading-relaxed text-gray-400">
                By creating an account, you agree to our{' '}
                <Link href="/terms" className="font-medium text-gray-500 underline hover:text-[#0F2356]">
                  Terms
                </Link>{' '}
                and{' '}
                <Link href="/privacy" className="font-medium text-gray-500 underline hover:text-[#0F2356]">
                  Privacy Policy
                </Link>
                .
              </p>

              <button
                type="submit"
                disabled={isLoading || googleLoading}
                className="h-11 w-full rounded-xl bg-emerald-500 text-sm font-semibold text-white shadow-sm transition-all duration-150 hover:bg-emerald-600 hover:shadow-md active:scale-[0.99] disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    Creating account…
                  </>
                ) : (
                  'Create Account'
                )}
              </button>
            </form>

            <p className="text-center text-sm text-gray-500">
              Already have an account?{' '}
              <Link
                href="/auth/login"
                className="font-semibold text-[#0F2356] transition-colors hover:text-emerald-600 focus-visible:outline-none focus-visible:underline"
              >
                Sign In
              </Link>
            </p>
          </div>
        </div>
      </div>
    </main>
  )
}
