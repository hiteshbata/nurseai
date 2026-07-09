import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Speaking Practice - SpeakOET',
  description: 'Practice OET Speaking roleplays with an AI patient and get a 9-criteria examiner report.',
}

export default function SpeakingLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
