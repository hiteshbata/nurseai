import axios, { AxiosInstance, AxiosError, AxiosRequestConfig, AxiosResponse } from 'axios'
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

// Describes a request/response payload's shape (field names, lengths) for
// error-report debugging without ever including the actual values -- this
// endpoint carries things like payment amounts, letter/conversation content,
// and profile fields, none of which should land in Sentry as a side effect
// of ordinary error reporting.
function describePayload(data: unknown): string | undefined {
  if (data === undefined || data === null) return undefined
  if (typeof data === 'string') {
    try {
      return describePayload(JSON.parse(data))
    } catch {
      return `string(${data.length} chars)`
    }
  }
  if (Array.isArray(data)) return `array(${data.length} items)`
  if (typeof data === 'object') return `object(keys: ${Object.keys(data as Record<string, unknown>).join(', ')})`
  return typeof data
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
        request_shape: describePayload(error.config?.data),
        response_shape: describePayload(error.response?.data),
      },
    })

    return Promise.reject(error)
  }
)

// Several pages mount multiple components that each independently GET the
// same endpoint (e.g. Navbar + PlanUsageBanner + dashboard page all fetch
// /sessions/usage on mount) -- confirmed live to fire the same request up
// to 4x on a single page load. Collapse concurrent identical GETs into one
// network call instead of touching every call site. Deliberately in-flight
// only (not a time-based cache): the map entry clears the moment the
// request settles, so the next distinct call always hits the network --
// this must never serve stale session/progress data.
const inFlightGets = new Map<string, Promise<AxiosResponse>>()
const originalGet = api.get.bind(api)

api.get = ((url: string, config?: AxiosRequestConfig) => {
  const key = `${url}?${JSON.stringify(config?.params ?? null)}`
  const existing = inFlightGets.get(key)
  if (existing) return existing

  const request = originalGet(url, config).finally(() => {
    inFlightGets.delete(key)
  })
  inFlightGets.set(key, request)
  return request
}) as typeof api.get

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

// Mirrors backend/app/core/plans.py PLANS. Used as the offline/error fallback
// everywhere a landing component needs a price or session count before (or
// instead of) a resolved /plans/ call, so there's one place to update instead
// of five components independently drifting out of sync with the backend --
// which is exactly how a stale ₹999 Pro-price fallback once shipped.
export const FALLBACK_PLANS: Plan[] = [
  {
    id: 'free',
    name: 'Free Trial',
    price: 0,
    period: 'forever',
    description: 'Try the full 9-criteria examiner report',
    features: [
      '3 speaking scenarios per month',
      'Full 9-criteria OET scoring',
      'AI patient conversation',
      'Standard voice',
      'Last 3 attempts',
    ],
    cta: 'Current Plan',
    highlight: false,
    disabled: true,
    profile_plan: 'free',
    sessions_limit: 3,
  },
  {
    id: 'basic',
    name: 'Basic',
    price: 299,
    period: 'month',
    description: 'Speaking practice with the full examiner report',
    features: [
      '20 speaking scenarios per month',
      'Full 9-criteria OET scoring',
      'AI patient conversation',
      'Standard voice',
      'Last 10 attempts',
      'Per-session report',
      'Email support',
    ],
    cta: 'Subscribe Basic',
    highlight: false,
    disabled: false,
    profile_plan: 'basic',
    sessions_limit: 20,
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 799,
    period: 'month',
    description: 'Complete OET preparation and performance tracking',
    features: [
      '40 speaking scenarios per month',
      'Full 9-criteria OET scoring with richer, more detailed feedback',
      'Premium British patient voice',
      'Writing practice and scoring',
      'Unlimited attempt history',
      'Unlimited attempt comparison over time',
      'Priority email support',
    ],
    cta: 'Subscribe Pro',
    highlight: true,
    disabled: false,
    profile_plan: 'pro',
    sessions_limit: 40,
  },
  {
    id: 'elite',
    name: 'Elite',
    price: 1499,
    period: 'month',
    description: 'Maximum preparation',
    features: [
      '80 speaking scenarios per month',
      'Full 9-criteria OET scoring with richer, more detailed feedback',
      'Phoneme-level pronunciation scoring',
      'Premium British patient voice',
      'AI generated study plan',
      'Writing practice and scoring',
      'Unlimited attempt history',
      'Unlimited attempt comparison over time',
      'Advanced weak area detection',
      'WhatsApp priority support',
    ],
    cta: 'Subscribe Elite',
    highlight: false,
    disabled: false,
    profile_plan: 'elite',
    sessions_limit: 80,
  },
]

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
