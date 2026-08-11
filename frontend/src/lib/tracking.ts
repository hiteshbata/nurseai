// Single entry point that turns a consent decision into actual tracker SDK
// state. Nothing outside this file should call PostHog/GA/Meta init or
// opt-out functions directly -- providers.tsx and the consent UI only ever
// call applyConsent(), so there is exactly one place that decides which
// trackers are allowed to run.
import { discardQueuedAnalytics, enableAnalytics, disableAnalytics } from './analytics'
import { enableGA, disableGA } from './ga'
import { enableMetaPixel, disableMetaPixel } from './meta-pixel'
import type { ConsentPreferences } from './consent'

export function applyConsent(consent: ConsentPreferences) {
  if (consent.analytics) {
    enableAnalytics()
    enableGA()
  } else {
    disableAnalytics()
    disableGA()
    discardQueuedAnalytics()
  }

  if (consent.marketing) {
    enableMetaPixel()
  } else {
    disableMetaPixel()
  }
}
