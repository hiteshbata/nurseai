import posthog from 'posthog-js'

let initialized = false
let pendingIdentify: { userId: string; props?: Record<string, unknown> } | null = null
const pendingEvents: { name: string; props?: Record<string, unknown> }[] = []

// initAnalytics() is deferred (requestIdleCallback, up to ~2s) so it doesn't
// block first paint. identifyUser/trackEvent can legitimately fire before it
// runs (e.g. a fast page load reaching onboarding quickly) — queue those
// calls instead of silently dropping them, and flush once init completes.
export function initAnalytics() {
  if (initialized || typeof window === 'undefined') return
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY
  if (!key) return
  posthog.init(key, {
    // Managed reverse proxy (data.speakoet.com) -- routes around ad blockers
    // that blocklist posthog's direct domains. ui_host stays PostHog's own
    // domain since it's just used for toolbar links, not data capture.
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://data.speakoet.com',
    ui_host: 'https://us.posthog.com',
    defaults: '2026-05-30',
    person_profiles: 'identified_only',
    capture_pageview: true,
    persistence: 'localStorage+cookie',
  })
  // One PostHog project for every deployment target -- this is what tells
  // rc1/local apart from production in it, on every event/session from here on.
  posthog.register({
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || process.env.NODE_ENV || 'development',
  })
  initialized = true

  if (pendingIdentify) {
    posthog.identify(pendingIdentify.userId, pendingIdentify.props)
    pendingIdentify = null
  }
  while (pendingEvents.length) {
    const evt = pendingEvents.shift()!
    posthog.capture(evt.name, evt.props)
  }
}

// Consent-driven on/off, layered on top of initAnalytics(). Analytics
// consent gates whether initAnalytics() ever runs at all (see tracking.ts),
// so these only matter for a user who granted consent and later withdraws
// it (or re-grants) within the same session, without a full page reload.
export function disableAnalytics() {
  if (typeof window === 'undefined' || !initialized) return
  posthog.opt_out_capturing()
}

export function enableAnalytics() {
  if (typeof window === 'undefined') return
  if (!initialized) {
    initAnalytics()
    return
  }
  posthog.opt_in_capturing()
}

export function identifyUser(userId: string, props?: Record<string, unknown>) {
  if (!initialized) {
    pendingIdentify = { userId, props }
    return
  }
  posthog.identify(userId, props)
}

export function resetAnalyticsIdentity() {
  if (!initialized) return
  posthog.reset()
}

export function trackEvent(name: string, props?: Record<string, unknown>) {
  if (!initialized) {
    pendingEvents.push({ name, props })
    return
  }
  posthog.capture(name, props)
}

// Called once when analytics consent is explicitly declined, so identify/
// trackEvent calls from the rest of the app stop piling up in memory for the
// remainder of a long client-side session that never initializes PostHog.
export function discardQueuedAnalytics() {
  pendingIdentify = null
  pendingEvents.length = 0
}
