'use client'

import { usePathname } from 'next/navigation'
import { Navbar } from '@/components/Navbar'
import { Footer } from '@/components/Footer'

export default function ConditionalLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isFullPage = pathname?.startsWith('/auth') || pathname?.startsWith('/onboarding')
  const hideFooter = pathname?.startsWith('/practice/speaking')

  if (isFullPage) {
    return <main id="main-content">{children}</main>
  }

  return (
    <>
      <Navbar />
      <main id="main-content" className="min-h-screen flex flex-col">{children}</main>
      {!hideFooter && <Footer />}
    </>
  )
}
