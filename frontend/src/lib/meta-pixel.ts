// Meta Pixel (client) + Meta Conversions API (server) dispatcher.
//
// Every call fires the browser pixel AND posts to our own /api/meta-capi
// route (which holds the real access token) using the *same* event_id, so
// Meta dedupes the two deliveries of one logical event.
//
// Mirrors the queue-until-init pattern already used by src/lib/analytics.ts
// so events fired before the deferred pixel script loads aren't dropped.

declare global {
  interface Window {
    fbq?: ((...args: unknown[]) => void) & { callMethod?: unknown; queue?: unknown[] }
    _fbq?: unknown
  }
}

export type MetaEventName =
  | 'PageView'
  | 'ViewContent'
  | 'Lead'
  | 'CompleteRegistration'
  | 'StartTrial'
  | 'InitiateCheckout'
  | 'Purchase'
  | 'Subscribe'
  | 'SpeakingSessionStarted'
  | 'SpeakingSessionCompleted'
  | 'ReadingPracticeStarted'
  | 'UserLoggedIn'

const STANDARD_EVENTS = new Set<MetaEventName>([
  'PageView',
  'ViewContent',
  'Lead',
  'CompleteRegistration',
  'StartTrial',
  'InitiateCheckout',
  'Purchase',
  'Subscribe',
])

export interface MetaUserData {
  email?: string
  phone?: string
}

let initialized = false
const pendingBrowserEvents: { name: MetaEventName; customData?: Record<string, unknown>; eventId: string }[] = []

// Set once the user's identity is known (see providers.tsx) so every event
// after login/signup carries hashed match data, without every call site
// having to thread the user through.
let currentUserData: MetaUserData = {}

export function setMetaUserData(data: MetaUserData) {
  currentUserData = { ...currentUserData, ...data }
}

export function clearMetaUserData() {
  currentUserData = {}
}

export function initMetaPixel() {
  if (initialized || typeof window === 'undefined') return
  const pixelId = process.env.NEXT_PUBLIC_META_PIXEL_ID
  if (!pixelId) return

  // Standard Meta Pixel base code: installs a queuing stub synchronously,
  // then loads fbevents.js async and flushes the stub's queue once ready.
  ;(function (f: Window, b: Document, e: string, v: string) {
    if (f.fbq) return
    const n: NonNullable<Window['fbq']> = function (...args: unknown[]) {
      if (n.callMethod) {
        ;(n.callMethod as (...a: unknown[]) => void)(...args)
      } else {
        n.queue!.push(args)
      }
    } as NonNullable<Window['fbq']>
    if (!f._fbq) f._fbq = n
    n.queue = []
    f.fbq = n
    const t = b.createElement(e) as HTMLScriptElement
    t.async = true
    t.src = v
    const s = b.getElementsByTagName(e)[0]
    s.parentNode?.insertBefore(t, s)
  })(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js')

  window.fbq!('init', pixelId)
  initialized = true

  while (pendingBrowserEvents.length) {
    const evt = pendingBrowserEvents.shift()!
    fireBrowserEvent(evt.name, evt.customData, evt.eventId)
  }
}

function fireBrowserEvent(name: MetaEventName, customData: Record<string, unknown> | undefined, eventId: string) {
  window.fbq?.(STANDARD_EVENTS.has(name) ? 'track' : 'trackCustom', name, customData ?? {}, { eventID: eventId })
}

export function trackMetaEvent(
  eventName: MetaEventName,
  customData?: Record<string, unknown>,
  userData?: MetaUserData
) {
  if (typeof window === 'undefined') return

  const eventId = crypto.randomUUID()

  if (initialized) {
    fireBrowserEvent(eventName, customData, eventId)
  } else {
    pendingBrowserEvents.push({ name: eventName, customData, eventId })
  }

  const mergedUserData = { ...currentUserData, ...userData }

  fetch('/api/meta-capi', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    keepalive: true,
    body: JSON.stringify({
      event_name: eventName,
      event_id: eventId,
      event_source_url: window.location.href,
      custom_data: customData,
      user_data: Object.keys(mergedUserData).length ? mergedUserData : undefined,
    }),
  }).catch((err) => {
    console.error('[meta-pixel] CAPI dispatch failed', err)
  })
}
