'use client'

import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter, usePathname } from 'next/navigation'
import { signOut, useSupabaseSession } from '@/lib/supabase'
import {
  LayoutDashboard,
  Compass,
  Mic,
  PenLine,
  BookOpen,
  Headphones,
  ClipboardCheck,
  Settings,
  LogOut,
  Gift,
  HelpCircle,
  Menu,
  X,
  MoreHorizontal,
} from 'lucide-react'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'
import api from '@/lib/api'

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

interface NavItem {
  href: string
  label: string
  icon: typeof LayoutDashboard
  /** Renders a "Pro" chip when the current plan can't reach this module. */
  gatedPlans?: string[]
}

// Grouped so seven destinations scan as three decisions, not seven. The old
// flat top row put all seven at equal weight, which is what read as
// disorganised -- see the group headers rendered below.
const NAV_GROUPS: Array<{ heading: string | null; items: NavItem[] }> = [
  {
    heading: null,
    items: [
      { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { href: '/hub', label: 'Study Hub', icon: Compass },
    ],
  },
  {
    heading: 'Practice',
    items: [
      { href: '/practice/speaking', label: 'Speaking', icon: Mic },
      { href: '/practice/writing', label: 'Writing', icon: PenLine, gatedPlans: WRITING_PLANS },
      { href: '/practice/reading', label: 'Reading', icon: BookOpen },
      { href: '/practice/listening', label: 'Listening', icon: Headphones },
    ],
  },
  {
    heading: 'Assess',
    items: [{ href: '/practice/mock', label: 'Mock Test', icon: ClipboardCheck }],
  },
]

const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((g) => g.items)

// Longest match wins so /practice/reading/test/42 titles as "Reading", and
// /practice/mock doesn't lose to /practice.
const EXTRA_TITLES: Record<string, string> = {
  '/profile': 'Settings',
  '/refer': 'Refer & Earn',
  '/upgrade': 'Plans & Pricing',
  '/practice/vocab': 'Vocabulary',
  '/sessions': 'Session Feedback',
  '/support': 'Support',
}

function pageTitle(pathname: string | null): string {
  if (!pathname) return ''
  const candidates = [
    ...ALL_NAV_ITEMS.map((i) => [i.href, i.label] as const),
    ...Object.entries(EXTRA_TITLES),
  ]
  let best = ''
  let bestLen = -1
  for (const [href, label] of candidates) {
    if ((pathname === href || pathname.startsWith(href + '/')) && href.length > bestLen) {
      best = label
      bestLen = href.length
    }
  }
  return best
}

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false
  return pathname === href || pathname.startsWith(href + '/')
}

function getInitials(name: string) {
  const parts = name.trim().split(' ')
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  }
  return parts[0]?.slice(0, 2).toUpperCase() || '?'
}

function ProChip() {
  return (
    <span className="ml-auto rounded-full bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-700">
      Pro
    </span>
  )
}

function NavLinks({
  pathname,
  usage,
  onNavigate,
}: {
  pathname: string | null
  usage: SessionUsage | null
  onNavigate?: () => void
}) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-6">
      {NAV_GROUPS.map((group, gi) => (
        <div key={group.heading ?? `group-${gi}`} className="flex flex-col gap-1">
          {group.heading && (
            <div className="px-3 pb-1 text-[11px] font-bold uppercase tracking-wider text-gray-400">
              {group.heading}
            </div>
          )}
          {group.items.map((item) => {
            const Icon = item.icon
            const active = isActive(pathname, item.href)
            const showChip =
              item.gatedPlans && usage && !item.gatedPlans.includes(usage.plan)
            return (
              <Link
                key={item.href}
                href={item.href}
                prefetch
                onClick={onNavigate}
                aria-current={active ? 'page' : undefined}
                className={`flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 ${
                  active
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'text-gray-700 hover:bg-gray-100 hover:text-gray-900'
                }`}
              >
                <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
                <span className="truncate">{item.label}</span>
                {showChip && <ProChip />}
              </Link>
            )
          })}
        </div>
      ))}
    </nav>
  )
}

