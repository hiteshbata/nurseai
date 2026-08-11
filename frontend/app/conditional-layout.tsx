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
// signed in; they are not part of the practice app. /support included so
// anonymous visitors from the public footer link see the plain marketing
// chrome instead of the app dashboard sidebar (which implied a logged-in
// state and linked to gated pages they couldn't use). Signed-in users
// dropping to the top bar via the avatar menu's "Help & Support" link is
// consistent with how Privacy/Terms already behave from that same menu.
const PUBLIC_PATHS = ['/', '/about', '/blog', '/privacy', '/terms', '/cookies', '/pricing', '/support']
const PUBLIC_PREFIXES = ['/learn', '/docs', '/tools']

export default function ConditionalLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isFullPage = pathname?.startsWith('/auth') || pathname?.startsWith('/onboarding')
  // AdminShell (app/admin/AdminShell.tsx) is a fully self-contained shell --
  // its own sidebar, its own nav, its own auth/role gate. Wrapping it in the
  // marketing Navbar/Footer here meant every /admin page shipped a second,
  // wrong-context nav (Navbar's own isPublicPage check doesn't know /admin
  // is "public" the way this file does, so it rendered the signed-in app's
  // nav links) plus a permanent marketing Footer at the bottom of every
  // admin page. Treat /admin like the isFullPage routes instead: no chrome
  // from this file at all.
  const isAdminPage = pathname?.startsWith('/admin')
  const hideFooter = pathname?.startsWith('/practice/speaking')

  if (isFullPage || isAdminPage) {
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
