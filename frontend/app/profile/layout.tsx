import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Settings - SpeakOET',
  description: 'Manage your account, practice plan, and billing.',
}

export default function ProfileLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
