import axios, { AxiosInstance, AxiosError, AxiosRequestConfig, AxiosResponse } from 'axios'
import * as Sentry from '@sentry/nextjs'
import { createElement } from 'react'
import toast from 'react-hot-toast'
import { supabase, signOut } from '@/lib/supabase'
import type { Plan } from './plans'

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
  // One ID per call so a Sentry error and the matching backend log line
  // (tagged via RequestIDMiddleware) can be pulled up side by side.
  config.headers['x-request-id'] = crypto.randomUUID()

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

// A 403 with this shape means the user hit a plan gate, not a real failure --
// every page should show the same upgrade prompt instead of its own
// "failed to load" / empty-state fallback. See isUpgradeRequiredError below.
function upgradeDetail(error: AxiosError): { upgrade_required: true; current_plan?: string } | null {
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
  if (error.response?.status === 403 && detail && typeof detail === 'object' && (detail as any).upgrade_required) {
    return detail as { upgrade_required: true; current_plan?: string }
  }
  return null
}

export function isUpgradeRequiredError(error: unknown): boolean {
  return !!upgradeDetail(error as AxiosError)
}

// Handle errors
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && error.config?.url) {
      const requestUrl: string = error.config.url
      const isPublicPath = ['/plans/'].some((p) => requestUrl.startsWith(p))
      // Routes through the same signOut() every other logout path uses (see
      // supabase.ts) instead of calling supabase.auth.signOut() directly --
      // that raw call skips the loggingOut flag, so every mounted page's own
      // "unauthenticated -> redirect" effect fired at the same time as this
      // handler's own redirect, racing two navigations to the same place.
      if (!isPublicPath && typeof window !== 'undefined') {
        signOut('/auth/login')
      }
    }

    if (upgradeDetail(error) && typeof window !== 'undefined') {
      // Round-trip back to whatever the user was trying to reach (e.g. a specific
      // reading test) instead of dropping them on a generic page post-upgrade.
      const next = window.location.pathname + window.location.search
      const upgradeHref = `/upgrade?next=${encodeURIComponent(next)}`
      toast.error(
        createElement(
          'div',
          null,
          createElement('p', { className: 'font-semibold' }, 'This feature requires a paid plan'),
          createElement(
            'a',
            {
              href: upgradeHref,
              className:
                'inline-block mt-2 bg-[#0F2356] text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-[#0F2356]/90',
            },
            'Upgrade to Pro →'
          )
        ),
        { id: 'upgrade-required', duration: 8000 }
      )
    }

    Sentry.captureException(error, {
      tags: {
        api_method: error.config?.method?.toUpperCase(),
        api_url: error.config?.url,
        status_code: error.response?.status?.toString() || '0',
        request_id: error.config?.headers?.['x-request-id'] as string | undefined,
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

// Re-exported so existing `import { FALLBACK_PLANS, type Plan } from '@/lib/api'`
// call sites keep working. New server components should import from
// '@/lib/plans' directly instead -- see the comment there.
export type { Plan } from './plans'
export { FALLBACK_PLANS } from './plans'

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
