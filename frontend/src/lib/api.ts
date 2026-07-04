import axios, { AxiosInstance, AxiosError } from 'axios'
import * as Sentry from '@sentry/nextjs'
import { supabase } from '@/lib/supabase'

const api: AxiosInstance = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
})

let cachedToken: string | null = null
let cachedTokenExpiry: number | null = null

const REFRESH_BUFFER_MS = 60000

api.interceptors.request.use(async (config) => {
  if (typeof window !== 'undefined') {
    if (cachedToken && cachedTokenExpiry && Date.now() < cachedTokenExpiry - REFRESH_BUFFER_MS) {
      config.headers.Authorization = `Bearer ${cachedToken}`
      return config
    }
    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token
    if (token) {
      cachedToken = token
      cachedTokenExpiry = session.expires_at ? session.expires_at * 1000 : null
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  return config
})

if (typeof window !== 'undefined') {
  supabase.auth.onAuthStateChange((event) => {
    if (event === 'SIGNED_OUT' || event === 'SIGNED_IN') {
      cachedToken = null
      cachedTokenExpiry = null
    }
  })
}

// Handle errors
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && error.config?.url) {
      const requestUrl: string = error.config.url
      const isPublicPath = ['/plans/'].some((p) => requestUrl.startsWith(p))
      if (!isPublicPath) {
        if (typeof window !== 'undefined') {
          supabase.auth.signOut()
          window.location.href = '/auth/login'
        }
      }
    }

    Sentry.captureException(error, {
      tags: {
        api_method: error.config?.method?.toUpperCase(),
        api_url: error.config?.url,
        status_code: error.response?.status?.toString() || '0',
      },
      extra: {
        request_data: error.config?.data,
        response_data: error.response?.data,
      },
    })

    return Promise.reject(error)
  }
)

export interface Plan {
  id: string
  name: string
  price: number
  period: string
  description: string
  features: string[]
  cta: string
  highlight: boolean
  disabled: boolean
  badge?: string
  profile_plan: string
  sessions_limit: number
}

let plansPromise: Promise<Plan[]> | null = null

export async function getPlans(): Promise<Plan[]> {
  if (!plansPromise) {
    plansPromise = api.get('/plans/').then((res) => res.data.plans)
      .catch((err) => {
        plansPromise = null
        throw err
      })
  }
  return plansPromise
}

export default api
