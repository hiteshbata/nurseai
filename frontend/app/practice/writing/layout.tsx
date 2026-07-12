import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Writing Practice',
  description: 'Practice OET Writing case notes and get scored feedback.',
}

export default function WritingLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
