import { createClient, SupabaseClient, Session } from '@supabase/supabase-js'
import { useState, useEffect } from 'react'

let _supabase: SupabaseClient | null = null

function getClient(): SupabaseClient | null {
  if (_supabase) return _supabase
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!url || !key) return null
  _supabase = createClient(url, key)
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
    getClient()?.auth.getSession().then(({ data: { session: s } }) => {
      setSession(s)
      setStatus(s ? 'authenticated' : 'unauthenticated')
    })
    const { data: { subscription } } = getClient()?.auth.onAuthStateChange((_event, s) => {
      setSession(s)
      setStatus(s ? 'authenticated' : 'unauthenticated')
    }) ?? { data: { subscription: { unsubscribe: () => {} } } }
    return () => subscription?.unsubscribe()
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
  if (data.session?.access_token) {
    localStorage.setItem('authToken', data.session.access_token)
  }
  return data
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

export async function signOut() {
  localStorage.removeItem('authToken')
  const client = getClient()
  if (client) await client.auth.signOut()
}