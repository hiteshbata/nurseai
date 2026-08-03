import type { Metadata } from 'next'
import { headers } from 'next/headers'

export const metadata: Metadata = {
  title: 'Mock Test',
  description: 'Take a full OET-style mock test to check your exam readiness.',
}

export default function MockTestLayout({ children }: { children: React.ReactNode }) {
  // See app/dashboard/layout.tsx for why this call is here.
  headers()
  return <>{children}</>
}
