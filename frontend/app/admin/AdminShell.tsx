'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { ErrorBoundary } from '@/components/ErrorBoundary'

// Matches backend/app/routers/admin.py's ROLE_RANK -- any staff tier
// (support and up) gets past the front door; per-page/per-action floors
// are still enforced server-side by each endpoint's own require_*() dep.
const STAFF_ROLES = new Set(['support', 'analyst', 'admin', 'owner'])

const NAV_GROUPS = [
  {
    label: 'Overview',
    items: [{ href: '/admin', label: 'Dashboard' }],
  },
  {
    label: 'Content',
    items: [
      { href: '/admin/scenarios', label: 'Scenarios' },
      { href: '/admin/reading', label: 'Reading' },
      { href: '/admin/writing', label: 'Writing' },
      { href: '/admin/listening', label: 'Listening' },
      { href: '/admin/mock-tests', label: 'Mock Tests' },
      { href: '/admin/scenario-generator', label: 'Generator' },
    ],
  },
  {
    label: 'Users',
    items: [
      { href: '/admin/users', label: 'Users' },
      { href: '/admin/audit-log', label: 'Action History' },
    ],
  },
  {
    label: 'AI',
    items: [
      { href: '/admin/ai-models', label: 'AI Models' },
    ],
  },
  {
    label: 'Revenue',
    items: [
      { href: '/admin/ai-costs', label: 'AI Cost & Margin' },
      { href: '/admin/failed-payments', label: 'Failed Payments' },
      { href: '/admin/coupons', label: 'Coupons' },
      { href: '/admin/expiring-soon', label: 'Expiring Soon' },
    ],
  },
  {
    label: 'System',
    items: [
      { href: '/admin/logs', label: 'Error Logs' },
      { href: '/admin/settings', label: 'Settings' },
    ],
  },
]

export default function AdminShell({ children }: { children: React.ReactNode }) {
  const { session, status } = useSupabaseSession()
  const pathname = usePathname()
  const router = useRouter()
  const [unresolvedCount, setUnresolvedCount] = useState(0)
  const [roleStatus, setRoleStatus] = useState<'checking' | 'staff' | 'denied'>('checking')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const mobileNavPanelRef = useRef<HTMLDivElement>(null)
  const mobileNavTriggerRef = useRef<HTMLButtonElement>(null)

  // Dialog semantics for the mobile drawer: trap focus inside it, close on
  // Escape, and hand focus back to the trigger button when it closes.
  useEffect(() => {
    if (!mobileNavOpen) return

    const panel = mobileNavPanelRef.current
    const focusable = panel?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
    focusable?.[0]?.focus()

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMobileNavOpen(false)
        return
      }
      if (e.key !== 'Tab' || !focusable || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      mobileNavTriggerRef.current?.focus()
    }
  }, [mobileNavOpen])

  useEffect(() => {
    if (status === 'loading') return
    if (!session?.user) {
      router.push('/auth/login')
      return
    }

    let cancelled = false
    api.get('/auth/me')
      .then((res) => {
        if (cancelled) return
        if (STAFF_ROLES.has(res.data?.role)) {
          setRoleStatus('staff')
        } else {
          setRoleStatus('denied')
          toast.error('Staff access required')
          router.push('/dashboard')
        }
      })
      .catch(() => {
        if (cancelled) return
        setRoleStatus('denied')
        toast.error('Staff access required')
        router.push('/dashboard')
      })

    return () => {
      cancelled = true
    }
  }, [status, session, router])

  useEffect(() => {
    if (roleStatus !== 'staff') return

    const fetchCount = async () => {
      try {
        const res = await api.get('/admin/logs/unresolved-count')
        setUnresolvedCount(res.data?.count || 0)
      } catch {
        setUnresolvedCount(0)
      }
    }

    fetchCount()
    const interval = setInterval(fetchCount, 30_000)
    return () => clearInterval(interval)
  }, [roleStatus])

  if (status === 'loading' || roleStatus === 'checking') {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading...</div>
      </div>
    )
  }

  if (!session?.user || roleStatus !== 'staff') return null

  const renderNavGroups = (onNavigate?: () => void) =>
    NAV_GROUPS.map((group) => (
      <div key={group.label} className="mb-6">
        <div className="px-3 mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {group.label}
        </div>
        {group.items.map((item) => {
          const isActive = pathname === item.href ||
            (item.href !== '/admin' && pathname.startsWith(item.href))
          return (
            <Link
              key={item.href}
              href={item.href}
              prefetch={true}
              onClick={onNavigate}
              className={`flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm font-medium transition ${
                isActive
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-blue-600'
              }`}
            >
              {item.label}
              {item.href === '/admin/logs' && unresolvedCount > 0 && (
                <span className="bg-red-500 text-white text-xs font-bold min-w-[20px] h-5 px-1.5 flex items-center justify-center rounded-full">
                  {unresolvedCount}
                </span>
              )}
            </Link>
          )
        })}
      </div>
    ))

  return (
    <div className="min-h-screen bg-gray-50 md:flex">
      {/* Mobile top bar */}
      <div className="md:hidden bg-white shadow-md sticky top-0 z-40 flex items-center justify-between px-4 py-3">
        <Link href="/admin" className="text-lg font-bold text-blue-600">
          SpeakOET Admin
        </Link>
        <button
          ref={mobileNavTriggerRef}
          onClick={() => setMobileNavOpen(true)}
          aria-label="Open admin menu"
          className="text-gray-600 border border-gray-300 rounded-md px-3 py-1.5 text-sm font-medium"
        >
          Menu
        </button>
      </div>

      {/* Mobile drawer */}
      {mobileNavOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-black/40"
            onClick={() => setMobileNavOpen(false)}
          />
          <div
            ref={mobileNavPanelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Admin menu"
            className="relative w-64 bg-white shadow-xl h-full overflow-y-auto p-4"
          >
            <div className="flex items-center justify-between mb-4">
              <Link href="/admin" className="text-lg font-bold text-blue-600" onClick={() => setMobileNavOpen(false)}>
                SpeakOET Admin
              </Link>
              <button
                onClick={() => setMobileNavOpen(false)}
                aria-label="Close admin menu"
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
              >
                &times;
              </button>
            </div>
            {renderNavGroups(() => setMobileNavOpen(false))}
            <Link
              href="/"
              className="block px-3 py-2 text-sm text-muted-foreground hover:text-gray-600 transition"
            >
              Back to Site
            </Link>
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <nav className="hidden md:flex md:flex-col md:w-60 md:shrink-0 md:h-screen md:sticky md:top-0 bg-white shadow-md overflow-y-auto p-4">
        <Link href="/admin" className="text-xl font-bold text-blue-600 px-3 mb-6 block">
          SpeakOET Admin
        </Link>
        {renderNavGroups()}
        <div className="mt-auto pt-4 border-t border-gray-100">
          <Link
            href="/"
            className="block px-3 py-2 text-sm text-muted-foreground hover:text-gray-600 transition"
          >
            Back to Site
          </Link>
        </div>
      </nav>

      <div className="flex-1 min-w-0">
        <ErrorBoundary>{children}</ErrorBoundary>
      </div>
    </div>
  )
}
