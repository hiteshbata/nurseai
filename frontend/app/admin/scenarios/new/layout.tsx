import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'New Scenario - Admin - SpeakOET',
  robots: { index: false, follow: false },
}

export default function AdminNewScenarioLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
