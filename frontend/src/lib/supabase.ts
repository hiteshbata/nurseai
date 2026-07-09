import { createBrowserClient } from '@supabase/ssr'
import type { SupabaseClient, Session } from '@supabase/supabase-js'
import { useState, useEffect } from 'react'

let _supabase: SupabaseClient | null = null

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

    // Use getSession() which reads from local storage — no network round-trip.
    // This is sufficient for routine auth checks on page load.
    getClient()?.auth.getSession().then(({ data: { session: s } }) => {
      if (cancelled) return
      setSession(s)
      setStatus(s ? 'authenticated' : 'unauthenticated')
    })

    const { data: { subscription } } = getClient()?.auth.onAuthStateChange((_event, s) => {
      if (!cancelled) {
        setSession(s)
        setStatus(s ? 'authenticated' : 'unauthenticated')
      }
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

export async function signOut() {
  const client = getClient()
  if (client) {
    try {
      await client.auth.signOut()
    } catch (e) {
      console.error('[supabase] signOut error (non-fatal):', e)
    }
  }
}