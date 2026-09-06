'use client'

import { useState, useEffect, useCallback, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { verifySignupOtp, resendSignupOtp } from '@/lib/supabase'
import { sanitizeNext, maskEmail } from '@/lib/auth-redirect'
import { trackEvent } from '@/lib/analytics'
import toast from 'react-hot-toast'
import { Loader2, Check } from 'lucide-react'
import { AuthLeftPanel } from '@/components/auth/auth-left-panel'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'
import { OtpInput } from '@/components/auth/OtpInput'
import { OTP_LENGTH } from '@/lib/otp'

const RESEND_COOLDOWN_SECONDS = 30

function VerifyForm() {
  const router = useRouter()
  const params = useSearchParams()
  const email = params.get('email') || ''
  const returnTo = sanitizeNext(params.get('returnTo'), typeof window !== 'undefined' ? window.location.origin : '')

  const [code, setCode] = useState('')
  const [isVerifying, setIsVerifying] = useState(false)
  const [isResending, setIsResending] = useState(false)
  const [error, setError] = useState('')
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SECONDS)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    if (cooldown <= 0) return
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => clearTimeout(t)
  }, [cooldown])

  const submit = useCallback(async (token: string) => {
    if (!email || token.length !== OTP_LENGTH || isVerifying) return
    setIsVerifying(true)
    setError('')
    try {
      await verifySignupOtp(email, token)
      trackEvent('signup_verified', { method: 'otp' })
      setSuccess(true)
      setTimeout(() => router.push(returnTo || '/onboarding'), 1200)
    } catch (err: any) {
      setError("That code isn't right or has expired. Request a new one below.")
      setCode('')
    } finally {
      setIsVerifying(false)
    }
  }, [email, isVerifying, returnTo, router])

  useEffect(() => {
    if (code.length === OTP_LENGTH) submit(code)
  }, [code, submit])

  const handleResend = async () => {
    if (cooldown > 0 || isResending || !email) return
    setIsResending(true)
    try {
      await resendSignupOtp(email)
    } catch (err: any) {
      // Only a genuine rate limit is safe to surface -- it paces requests,
      // it doesn't reveal whether the account exists. Everything else is
      // swallowed the same way forgot-password swallows its errors, so a
      // nonexistent/already-confirmed email can't be distinguished by response.
      if (err?.status === 429 || /rate limit/i.test(err?.message || '')) {
        toast.error('Please wait before requesting another code.')
        setIsResending(false)
        return
      }
      console.error('[auth/verify] resend error', err)
    }
    toast.success('Code sent — check your inbox.')
    setCooldown(RESEND_COOLDOWN_SECONDS)
    setIsResending(false)
  }

  if (!email) {
    return (
      <div className="flex flex-col gap-4 text-center">
        <h2 className="text-2xl font-bold text-foreground">Missing email</h2>
        <p className="text-sm text-muted-foreground">
          We couldn&apos;t tell which account to verify. Please sign up again.
        </p>
        <Link
          href="/auth/register"
          className="h-11 w-full rounded-xl bg-emerald-500 text-sm font-semibold text-white shadow-sm transition-all duration-150 hover:bg-emerald-600 hover:shadow-md flex items-center justify-center"
        >
          Back to sign up
        </Link>
      </div>
    )
  }

  if (success) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100">
          <Check className="h-6 w-6 text-emerald-600" aria-hidden="true" />
        </div>
        <h2 className="text-xl font-bold text-foreground">Email verified</h2>
        <p className="text-sm text-muted-foreground">Redirecting you…</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-2xl font-bold text-foreground text-balance">Check your email</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Enter the {OTP_LENGTH}-digit code we sent to <span className="font-medium text-foreground">{maskEmail(email)}</span>
        </p>
      </div>

      {error && (
        <div role="alert" className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <OtpInput value={code} onChange={setCode} disabled={isVerifying} error={!!error} autoFocus length={OTP_LENGTH} />

      {isVerifying && (
        <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Verifying…
        </div>
      )}

      <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
        <button
          type="button"
          onClick={handleResend}
          disabled={cooldown > 0 || isResending}
          className="font-semibold text-foreground transition-colors hover:text-emerald-600 focus-visible:outline-none focus-visible:underline disabled:opacity-50 disabled:hover:text-foreground"
        >
          {isResending ? 'Sending…' : cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
        </button>
        <Link
          href="/auth/register"
          className="transition-colors hover:text-foreground focus-visible:outline-none focus-visible:underline"
        >
          Entered the wrong email? Go back
        </Link>
      </div>
    </div>
  )
}

export default function VerifyPage() {
  return (
    <main className="flex min-h-screen">
      <AuthLeftPanel />
      <div className="flex flex-1 items-center justify-center bg-background px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <SpeakOETLogo height={28} variant="full" theme="dark" priority />
          </div>
          <Suspense fallback={<div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-foreground" /></div>}>
            <VerifyForm />
          </Suspense>
        </div>
      </div>
    </main>
  )
}
