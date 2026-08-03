import { headers } from 'next/headers'

export const metadata = {
  title: 'Dashboard',
  description: 'Track your OET Speaking progress, scores, and streaks.',
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Reading a request header opts this route into dynamic rendering, which
  // is what lets Next.js pick up the per-request nonce middleware.ts put in
  // the CSP header and apply it to its own hydration scripts. See middleware.ts.
  headers()
  return <>{children}</>
}
