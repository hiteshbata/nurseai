import type { Metadata } from 'next'
import { headers } from 'next/headers'

export const metadata: Metadata = {
  title: 'Settings',
  description: 'Manage your account, practice plan, and billing.',
}

export default function ProfileLayout({ children }: { children: React.ReactNode }) {
  // See app/dashboard/layout.tsx for why this call is here.
  headers()
  return <>{children}</>
}
