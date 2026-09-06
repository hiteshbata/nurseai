'use client'

import { useState, useEffect, useCallback, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { verifyInviteOtp } from '@/lib/supabase'
import { Loader2 } from 'lucide-react'
import { AuthLeftPanel } from '@/components/auth/auth-left-panel'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'
import { OtpInput } from '@/components/auth/OtpInput'
import { OTP_LENGTH } from '@/lib/otp'

// Numeric-code alternative to clicking the invite link in
// /auth/confirm?token_hash=... -- same GoTrue invite, entered as an
// OTP_LENGTH-digit code shown alongside the link in the "Invite user" email
// template ({{ .Token }}). Converges on the same
// /auth/reset-password?type=invite destination as the link flow once
// verifyOtp succeeds.

function InviteCodeForm() {
  const router = useRouter()
  const params = useSearchParams()

  const [email, setEmail] = useState(params.get('email') || '')
  const [code, setCode] = useState('')
  const [isVerifying, setIsVerifying] = useState(false)
  const [error, setError] = useState('')

  const submit = useCallback(async (token: string) => {
    if (!email.trim() || token.length !== OTP_LENGTH || isVerifying) return
    setIsVerifying(true)
    setError('')
    try {
      await verifyInviteOtp(email.trim(), token)
      router.push('/auth/reset-password?type=invite')
    } catch (err: any) {
      setError("That code isn't right or has expired. Ask your institution admin to resend the invite.")
      setCode('')
      setIsVerifying(false)
    }
  }, [email, isVerifying, router])

  useEffect(() => {
    if (code.length === OTP_LENGTH) submit(code)
  }, [code, submit])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-2xl font-bold text-foreground text-balance">Enter your invite code</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Enter your email and the {OTP_LENGTH}-digit code from your invitation email.
        </p>
      </div>

      {error && (
        <div role="alert" className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <label htmlFor="invite-email" className="text-sm font-medium text-foreground">
          Email
        </label>
        <input
          id="invite-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@institution.org"
          autoComplete="email"
          disabled={isVerifying}
          className="h-11 w-full rounded-xl border border-border bg-muted/60 px-3.5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-all duration-150 focus:border-primary/40 focus:bg-card focus:ring-2 focus:ring-primary/10 hover:border-border disabled:opacity-60"
        />
      </div>

      <OtpInput value={code} onChange={setCode} disabled={isVerifying || !email.trim()} error={!!error} length={OTP_LENGTH} />

      {isVerifying && (
        <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Verifying…
        </div>
      )}
    </div>
  )
}

export default function InviteCodePage() {
  return (
    <main className="flex min-h-screen">
      <AuthLeftPanel />
      <div className="flex flex-1 items-center justify-center bg-background px-6 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <SpeakOETLogo height={28} variant="full" theme="dark" priority />
          </div>
          <Suspense fallback={<div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-foreground" /></div>}>
            <InviteCodeForm />
          </Suspense>
        </div>
      </div>
    </main>
  )
}
