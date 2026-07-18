import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Action History - Admin',
  robots: { index: false, follow: false },
}

export default function AdminAuditLogLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
