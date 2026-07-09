import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Mock Test - SpeakOET',
  description: 'Take a full OET-style mock test to check your exam readiness.',
}

export default function MockTestLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
