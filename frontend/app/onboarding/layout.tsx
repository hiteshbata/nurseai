import type { Metadata } from 'next'
import { headers } from 'next/headers'

export const metadata: Metadata = {
  title: 'Get Started',
  description: 'Tell us about your exam and goals so we can personalize your OET Speaking practice.',
}

export default function OnboardingLayout({ children }: { children: React.ReactNode }) {
  // See app/dashboard/layout.tsx for why this call is here.
  headers()
  return (
    <div className="min-h-screen bg-gray-50">
      {children}
    </div>
  )
}
