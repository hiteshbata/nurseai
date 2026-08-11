'use client'

import { useEffect, useState } from 'react'
import { useConsent } from '@/app/hooks/useConsent'
import { OPEN_CONSENT_PREFERENCES_EVENT } from '@/lib/consent'
import { ConsentBanner } from './ConsentBanner'
import { ConsentPreferencesModal } from './ConsentPreferencesModal'

// Mounted once in providers.tsx. Owns both the first-visit banner and the
// preferences modal so the "Cookie settings" link in the footer/avatar menu
// can reopen the same modal later by firing a window event instead of each
// needing their own copy of this state.
export function ConsentManager() {
  const { consent, needsDecision, acceptAll, rejectNonEssential, respond } = useConsent()
  const [modalOpen, setModalOpen] = useState(false)

  useEffect(() => {
    const openHandler = () => setModalOpen(true)
    window.addEventListener(OPEN_CONSENT_PREFERENCES_EVENT, openHandler)
    return () => window.removeEventListener(OPEN_CONSENT_PREFERENCES_EVENT, openHandler)
  }, [])

  return (
    <>
      {needsDecision && !modalOpen && (
        <ConsentBanner
          onAcceptAll={acceptAll}
          onRejectAll={rejectNonEssential}
          onManage={() => setModalOpen(true)}
        />
      )}
      {modalOpen && (
        <ConsentPreferencesModal
          initial={consent}
          onClose={() => setModalOpen(false)}
          onSave={(prefs) => {
            respond(prefs)
            setModalOpen(false)
          }}
        />
      )}
    </>
  )
}
