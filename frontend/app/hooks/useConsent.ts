'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  CONSENT_CHANGED_EVENT,
  getStoredConsent,
  saveConsent,
  type ConsentPreferences,
  type ConsentRecord,
} from '@/lib/consent'
import { applyConsent } from '@/lib/tracking'

export function useConsent() {
  // null + !ready during SSR/first client render (matches ThemeToggle's
  // "mounted" gate) so the server-rendered banner state and the client's
  // first render agree -- localStorage is only read after mount.
  const [consent, setConsent] = useState<ConsentRecord | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setConsent(getStoredConsent())
    setReady(true)

    const onChange = (e: Event) => setConsent((e as CustomEvent<ConsentRecord>).detail)
    window.addEventListener(CONSENT_CHANGED_EVENT, onChange)
    return () => window.removeEventListener(CONSENT_CHANGED_EVENT, onChange)
  }, [])

  const respond = useCallback((prefs: ConsentPreferences) => {
    const record = saveConsent(prefs)
    applyConsent(record)
    setConsent(record)
  }, [])

  const acceptAll = useCallback(() => respond({ analytics: true, marketing: true }), [respond])
  const rejectNonEssential = useCallback(() => respond({ analytics: false, marketing: false }), [respond])

  return {
    consent,
    ready,
    needsDecision: ready && consent === null,
    respond,
    acceptAll,
    rejectNonEssential,
  }
}
