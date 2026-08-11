// Cookie/tracking consent state. First-party localStorage record (mirrors the
// speakoet_impersonation pattern in src/lib/impersonation.ts) plus a
// window CustomEvent so any mounted component -- the banner, the preferences
// modal, the footer link -- stays in sync without a React context provider.
//
// This file only reads/writes consent state. Applying it to the actual
// tracker SDKs (PostHog/GA/Meta) lives in src/lib/tracking.ts.

const STORAGE_KEY = 'speakoet_consent'
export const CONSENT_CHANGED_EVENT = 'speakoet:consent-changed'
export const OPEN_CONSENT_PREFERENCES_EVENT = 'speakoet:open-consent-preferences'

// Bump this when the categories or purposes of tracking materially change --
// any consent recorded under an older version is treated as absent, so the
// banner reappears and the user is asked again.
export const CONSENT_VERSION = '1.0'

export interface ConsentPreferences {
  analytics: boolean
  marketing: boolean
}

export interface ConsentRecord extends ConsentPreferences {
  necessary: true
  version: string
  timestamp: string
}

export function getStoredConsent(): ConsentRecord | null {
  if (typeof window === 'undefined') return null
  let raw: string | null
  try {
    raw = localStorage.getItem(STORAGE_KEY)
  } catch {
    // Storage can throw in private-browsing/locked-down contexts -- treat as
    // "no decision yet" rather than crashing the app.
    return null
  }
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<ConsentRecord>
    if (parsed.version !== CONSENT_VERSION) return null
    if (typeof parsed.analytics !== 'boolean' || typeof parsed.marketing !== 'boolean') return null
    return {
      necessary: true,
      analytics: parsed.analytics,
      marketing: parsed.marketing,
      version: CONSENT_VERSION,
      timestamp: parsed.timestamp ?? new Date().toISOString(),
    }
  } catch {
    return null
  }
}

export function saveConsent(prefs: ConsentPreferences): ConsentRecord {
  const record: ConsentRecord = {
    necessary: true,
    analytics: prefs.analytics,
    marketing: prefs.marketing,
    version: CONSENT_VERSION,
    timestamp: new Date().toISOString(),
  }
  if (typeof window !== 'undefined') {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(record))
    } catch {
      // Non-fatal -- the in-memory record still drives this tab's session
      // via the dispatched event below, it just won't survive a reload.
    }
    window.dispatchEvent(new CustomEvent<ConsentRecord>(CONSENT_CHANGED_EVENT, { detail: record }))
  }
  return record
}

// Used by the footer link / avatar-menu "Cookie settings" entry to reopen
// the preferences modal without prop-drilling a context through the tree --
// same pattern as the impersonation-changed event.
export function openConsentPreferences() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(OPEN_CONSENT_PREFERENCES_EVENT))
}
