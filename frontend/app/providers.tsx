'use client'

import { useEffect, useRef } from 'react'
import { usePathname } from 'next/navigation'
import { ThemeProvider } from 'next-themes'
import { Toaster } from 'react-hot-toast'
import { SessionProvider, useSupabaseSession } from '@/lib/supabase'
import { initAnalytics, identifyUser } from '@/lib/analytics'
import { initGA } from '@/lib/ga'
import { initClarity } from '@/lib/clarity'
import { initMetaPixel, trackMetaEvent, setMetaUserData } from '@/lib/meta-pixel'

// SessionProvider owns the app's one Supabase session subscription; every
// descendant (AppShell, Navbar, page components, ...) reads it via
// useSupabaseSession() instead of each opening its own subscription.
export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <ProvidersInner>{children}</ProvidersInner>
    </SessionProvider>
  )
}

function ProvidersInner({ children }: { children: React.ReactNode }) {
  const { session, status } = useSupabaseSession()
  const pathname = usePathname()

  useEffect(() => {
    // Sentry's beforeSend no-ops every event in development anyway, and its
    // deferred dynamic import races Turbopack's dev-mode HMR (the chunk gets
    // invalidated before it loads, throwing "module factory is not
    // available") — so skip initializing it outside production entirely.
    const initSentryDeferred = process.env.NODE_ENV === 'production'
      ? () => import('@/lib/sentry-client').then(m => m.initSentry())
      : () => {}

    const runDeferred = () => {
      initSentryDeferred()
      initAnalytics()
      initGA()
      initClarity()
      initMetaPixel()
    }

    const hasIdleCallback = typeof window !== 'undefined' && 'requestIdleCallback' in window
    const id = hasIdleCallback
      ? window.requestIdleCallback(runDeferred, { timeout: 2000 })
      : setTimeout(runDeferred, 2000)

    return () => {
      if (hasIdleCallback) window.cancelIdleCallback(id as number)
      else clearTimeout(id as number)
    }
  }, [])

  useEffect(() => {
    if (status === 'authenticated' && session?.user) {
      identifyUser(session.user.id, { email: session.user.email })
      if (session.user.email) setMetaUserData({ email: session.user.email })
    }
  }, [status, session])

  // PageView on first mount and every client-side route change -- Meta's
  // pixel doesn't hook the App Router's history API on its own like GA's
  // gtag/PostHog's autocapture do. The ref guards against React StrictMode's
  // dev-only double-invoke of this effect (same pathname, no real navigation
  // happened) firing the same PageView twice; a real route change always
  // changes pathname, so it's never suppressed.
  const lastPageViewPathnameRef = useRef<string | null>(null)
  useEffect(() => {
    if (lastPageViewPathnameRef.current === pathname) return
    lastPageViewPathnameRef.current = pathname
    trackMetaEvent('PageView')
  }, [pathname])

  return (
    // ponytail: dark mode disabled pending full redesign (audit found only
    // ~4% component coverage). forcedTheme keeps the .dark CSS vars and
    // next-themes wiring intact for later; it just stops them from ever
    // being applied, regardless of OS/system preference or stored choice.
    <ThemeProvider attribute="class" defaultTheme="light" forcedTheme="light">
      {children}
      <Toaster position="top-center" reverseOrder={false} />
    </ThemeProvider>
  )
}
