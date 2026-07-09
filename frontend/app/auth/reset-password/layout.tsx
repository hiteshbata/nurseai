import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Reset Password - SpeakOET',
  description: 'Choose a new password for your SpeakOET account.',
  robots: { index: false, follow: false },
}

export default function ResetPasswordLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
