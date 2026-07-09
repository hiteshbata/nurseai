import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Forgot Password - SpeakOET',
  description: 'Reset the password for your SpeakOET account.',
}

export default function ForgotPasswordLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
