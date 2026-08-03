import type { Metadata } from 'next'
import { headers } from 'next/headers'
import AdminShell from './AdminShell'

export const metadata: Metadata = {
  title: 'Admin',
  robots: { index: false, follow: false },
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  // See app/dashboard/layout.tsx for why this call is here.
  headers()
  return <AdminShell>{children}</AdminShell>
}
