import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Error Logs - Admin - SpeakOET',
  robots: { index: false, follow: false },
}

export default function AdminLogsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