function PlanCard({ usage, onNavigate }: { usage: SessionUsage | null; onNavigate?: () => void }) {
  if (!usage) return null
  const planLabel = PLAN_LABELS[usage.plan] ?? usage.plan
  const showUpgrade = usage.plan !== 'elite'

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
      <div className="text-xs font-bold text-gray-900">{planLabel} plan</div>
      {/* "0 of 3 left" instead of the old "3/3", which read as 3 available. */}
      <div className="mt-0.5 text-xs text-gray-600 tabular-nums">
        {usage.sessions_remaining} of {usage.sessions_limit} sessions left
      </div>
      {showUpgrade && (
        <Link
          href="/upgrade"
          onClick={onNavigate}
          className="mt-2.5 flex min-h-9 items-center justify-center rounded-lg bg-emerald-700 px-3 text-xs font-semibold text-white transition hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 focus-visible:ring-offset-2"
        >
          Upgrade
        </Link>
      )}
    </div>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { session, status } = useSupabaseSession()
  const pathname = usePathname()
  const router = useRouter()
  const [usage, setUsage] = useState<SessionUsage | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [avatarOpen, setAvatarOpen] = useState(false)
  const avatarRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (status !== 'authenticated') {
      setUsage(null)
      return
    }
    let cancelled = false
    api
      .get('/sessions/usage')
      .then((res) => {
        if (!cancelled) setUsage(res.data)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [status])

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (avatarRef.current && !avatarRef.current.contains(e.target as Node)) {
        setAvatarOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setDrawerOpen(false)
      setAvatarOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  // Route change closes the drawer; without this a mobile tap leaves the
  // slide-over covering the page it just navigated to.
  useEffect(() => {
    setDrawerOpen(false)
  }, [pathname])

  const userEmail = session?.user?.email || ''
  const emailLocalPart = userEmail.split('@')[0]
  const userName =
    session?.user?.user_metadata?.full_name ||
    session?.user?.user_metadata?.name ||
    (emailLocalPart ? emailLocalPart[0].toUpperCase() + emailLocalPart.slice(1) : '')

  const title = pageTitle(pathname)

  const sidebarBody = (onNavigate?: () => void) => (
    <>
      <div className="px-3 py-1">
        <Link
          href="/dashboard"
          onClick={onNavigate}
          className="inline-flex rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
        >
          <SpeakOETLogo height={26} variant="full" theme="dark" priority />
        </Link>
      </div>
      <div className="mt-6 flex-1 overflow-y-auto">
        <NavLinks pathname={pathname} usage={usage} onNavigate={onNavigate} />
      </div>
      <div className="pt-4">
        <PlanCard usage={usage} onNavigate={onNavigate} />
      </div>
    </>
  )

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-gray-200 bg-white px-3 py-4 lg:flex">
        {sidebarBody()}
      </aside>

      {/* Mobile slide-over */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-gray-900/40"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-gray-200 bg-white px-3 py-4"
          >
            <button
              onClick={() => setDrawerOpen(false)}
              aria-label="Close menu"
              className="absolute right-3 top-3 rounded-lg p-2 text-gray-500 hover:bg-gray-100"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
            {sidebarBody(() => setDrawerOpen(false))}
            <div className="mt-3 flex flex-col gap-1 border-t border-gray-100 pt-3">
              <Link
                href="/profile"
                onClick={() => setDrawerOpen(false)}
                className="flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-semibold text-gray-700 hover:bg-gray-100"
              >
                <Settings className="h-[18px] w-[18px]" aria-hidden="true" />
                Settings
              </Link>
              <Link
                href="/refer"
                onClick={() => setDrawerOpen(false)}
                className="flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-semibold text-gray-700 hover:bg-gray-100"
              >
                <Gift className="h-[18px] w-[18px]" aria-hidden="true" />
                Refer &amp; Earn
              </Link>
              <Link
                href="/support"
                onClick={() => setDrawerOpen(false)}
                className="flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-semibold text-gray-700 hover:bg-gray-100"
              >
                <HelpCircle className="h-[18px] w-[18px]" aria-hidden="true" />
                Help &amp; Support
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* pb clears the mobile bottom tab bar for both content and footer. */}
      <div className="pb-14 lg:pb-0 lg:pl-60">
        {/* Top bar: page identity + account only. No nav links, no sales CTA. */}
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-gray-200 bg-white/95 px-4 backdrop-blur sm:px-6 lg:px-8">
          <button
            onClick={() => setDrawerOpen(true)}
            aria-label="Open menu"
            className="-ml-2 rounded-lg p-2 text-gray-700 hover:bg-gray-100 lg:hidden"
          >
            <Menu className="h-6 w-6" aria-hidden="true" />
          </button>

          <h1 className="truncate text-base font-bold text-gray-900">{title}</h1>

          <div className="ml-auto flex items-center gap-3">
            {status === 'loading' ? (
              <div className="h-9 w-9" />
            ) : status === 'unauthenticated' ? (
              // Reachable when a signed-out visitor lands on an app route
              // before the page's own redirect fires.
              <Link
                href="/auth/login"
                className="rounded-lg px-4 py-2 text-sm font-semibold text-[#0F2356] transition hover:bg-gray-100"
              >
                Sign In
              </Link>
            ) : (
              <div className="relative" ref={avatarRef}>
                <button
                  onClick={() => setAvatarOpen(!avatarOpen)}
                  aria-haspopup="menu"
                  aria-expanded={avatarOpen}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-[#0F2356] text-sm font-semibold text-white transition-opacity hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-[#10B981] focus:ring-offset-2"
                >
                  {getInitials(userName)}
                </button>
                {avatarOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 top-12 z-50 w-56 rounded-xl border border-gray-100 bg-white py-2 shadow-lg"
                  >
                    <div className="truncate px-4 py-2 text-sm font-semibold text-gray-900">
                      {userName}
                    </div>
                    <div className="truncate px-4 pb-2 text-xs text-gray-500">{userEmail}</div>
                    {usage && (
                      <>
                        <div className="my-1 border-t border-gray-100" />
                        <div className="px-4 py-1.5 text-xs text-gray-600 tabular-nums">
                          {PLAN_LABELS[usage.plan] ?? usage.plan} plan &middot;{' '}
                          {usage.sessions_remaining} of {usage.sessions_limit} left
                        </div>
                      </>
                    )}
                    <div className="my-1 border-t border-gray-100" />
                    <Link
                      href="/profile"
                      onClick={() => setAvatarOpen(false)}
                      className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      <Settings className="h-4 w-4" aria-hidden="true" />
                      Settings
                    </Link>
                    <Link
                      href="/refer"
                      onClick={() => setAvatarOpen(false)}
                      className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      <Gift className="h-4 w-4" aria-hidden="true" />
                      Refer &amp; Earn
                    </Link>
                    <Link
                      href="/support"
                      onClick={() => setAvatarOpen(false)}
                      className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      <HelpCircle className="h-4 w-4" aria-hidden="true" />
                      Help &amp; Support
                    </Link>
                    {/* The app shell has no footer, so this row is the only
                        in-app route to the legal pages. Keep it reachable. */}
                    <div className="my-1 border-t border-gray-100" />
                    <div className="flex items-center gap-2 px-4 py-1.5 text-[11px] text-gray-400">
                      <Link
                        href="/privacy"
                        onClick={() => setAvatarOpen(false)}
                        className="hover:text-gray-600 hover:underline"
                      >
                        Privacy
                      </Link>
                      <span aria-hidden="true">&middot;</span>
                      <Link
                        href="/terms"
                        onClick={() => setAvatarOpen(false)}
                        className="hover:text-gray-600 hover:underline"
                      >
                        Terms
                      </Link>
                    </div>
                    <div className="my-1 border-t border-gray-100" />
                    <button
                      onClick={async () => {
                        setAvatarOpen(false)
                        router.push('/')
                        await signOut()
                      }}
                      className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-rose-600 hover:bg-rose-50"
                    >
                      <LogOut className="h-4 w-4" aria-hidden="true" />
                      Sign Out
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </header>

        <main
          id="main-content"
          className="mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8"
        >
          {children}
        </main>
      </div>

      {/* Mobile bottom tabs -- primary actions in the thumb zone. */}
      <nav
        aria-label="Quick navigation"
        className="fixed bottom-0 left-0 right-0 z-40 grid grid-cols-4 border-t border-gray-200 bg-white lg:hidden"
      >
        {[
          { href: '/dashboard', label: 'Home', icon: LayoutDashboard },
          { href: '/practice/speaking', label: 'Speaking', icon: Mic },
          { href: '/practice/mock', label: 'Mock', icon: ClipboardCheck },
        ].map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href)
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? 'page' : undefined}
              className={`flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold ${
                active ? 'text-emerald-700' : 'text-gray-500'
              }`}
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
              {label}
            </Link>
          )
        })}
        <button
          onClick={() => setDrawerOpen(true)}
          aria-label="More navigation"
          className="flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold text-gray-500"
        >
          <MoreHorizontal className="h-5 w-5" aria-hidden="true" />
          More
        </button>
      </nav>
    </div>
  )
}
