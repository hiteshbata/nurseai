import { createBrowserClient } from '@supabase/ssr'
import type { SupabaseClient, Session } from '@supabase/supabase-js'
import { useState, useEffect } from 'react'

let _supabase: SupabaseClient | null = null

// Set while an intentional signOut() is in flight. useSupabaseSession ignores
// the SIGNED_OUT event during this window so mounted protected pages don't
// race their own "unauthenticated -> /auth/login" redirect against the
// caller's post-signOut navigation (e.g. hard nav to '/').
let loggingOut = false

function getClient(): SupabaseClient | null {
  if (_supabase) return _supabase
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!url || !key) return null
  _supabase = createBrowserClient(url, key, {
    cookieOptions: {
      secure: process.env.NODE_ENV === 'production',
    },
  })
  return _supabase
}

export const supabase = new Proxy({} as SupabaseClient, {
  get(_target, prop) {
    const client = getClient()
    if (!client) return undefined
    return (client as any)[prop]
  },
})

export function useSupabaseSession() {
  const [session, setSession] = useState<Session | null>(null)
  const [status, setStatus] = useState<'loading' | 'authenticated' | 'unauthenticated'>('loading')

  useEffect(() => {
    let cancelled = false

    // getSession() (local storage read) and onAuthStateChange's INITIAL_SESSION
    // event both fire on mount with a *new* Session object even when the user
    // hasn't changed. Keep the same object reference when the token is
    // unchanged so consumers keying a useEffect off `session` don't double-fetch.
    const applySession = (s: Session | null) => {
      if (cancelled) return
      setSession(prev => (prev?.access_token === s?.access_token ? prev : s))
      setStatus(s ? 'authenticated' : 'unauthenticated')
    }

    // Use getSession() which reads from local storage — no network round-trip.
    // This is sufficient for routine auth checks on page load.
    getClient()?.auth.getSession().then(({ data: { session: s } }) => applySession(s))

    const { data: { subscription } } = getClient()?.auth.onAuthStateChange((_event, s) => {
      if (loggingOut) return
      applySession(s)
    }) ?? { data: { subscription: { unsubscribe: () => {} } } }

    return () => {
      cancelled = true
      subscription?.unsubscribe()
    }
  }, [])

  return { session, status }
}

export async function getCurrentSession() {
  const client = getClient()
  if (!client) return null
  const { data: { session } } = await client.auth.getSession()
  return session
}

export async function signIn(email: string, password: string) {
  const client = getClient()
  if (!client) throw new Error('Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.')
  const { data, error } = await client.auth.signInWithPassword({ email, password })
  if (error) throw error
  return data
}

// Supabase/GoTrue error messages are written for developers, not nurses about
// to sign in. Translate the common ones into plain, reassuring copy.
export function humanizeAuthError(message: string | undefined): string {
  const msg = (message || '').toLowerCase()
  if (msg.includes('invalid login credentials')) {
    return "That email and password don't match. Try again or reset your password."
  }
  if (msg.includes('email not confirmed')) {
    return 'Please confirm your email before signing in — check your inbox for the confirmation link.'
  }
  if (msg.includes('missing email or phone') || msg.includes('missing password')) {
    return 'Enter your email and password to continue.'
  }
  if (msg.includes('too many requests') || msg.includes('rate limit')) {
    return 'Too many attempts. Please wait a minute and try again.'
  }
  if (msg.includes('network') || msg.includes('failed to fetch')) {
    return "Can't reach the server. Check your connection and try again."
  }
  return message || 'Something went wrong. Please try again.'
}

export async function signUp(email: string, password: string, name: string) {
  const client = getClient()
  if (!client) throw new Error('Supabase is not configured.')
  const { data, error } = await client.auth.signUp({
    email,
    password,
    options: { data: { name } },
  })
  if (error) throw error
  return data
}

export async function signInAnonymously() {
  const client = getClient()
  if (!client) throw new Error('Supabase is not configured.')
  const { data, error } = await client.auth.signInAnonymously()
  if (error) throw error
  return data
}

// Converts the current anonymous session into a real account, same user_id,
// so everything recorded while anonymous (e.g. a free mock test) carries
// over. Whether this completes immediately or needs an email confirmation
// click first is a Supabase project setting, not something the caller
// controls — check session.user.is_anonymous afterward to tell which happened.
export async function linkAnonymousAccount(email: string, password: string, name: string) {
  const client = getClient()
  if (!client) throw new Error('Supabase is not configured.')
  const { data, error } = await client.auth.updateUser({ email, password, data: { name } })
  if (error) throw error
  return data
}

export async function requestPasswordReset(email: string) {
  const client = getClient()
  if (!client) throw new Error('Supabase is not configured.')
  const { error } = await client.auth.resetPasswordForEmail(email, {
    redirectTo: `${window.location.origin}/auth/reset-password`,
  })
  if (error) throw error
}

export async function updatePassword(newPassword: string) {
  const client = getClient()
  if (!client) throw new Error('Supabase is not configured.')
  const { error } = await client.auth.updateUser({ password: newPassword })
  if (error) throw error
}

// Single logout path for the whole app -- every caller (menu "Sign Out"
// buttons, the api.ts 401 interceptor, post-password-reset, etc.) goes
// through this instead of calling supabase.auth.signOut() directly. That
// matters because the `loggingOut` flag above only suppresses the SIGNED_OUT
// event for callers that go through here; a caller that bypasses this and
// calls the raw client method fires SIGNED_OUT unsuppressed, which makes
// every mounted page's own "unauthenticated -> redirect" effect fire at the
// same time as that caller's redirect -- two navigations racing each other.
export async function signOut(redirectTo?: string) {
  const client = getClient()
  if (client) {
    loggingOut = true
    // Captured before signOut() clears local storage -- the interceptor in
    // api.ts can no longer find a token to attach once the session is gone,
    // so it's passed explicitly to /auth/logout below.
    const { data: { session } } = await client.auth.getSession()
    const accessToken = session?.access_token
    try {
      await client.auth.signOut()
    } catch (e) {
      console.error('[supabase] signOut error (non-fatal):', e)
    } finally {
      loggingOut = false
    }
    if (accessToken) {
      try {
        // Dynamic import: api.ts imports `signOut` from this file, so a
        // static import here would be circular.
        const { default: api } = await import('@/lib/api')
        await api.post('/auth/logout', {}, { headers: { Authorization: `Bearer ${accessToken}` } })
      } catch (e) {
        console.error('[supabase] server-side logout revoke failed (non-fatal):', e)
      }
    }
  }
  // Callers that need to stay put (e.g. showing a toast before a delayed
  // router.push elsewhere) simply omit redirectTo -- this only navigates
  // when asked to, so it doesn't change behavior for those call sites.
  if (redirectTo && typeof window !== 'undefined') {
    window.location.href = redirectTo
  }
}