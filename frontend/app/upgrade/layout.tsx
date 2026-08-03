import type { Metadata } from 'next'
import { headers } from 'next/headers'

export const metadata: Metadata = {
  title: 'Upgrade Your Plan',
  description: 'Compare SpeakOET plans and pick the one that fits your OET Speaking prep.',
}

export default function UpgradeLayout({ children }: { children: React.ReactNode }) {
  // See app/dashboard/layout.tsx for why this call is here.
  headers()
  return <>{children}</>
}
