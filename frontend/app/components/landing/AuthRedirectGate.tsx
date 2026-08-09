'use client'

import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import api from '@/lib/api'

// Landing page ('/') is server-rendered for SEO/performance, but the redirect
// decision (anonymous -> free mock test, authenticated -> onboarding/dashboard)
// depends on client-side session state. This wraps the landing sections as
// `children` so they stay server components; only this gate is client-side.
// Middleware already redirects non-anonymous authenticated users away from
// '/' before this ever mounts (see middleware.ts) -- this is the fallback
// layer for cases middleware doesn't catch (e.g. anonymous sessions, which
// middleware intentionally lets through to '/').
export function AuthRedirectGate({ children }: { children: React.ReactNode }) {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [onboardingChecked, setOnboardingChecked] = useState(false)

  useEffect(() => {
    if (status === 'authenticated' && session?.user?.is_anonymous) {
      router.push('/tools/oet-mock-test-free')
      return
    }
    if (status === 'authenticated' && !session?.user?.is_anonymous && !onboardingChecked) {
      api.get('/onboarding/status').then((res) => {
        const complete = res.data?.onboarding_completed === true
        router.push(complete ? '/dashboard' : '/onboarding')
      }).catch(() => {
        router.push('/dashboard')
      }).finally(() => {
        setOnboardingChecked(true)
      })
    }
  }, [status, session, onboardingChecked, router])

  if (status === 'authenticated') {
    return null
  }

  return <>{children}</>
}
