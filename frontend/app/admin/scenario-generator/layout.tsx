import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Scenario Generator - Admin',
  robots: { index: false, follow: false },
}

export default function AdminScenarioGeneratorLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
