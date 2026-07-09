import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Sign Up - SpeakOET',
  description: 'Create a free SpeakOET account and start practicing OET Speaking with an AI patient.',
}

export default function RegisterLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
