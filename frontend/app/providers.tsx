'use client'

import { useEffect } from 'react'
import { Toaster } from 'react-hot-toast'
import { useSupabaseSession } from '@/lib/supabase'
import { initAnalytics, identifyUser } from '@/lib/analytics'

export default function Providers({ children }: { children: React.ReactNode }) {
  const { session, status } = useSupabaseSession()

  useEffect(() => {
    // Sentry's beforeSend no-ops every event in development anyway, and its
    // deferred dynamic import races Turbopack's dev-mode HMR (the chunk gets
    // invalidated before it loads, throwing "module factory is not
    // available") — so skip initializing it outside production entirely.
    const initSentryDeferred = process.env.NODE_ENV === 'production'
      ? () => import('@/lib/sentry-client').then(m => m.initSentry())
      : () => {}

    const id = requestIdleCallback ? requestIdleCallback(() => {
      initSentryDeferred()
      initAnalytics()
    }, { timeout: 2000 }) : setTimeout(() => {
      initSentryDeferred()
      initAnalytics()
    }, 2000)

    return () => {
      if (requestIdleCallback) cancelIdleCallback(id as number)
      else clearTimeout(id as number)
    }
  }, [])

  useEffect(() => {
    if (status === 'authenticated' && session?.user) {
      identifyUser(session.user.id, { email: session.user.email })
    }
  }, [status, session])

  return (
    <>
      {children}
      <Toaster position="top-center" reverseOrder={false} />
    </>
  )
}
