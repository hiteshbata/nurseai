import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'AI Cost & Margin - Admin',
  robots: { index: false, follow: false },
}

export default function AdminAiCostsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
