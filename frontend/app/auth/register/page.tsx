'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase, signUp, signOut } from '@/lib/supabase'
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

export default function RegisterPage() {
  const router = useRouter()
  const [formData, setFormData] = useState({ name: '', email: '', password: '', confirmPassword: '' })
  const [isLoading, setIsLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [microsoftLoading, setMicrosoftLoading] = useState(false)
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

  const handleMicrosoftSignUp = async () => {
    setMicrosoftLoading(true)
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'azure',
        options: {
          redirectTo: window.location.origin + '/auth/callback',
          scopes: 'email',
        },
      })
      if (error) throw error
    } catch (error: any) {
      toast.error(error.message || 'Microsoft sign up failed')
      setMicrosoftLoading(false)
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
        // Registering while already signed in as someone else leaves that old
        // session in place — sign out so the login page's authenticated-user
        // redirect doesn't bounce back into the old account's dashboard.
        await signOut()
        toast.success('Registration successful! Check your email to confirm your account, then sign in.')
        setFormData({ name: '', email: '', password: '', confirmPassword: '' })
        setTimeout(() => router.push('/auth/login'), 2000)
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

      <div className="flex flex-1 items-center justify-center bg-background px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <SpeakOETLogo height={28} variant="full" theme="dark" priority />
          </div>

          <div className="flex w-full flex-col gap-6">
            <div className="flex flex-col gap-1">
              <h2 className="text-2xl font-bold text-foreground text-balance">
                Create your account
              </h2>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Join nurses already practicing with SpeakOET
              </p>
            </div>

            {error && (
              <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
                {error}
              </div>
            )}

            <div className="flex flex-col gap-3">
              <button
                type="button"
                onClick={handleGoogleSignUp}
                disabled={googleLoading || microsoftLoading || isLoading}
                className="h-11 w-full rounded-xl border border-border bg-card text-sm font-medium text-foreground/80 shadow-sm transition-all duration-150 hover:bg-muted hover:shadow-md disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {googleLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <GoogleIcon />
                )}
                Sign up with Google
              </button>

              <button
                type="button"
                onClick={handleMicrosoftSignUp}
                disabled={googleLoading || microsoftLoading || isLoading}
                className="h-11 w-full rounded-xl border border-border bg-card text-sm font-medium text-foreground/80 shadow-sm transition-all duration-150 hover:bg-muted hover:shadow-md disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {microsoftLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <MicrosoftIcon />
                )}
                Sign up with Microsoft
              </button>
            </div>

            <div className="flex items-center gap-3" role="separator" aria-label="or">
              <div className="h-px flex-1 bg-border" />
              <span className="text-xs font-medium text-muted-foreground">or</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="name" className="text-sm font-medium text-foreground">
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
                  className="h-11 w-full rounded-xl border border-border bg-muted/60 px-3.5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all duration-150 focus:border-primary/40 focus:bg-card focus:ring-2 focus:ring-primary/10 hover:border-border"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="email" className="text-sm font-medium text-foreground">
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
                  className="h-11 w-full rounded-xl border border-border bg-muted/60 px-3.5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all duration-150 focus:border-primary/40 focus:bg-card focus:ring-2 focus:ring-primary/10 hover:border-border"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="password" className="text-sm font-medium text-foreground">
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
                <p className="text-xs text-muted-foreground">Must be at least 8 characters</p>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="confirmPassword" className="text-sm font-medium text-foreground">
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
                  className="h-11 w-full rounded-xl border border-border bg-muted/60 px-3.5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all duration-150 focus:border-primary/40 focus:bg-card focus:ring-2 focus:ring-primary/10 hover:border-border"
                />
              </div>

              <p className="text-center text-xs leading-relaxed text-muted-foreground">
                By creating an account, you agree to our{' '}
                <Link href="/terms" className="font-medium text-muted-foreground underline hover:text-foreground">
                  Terms
                </Link>{' '}
                and{' '}
                <Link href="/privacy" className="font-medium text-muted-foreground underline hover:text-foreground">
                  Privacy Policy
                </Link>
                .
              </p>

              <button
                type="submit"
                disabled={isLoading || googleLoading || microsoftLoading}
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

            <p className="text-center text-sm text-muted-foreground">
              Already have an account?{' '}
              <Link
                href="/auth/login"
                className="font-semibold text-foreground transition-colors hover:text-emerald-600 focus-visible:outline-none focus-visible:underline"
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
