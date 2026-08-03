import { headers } from 'next/headers'

export default function PracticeLayout({ children }: { children: React.ReactNode }) {
  // See app/dashboard/layout.tsx for why this call is here.
  headers()
  return <>{children}</>
}
