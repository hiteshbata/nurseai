'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import { trackEvent } from '@/lib/analytics'
import { trackMetaEvent } from '@/lib/meta-pixel'
import Link from 'next/link'

// A brand-new OAuth signup creates the auth.users row and signs the user in
// within the same request, so created_at and last_sign_in_at land within
// milliseconds of each other. A returning login leaves created_at fixed from
// whenever the account was first made while last_sign_in_at jumps to now —
// a gap of hours/days/months. No backend flag needed to tell them apart.
const NEW_SIGNUP_WINDOW_MS = 15_000

function isNewSignup(user: { created_at?: string; last_sign_in_at?: string } | undefined): boolean {
  if (!user?.created_at || !user?.last_sign_in_at) return false
  const created = new Date(user.created_at).getTime()
  const lastSignIn = new Date(user.last_sign_in_at).getTime()
  return Math.abs(lastSignIn - created) < NEW_SIGNUP_WINDOW_MS
}

export default function AuthCallbackPage() {
  const router = useRouter()
  const [status, setStatus] = useState<'loading' | 'error' | 'done'>('loading')

  useEffect(() => {
    let cancelled = false

    const onSession = async (session: any) => {
      if (!session || cancelled) return
      if (isNewSignup(session.user)) {
        trackEvent('signup_completed', { method: 'google' })
        trackMetaEvent('CompleteRegistration', { registration_method: 'oauth' }, { email: session.user.email })
      } else {
        trackEvent('login_completed', { method: 'oauth' })
        trackMetaEvent('UserLoggedIn', { method: 'oauth' }, { email: session.user.email })
      }
      try {
        const statusRes = await api.get('/onboarding/status')
        const onboardingComplete = statusRes.data?.onboarding_completed === true
        router.push(onboardingComplete ? '/dashboard' : '/onboarding')
      } catch {
        router.push('/dashboard')
      }
    }

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN' && session) {
        onSession(session)
      }
    })

    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        onSession(session)
      } else {
        setStatus('error')
      }
    })

    return () => {
      cancelled = true
      subscription?.unsubscribe()
    }
  }, [router])

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-card rounded-lg shadow-lg p-8 text-center">
        {status === 'loading' && (
          <>
            <div className="flex justify-center mb-4">
              <svg className="animate-spin h-10 w-10 text-primary" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">Signing you in...</h2>
            <p className="text-muted-foreground">Please wait while we complete your sign in.</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="text-4xl mb-4">❌</div>
            <h2 className="text-xl font-semibold text-foreground mb-2">Sign in failed</h2>
            <p className="text-muted-foreground mb-2">Could not complete sign in. If using Google OAuth, make sure:</p>
            <ul className="text-sm text-muted-foreground mb-4 list-disc text-left px-6 space-y-1">
              <li>Your Supabase project has <code className="bg-muted px-1 rounded">http://localhost:3000/auth/callback</code> in Redirect URLs (Authentication → Settings)</li>
              <li>Google provider is enabled in Supabase Auth providers</li>
            </ul>
            <p className="text-muted-foreground mb-6">Try signing in with email &amp; password instead.</p>
            <Link
              href="/auth/login"
              className="inline-block px-6 py-2.5 bg-primary text-primary-foreground rounded-lg font-semibold hover:opacity-90 transition"
            >
              Back to Sign In
            </Link>
          </>
        )}
      </div>
    </div>
  )
}
