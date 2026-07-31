'use client'

import { usePathname } from 'next/navigation'
import { Navbar } from '@/components/Navbar'
import { Footer } from '@/components/Footer'
import { AppShell } from '@/components/AppShell'

// Flip to false to go straight back to the old top-bar Navbar on every page.
// Nothing else needs changing -- Navbar.tsx is untouched and still owns the
// public pages either way.
const USE_APP_SHELL = true

// Marketing / legal / content pages keep the marketing top bar even when
// signed in; they are not part of the practice app.
//
// /support is deliberately NOT here even though it's marketing-adjacent: the
// avatar menu's "Help & Support" link points at it, so it must render inside
// AppShell or clicking it drops a signed-in user back into the old top bar
// mid-session. Anonymous visitors arriving from the public footer link get
// AppShell too (with a Sign In button instead of the avatar) rather than
// branching this decision on auth state -- see the hydration note below.
const PUBLIC_PATHS = ['/', '/about', '/blog', '/privacy', '/terms', '/pricing']
const PUBLIC_PREFIXES = ['/learn', '/docs', '/admin', '/tools']

export default function ConditionalLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isFullPage = pathname?.startsWith('/auth') || pathname?.startsWith('/onboarding')
  const hideFooter = pathname?.startsWith('/practice/speaking')

  if (isFullPage) {
    return <main id="main-content">{children}</main>
  }

  const isPublicPage =
    PUBLIC_PATHS.includes(pathname || '') ||
    PUBLIC_PREFIXES.some((p) => pathname?.startsWith(p))

  // Decide the shell from the pathname ONLY. Branching on `session` here
  // rendered the Navbar tree on the server and swapped to the AppShell tree
  // once getSession() resolved on the client -- moving {children} to a
  // different position mid-hydration, which threw "Hydration failed because
  // the initial UI does not match" and remounted the whole page subtree on
  // every load. Pathname is identical on server and client, so the tree is
  // stable and AppShell handles the signed-out case itself.
  //
  // No footer inside the app shell: the site footer is a marketing footer
  // (How It Works, Pricing, the /learn SEO pages, social) aimed at visitors
  // who haven't signed up. Support, Privacy and Terms live in the avatar menu
  // instead, which is where signed-in users look for them.
  if (USE_APP_SHELL && !isPublicPage) {
    return <AppShell>{children}</AppShell>
  }

  return (
    <>
      <Navbar />
      <main id="main-content" className="min-h-screen flex flex-col">{children}</main>
      {!hideFooter && <Footer />}
    </>
  )
}
