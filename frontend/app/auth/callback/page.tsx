'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import api from '@/lib/api'
import Link from 'next/link'

export default function AuthCallbackPage() {
  const router = useRouter()
  const [status, setStatus] = useState<'loading' | 'error' | 'done'>('loading')

  useEffect(() => {
    let cancelled = false

    const onSession = async (session: any) => {
      if (!session || cancelled) return
      localStorage.setItem('authToken', session.access_token)
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
        // Check URL hash directly as fallback
        const hashParams = new URLSearchParams(window.location.hash.replace('#', '?'))
        const hashToken = hashParams.get('access_token')
        if (hashToken) {
          supabase.auth.setSession({
            access_token: hashToken,
            refresh_token: hashParams.get('refresh_token') || '',
          }).then(({ data: { session: hashSession } }) => {
            if (hashSession) onSession(hashSession)
            else setStatus('error')
          })
        } else {
          setStatus('error')
        }
      }
    })

    return () => {
      cancelled = true
      subscription?.unsubscribe()
    }
  }, [router])

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow-lg p-8 text-center">
        {status === 'loading' && (
          <>
            <div className="flex justify-center mb-4">
              <svg className="animate-spin h-10 w-10 text-blue-600" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Signing you in...</h2>
            <p className="text-gray-500">Please wait while we complete your sign in.</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="text-4xl mb-4">❌</div>
            <h2 className="text-xl font-semibold text-gray-800 mb-2">Sign in failed</h2>
            <p className="text-gray-500 mb-2">Could not complete sign in. If using Google OAuth, make sure:</p>
            <ul className="text-sm text-gray-500 mb-4 list-disc text-left px-6 space-y-1">
              <li>Your Supabase project has <code className="bg-gray-100 px-1 rounded">http://localhost:3000/auth/callback</code> in Redirect URLs (Authentication → Settings)</li>
              <li>Google provider is enabled in Supabase Auth providers</li>
            </ul>
            <p className="text-gray-500 mb-6">Try signing in with email &amp; password instead.</p>
            <Link
              href="/auth/login"
              className="inline-block px-6 py-2.5 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition"
            >
              Back to Sign In
            </Link>
          </>
        )}
      </div>
    </div>
  )
}
