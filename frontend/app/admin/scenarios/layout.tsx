import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Scenarios - Admin',
  robots: { index: false, follow: false },
}

export default function AdminScenariosLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
