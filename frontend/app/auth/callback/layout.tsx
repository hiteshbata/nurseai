import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Signing In... - SpeakOET',
  robots: { index: false, follow: false },
}

export default function CallbackLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
