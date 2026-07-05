'use client'

import { useEffect } from 'react'
import { Toaster } from 'react-hot-toast'
import { useSupabaseSession } from '@/lib/supabase'
import { initAnalytics, identifyUser } from '@/lib/analytics'

export default function Providers({ children }: { children: React.ReactNode }) {
  const { session, status } = useSupabaseSession()

  useEffect(() => {
    const id = requestIdleCallback ? requestIdleCallback(() => {
      import('../sentry.client.config').then(m => m.initSentry())
      initAnalytics()
    }, { timeout: 2000 }) : setTimeout(() => {
      import('../sentry.client.config').then(m => m.initSentry())
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
