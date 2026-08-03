'use client'

import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter, usePathname } from 'next/navigation'
import { supabase, signOut, useSupabaseSession } from '@/lib/supabase'
import { LayoutDashboard, Settings, LogOut, Gift } from 'lucide-react'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'
import { ThemeToggle } from '@/components/ThemeToggle'
import api from '@/lib/api'

const publicNavLinks = [
  { href: '/#how-it-works', label: 'How It Works' },
  { href: '/pricing', label: 'Pricing' },
  { href: '/about', label: 'About' },
  { href: '/blog', label: 'Blog' },
]

const appNavLinks = [
  { href: '/hub', label: 'Study Hub' },
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/practice/speaking', label: 'Speaking' },
  { href: '/practice/writing', label: 'Writing' },
  { href: '/practice/reading', label: 'Reading' },
  { href: '/practice/listening', label: 'Listening' },
  { href: '/practice/mock', label: 'Mock Test' },
]

const WRITING_PLANS = ['pro', 'elite']

const PLAN_LABELS: Record<string, string> = {
  free: 'Free',
  basic: 'Basic',
  pro: 'Pro',
  elite: 'Elite',
}

interface SessionUsage {
  sessions_used: number
  sessions_limit: number
  sessions_remaining: number
  plan: string
}

export function Navbar() {
  const { session, status } = useSupabaseSession()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const [avatarOpen, setAvatarOpen] = useState(false)
  const avatarRef = useRef<HTMLDivElement>(null)
  const avatarButtonRef = useRef<HTMLButtonElement>(null)
  const upgradeMenuItemRef = useRef<HTMLAnchorElement>(null)
  const dashboardMenuItemRef = useRef<HTMLAnchorElement>(null)
  const settingsMenuItemRef = useRef<HTMLAnchorElement>(null)
  const referMenuItemRef = useRef<HTMLAnchorElement>(null)
  const signOutMenuItemRef = useRef<HTMLButtonElement>(null)
  const router = useRouter()
  const pathname = usePathname()
  const isLanding = pathname === '/'
  const publicPaths = ['/', '/about', '/support', '/blog', '/privacy', '/terms', '/pricing']
  const isPublicPage =
    publicPaths.includes(pathname || '') ||
    (pathname?.startsWith('/learn') ?? false) ||
    (pathname?.startsWith('/docs') ?? false) ||
    (pathname?.startsWith('/tools') ?? false)
  // An anonymous free-mock-test session is a real `session` object, but it's
  // not a signed-up visitor -- on public/marketing pages it should read the
  // same as signed-out (see AppShell.tsx's isAnonymous branch for the app-shell
  // side of this same fix).
  const isAnonymous = !!session?.user?.is_anonymous
  const navLinksToShow = (!session || isAnonymous) && isPublicPage ? publicNavLinks : appNavLinks
  const isActiveLink = (href: string) => !href.startsWith('/#') && pathname === href

  const getInitials = (name: string) => {
    const parts = name.trim().split(' ')
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    }
    return parts[0].slice(0, 2).toUpperCase()
  }

  const userEmail = session?.user?.email || ''
  // Fall back to the email's local part rather than the raw address --
  // getInitials() on a full email (no space) collapses to its first two
  // characters (e.g. "test@gmail.com" -> "TE"), which is what the avatar
  // badge showed before this fix.
  const emailLocalPart = userEmail.split('@')[0]
  const userName =
    session?.user?.user_metadata?.full_name ||
    session?.user?.user_metadata?.name ||
    (emailLocalPart ? emailLocalPart[0].toUpperCase() + emailLocalPart.slice(1) : '')

  const [usage, setUsage] = useState<SessionUsage | null>(null)

  useEffect(() => {
    if (status !== 'authenticated' || isAnonymous) {
      setUsage(null)
      return
    }
    let cancelled = false
    api.get('/sessions/usage').then((res) => {
      if (!cancelled) setUsage(res.data)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [status, isAnonymous])

  const planLabel = usage ? (PLAN_LABELS[usage.plan] ?? usage.plan) : null
  const showUpgrade = usage ? usage.plan !== 'elite' : false

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (avatarRef.current && !avatarRef.current.contains(e.target as Node)) {
        setAvatarOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const getAvatarMenuItems = () =>
    [
      showUpgrade ? upgradeMenuItemRef.current : null,
      dashboardMenuItemRef.current,
      settingsMenuItemRef.current,
      referMenuItemRef.current,
      signOutMenuItemRef.current,
    ].filter((el): el is HTMLAnchorElement | HTMLButtonElement => !!el)

  useEffect(() => {
    if (avatarOpen) getAvatarMenuItems()[0]?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [avatarOpen])

  const handleAvatarMenuKeyDown = (e: React.KeyboardEvent) => {
    const items = getAvatarMenuItems()
    const currentIndex = items.indexOf(document.activeElement as HTMLAnchorElement | HTMLButtonElement)
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      items[(currentIndex + 1) % items.length]?.focus()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      items[(currentIndex - 1 + items.length) % items.length]?.focus()
    } else if (e.key === 'Home') {
      e.preventDefault()
      items[0]?.focus()
    } else if (e.key === 'End') {
      e.preventDefault()
      items[items.length - 1]?.focus()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setAvatarOpen(false)
      avatarButtonRef.current?.focus()
    }
  }

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 10)
    window.addEventListener('scroll', handler)
    return () => window.removeEventListener('scroll', handler)
  }, [])

  // Captured wherever a ?ref=CODE link first lands (Navbar mounts on every
  // page), then redeemed once the visitor actually signs up and hits
  // onboarding — see the redeem call in onboarding/page.tsx.
  useEffect(() => {
    const ref = new URLSearchParams(window.location.search).get('ref')
    if (ref) localStorage.setItem('referral_code', ref)
  }, [])

  const PlanUsagePill = ({ onNavigate }: { onNavigate?: () => void }) => {
    if (!usage) return null
    return (
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center whitespace-nowrap rounded-full bg-blue-50 dark:bg-blue-500/10 px-2.5 py-1 text-xs font-semibold text-blue-700 dark:text-blue-400">
          {planLabel} &middot; {usage.sessions_used}/{usage.sessions_limit} sessions
        </span>
        {showUpgrade && (
          <Link
            href="/upgrade"
            onClick={onNavigate}
            className="rounded-full bg-emerald-700 px-3 py-1 text-xs font-semibold text-white hover:opacity-90 transition whitespace-nowrap"
          >
            Upgrade
          </Link>
        )}
      </div>
    )
  }

  return (
    <nav
      id="main-navbar"
      className={`sticky top-0 z-50 bg-card border-b border-border transition-shadow duration-200 ${scrolled ? 'shadow-md' : ''}`}
    >
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link href="/">
          <SpeakOETLogo height={28} variant="full" theme="dark" priority />
        </Link>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-6">
          {navLinksToShow.map((link: any) =>
            link.disabled ? (
              <span
                key={link.href}
                className="text-muted-foreground cursor-not-allowed text-sm font-semibold transition"
                title="Coming Soon"
              >
                {link.label}
              </span>
            ) : (
              <Link
                key={link.href}
                href={link.href}
                prefetch={true}
                aria-current={isActiveLink(link.href) ? 'page' : undefined}
                className={`inline-flex items-center gap-1.5 min-h-11 transition text-sm font-semibold ${
                  isActiveLink(link.href)
                    ? 'text-emerald-600 border-b-2 border-emerald-600'
                    : 'text-foreground/80 hover:text-emerald-600'
                }`}
              >
                {link.label}
                {link.href === '/practice/writing' && usage && !WRITING_PLANS.includes(usage.plan) && (
                  <span className="rounded-full bg-blue-50 dark:bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-bold text-blue-700 dark:text-blue-400">Pro</span>
                )}
              </Link>
            )
          )}
        </div>

        <div className="flex items-center gap-3">
          {status === 'loading' ? (
            <div className="w-24 h-9" />
          ) : status === 'authenticated' && !isAnonymous ? (
            <>
              <div className="hidden sm:flex">
                <PlanUsagePill />
              </div>
              <div className="relative" ref={avatarRef}>
              <button
                ref={avatarButtonRef}
                onClick={() => setAvatarOpen(!avatarOpen)}
                aria-haspopup="menu"
                aria-expanded={avatarOpen}
                aria-controls="avatar-menu"
                className="w-9 h-9 rounded-full bg-primary text-primary-foreground text-sm font-semibold flex items-center justify-center hover:opacity-90 transition-opacity focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2"
              >
                {getInitials(userName)}
              </button>
              {avatarOpen && (
                <div
                  id="avatar-menu"
                  role="menu"
                  aria-label="User menu"
                  onKeyDown={handleAvatarMenuKeyDown}
                  className="absolute right-0 top-12 z-50 w-48 bg-card rounded-xl shadow-lg border border-border py-2"
                >
                  <div className="px-4 py-2 font-semibold text-sm text-foreground truncate">
                    {userName}
                  </div>
                  <div className="px-4 pb-2 text-xs text-muted-foreground truncate">
                    {userEmail}
                  </div>
                  {usage && (
                    <div className="px-4 pb-2 flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-muted-foreground">
                        {planLabel} plan &middot; {usage.sessions_used}/{usage.sessions_limit} sessions
                      </span>
                      {showUpgrade && (
                        <Link
                          ref={upgradeMenuItemRef}
                          href="/upgrade"
                          role="menuitem"
                          onClick={() => setAvatarOpen(false)}
                          className="text-xs font-semibold text-emerald-600 hover:underline whitespace-nowrap"
                        >
                          Upgrade
                        </Link>
                      )}
                    </div>
                  )}
                  <div className="border-t border-border my-1" />
                  <Link
                    ref={dashboardMenuItemRef}
                    href="/dashboard"
                    role="menuitem"
                    onClick={() => setAvatarOpen(false)}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-foreground/80 hover:bg-muted"
                  >
                    <LayoutDashboard className="h-4 w-4" />
                    Dashboard
                  </Link>
                  <Link
                    ref={settingsMenuItemRef}
                    href="/profile"
                    role="menuitem"
                    onClick={() => setAvatarOpen(false)}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-foreground/80 hover:bg-muted"
                  >
                    <Settings className="h-4 w-4" />
                    Settings
                  </Link>
                  <Link
                    ref={referMenuItemRef}
                    href="/refer"
                    role="menuitem"
                    onClick={() => setAvatarOpen(false)}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-foreground/80 hover:bg-muted"
                  >
                    <Gift className="h-4 w-4" />
                    Refer &amp; Earn
                  </Link>
                  <div className="border-t border-border my-1" />
                  <button
                    ref={signOutMenuItemRef}
                    role="menuitem"
                    onClick={async () => { setAvatarOpen(false); await signOut(); window.location.href = '/' }}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10 w-full text-left"
                  >
                    <LogOut className="h-4 w-4" />
                    Sign Out
                  </button>
                </div>
              )}
              </div>
            </>
          ) : isLanding ? (
            <div className="hidden sm:flex items-center gap-3">
              <Link
                href="/auth/register"
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition whitespace-nowrap"
                style={{ backgroundColor: "#10B981" }}
              >
                Get Started
              </Link>
              <Link
                href="/auth/login"
                className="text-sm font-semibold px-3 py-2 rounded transition whitespace-nowrap"
                style={{ color: "#0F2356" }}
              >
                Sign In
              </Link>
            </div>
          ) : (
            <div className="hidden sm:flex items-center gap-3">
              <Link href="/auth/login" className="text-sm text-foreground font-semibold hover:bg-muted px-3 py-2 rounded transition whitespace-nowrap">
                Sign In
              </Link>
              <Link href="/auth/register" className="px-4 py-2 bg-emerald-700 text-white rounded-lg text-sm font-semibold hover:opacity-90 transition whitespace-nowrap">
                Sign Up
              </Link>
            </div>
          )}

          <ThemeToggle className="hidden sm:inline-flex" />

          {/* Hamburger */}
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden p-2 text-foreground/80 hover:bg-muted rounded-lg"
            aria-label="Toggle menu"
          >
            {mobileOpen ? (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            ) : (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      <div
        className={`md:hidden overflow-hidden transition-all duration-300 ease-in-out ${
          mobileOpen ? 'max-h-96 border-b border-border shadow-sm' : 'max-h-0'
        }`}
      >
        <div className="px-4 py-2 bg-card">
          {session && usage && (
            <div className="sm:hidden flex items-center justify-between gap-2 py-3 border-b border-border mb-1">
              <span className="inline-flex items-center whitespace-nowrap rounded-full bg-blue-50 dark:bg-blue-500/10 px-2.5 py-1 text-xs font-semibold text-blue-700 dark:text-blue-400">
                {planLabel} &middot; {usage.sessions_used}/{usage.sessions_limit} sessions
              </span>
              {showUpgrade && (
                <Link
                  href="/upgrade"
                  onClick={() => setMobileOpen(false)}
                  className="rounded-full bg-emerald-700 px-3 py-1 text-xs font-semibold text-white hover:opacity-90 transition whitespace-nowrap"
                >
                  Upgrade
                </Link>
              )}
            </div>
          )}
          {navLinksToShow.map((link: any) =>
            link.disabled ? (
              <span
                key={link.href}
                className="block py-2 text-muted-foreground cursor-not-allowed text-sm"
                title="Coming Soon"
              >
                {link.label} <span className="text-xs text-amber-500">(Coming Soon)</span>
              </span>
            ) : (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                aria-current={isActiveLink(link.href) ? 'page' : undefined}
                className={`flex items-center gap-1.5 min-h-11 transition text-sm ${
                  isActiveLink(link.href) ? 'text-emerald-600 font-semibold' : 'text-foreground/80 hover:text-emerald-600'
                }`}
              >
                {link.label}
                {link.href === '/practice/writing' && usage && !WRITING_PLANS.includes(usage.plan) && (
                  <span className="rounded-full bg-blue-50 dark:bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-bold text-blue-700 dark:text-blue-400">Pro</span>
                )}
              </Link>
            )
          )}
          {status !== 'loading' && (!session || isAnonymous) && (
            <>
              <Link href="/auth/login" onClick={() => setMobileOpen(false)} className="flex items-center min-h-11 text-foreground/80 hover:text-emerald-600 transition text-sm">
                Sign In
              </Link>
              <Link href="/auth/register" onClick={() => setMobileOpen(false)} className="flex items-center min-h-11 text-emerald-700 font-semibold text-sm">
                Sign Up
              </Link>
            </>
          )}
          <div className="flex items-center justify-between border-t border-border mt-2 pt-3">
            <span className="text-sm text-muted-foreground">Appearance</span>
            <ThemeToggle />
          </div>
        </div>
      </div>
    </nav>
  )
}
