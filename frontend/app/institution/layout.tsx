import { headers } from 'next/headers'

export const metadata = {
  title: 'Institution Overview',
  description: 'Institution admin dashboard for your OET Speaking program.',
}

export default function InstitutionLayout({
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
