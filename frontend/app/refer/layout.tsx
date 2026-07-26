import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Refer & Earn',
  description: 'Invite friends and earn free practice sessions.',
}

export default function ReferLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
