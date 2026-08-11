'use client'

import { Button } from '@/components/ui/button'
import { openConsentPreferences } from '@/lib/consent'

// Small client-component wrapper so the (server-rendered) Privacy Policy
// page can drop an interactive control into an otherwise static section
// without itself becoming a client component.
export function ManageCookiePreferencesButton() {
  return (
    <Button variant="outline" size="sm" onClick={openConsentPreferences}>
      Manage cookie preferences
    </Button>
  )
}
