import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Settings - Admin',
  robots: { index: false, follow: false },
}

export default function AdminSettingsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
