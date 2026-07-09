import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Log In - SpeakOET',
  description: 'Log in to your SpeakOET account to continue your OET Speaking practice.',
}

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
