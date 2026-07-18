import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Users - Admin',
  robots: { index: false, follow: false },
}

export default function AdminUsersLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
