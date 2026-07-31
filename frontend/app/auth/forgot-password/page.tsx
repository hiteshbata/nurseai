'use client'

import { useState } from 'react'
import Link from 'next/link'
import { requestPasswordReset } from '@/lib/supabase'
import { Loader2 } from 'lucide-react'
import { AuthLeftPanel } from '@/components/auth/auth-left-panel'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setIsLoading(true)
    try {
      await requestPasswordReset(email)
    } catch (error) {
      // Never surface this to the user -- doing so would let an attacker
      // distinguish "email exists" from "email doesn't exist" (account
      // enumeration). Log for diagnostics only.
      console.error('[forgot-password]', error)
    } finally {
      setIsLoading(false)
      setSubmitted(true)
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
            {submitted ? (
              <>
                <div className="flex flex-col gap-1">
                  <h2 className="text-2xl font-bold text-foreground text-balance">
                    Check your email
                  </h2>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    If an account exists for <span className="font-medium text-foreground">{email}</span>,
                    we&apos;ve sent a link to reset your password. The link expires soon, so use it shortly.
                  </p>
                </div>

                <Link
                  href="/auth/login"
                  className="text-center text-sm font-semibold text-foreground transition-colors hover:text-emerald-600 focus-visible:outline-none focus-visible:underline"
                >
                  Back to sign in
                </Link>
              </>
            ) : (
              <>
                <div className="flex flex-col gap-1">
                  <h2 className="text-2xl font-bold text-foreground text-balance">
                    Forgot your password?
                  </h2>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    Enter your email and we&apos;ll send you a link to reset it.
                  </p>
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
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      autoComplete="email"
                      required
                      className="h-11 w-full rounded-xl border border-border bg-muted/60 px-3.5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all duration-150 focus:border-primary/40 focus:bg-card focus:ring-2 focus:ring-primary/10 hover:border-border"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={isLoading}
                    className="h-11 w-full rounded-xl bg-emerald-500 text-sm font-semibold text-white shadow-sm transition-all duration-150 hover:bg-emerald-600 hover:shadow-md active:scale-[0.99] disabled:opacity-60 flex items-center justify-center gap-2"
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                        Sending link…
                      </>
                    ) : (
                      'Send reset link'
                    )}
                  </button>
                </form>

                <p className="text-center text-sm text-muted-foreground">
                  Remembered your password?{' '}
                  <Link
                    href="/auth/login"
                    className="font-semibold text-foreground transition-colors hover:text-emerald-600 focus-visible:outline-none focus-visible:underline"
                  >
                    Sign in
                  </Link>
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </main>
  )
}
