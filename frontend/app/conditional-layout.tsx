'use client'

import { usePathname } from 'next/navigation'
import { Navbar } from '@/components/Navbar'
import { Footer } from '@/components/Footer'

export default function ConditionalLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isFullPage = pathname?.startsWith('/auth') || pathname?.startsWith('/onboarding')

  if (isFullPage) {
    return <>{children}</>
  }

  return (
    <>
      <Navbar />
      <main className="min-h-screen flex flex-col">{children}</main>
      <Footer />
    </>
  )
}
