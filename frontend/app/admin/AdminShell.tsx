'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import toast from 'react-hot-toast'

// Matches backend/app/routers/admin.py's ROLE_RANK -- any staff tier
// (support and up) gets past the front door; per-page/per-action floors
// are still enforced server-side by each endpoint's own require_*() dep.
const STAFF_ROLES = new Set(['support', 'analyst', 'admin', 'owner'])

const NAV_ITEMS = [
  { href: '/admin', label: 'Dashboard' },
  { href: '/admin/users', label: 'Users' },
  { href: '/admin/scenarios', label: 'Scenarios' },
  { href: '/admin/audit-log', label: 'Action History' },
  { href: '/admin/ai-costs', label: 'AI Cost & Margin' },
  { href: '/admin/failed-payments', label: 'Failed Payments' },
  { href: '/admin/expiring-soon', label: 'Expiring Soon' },
  { href: '/admin/scenario-generator', label: 'Generator' },
  { href: '/admin/logs', label: 'Error Logs' },
  { href: '/admin/settings', label: 'Settings' },
]

export default function AdminShell({ children }: { children: React.ReactNode }) {
  const { session, status } = useSupabaseSession()
  const pathname = usePathname()
  const router = useRouter()
  const [unresolvedCount, setUnresolvedCount] = useState(0)
  const [roleStatus, setRoleStatus] = useState<'checking' | 'staff' | 'denied'>('checking')

  useEffect(() => {
    // Hide main site navbar on admin pages
    const mainNav = document.querySelector('#main-navbar')
    if (mainNav) (mainNav as HTMLElement).style.display = 'none'
    return () => {
      if (mainNav) (mainNav as HTMLElement).style.display = ''
    }
  }, [])

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

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/admin" className="text-xl font-bold text-blue-600">
            SpeakOET Admin
          </Link>
          <div className="hidden md:flex items-center gap-6">
            {NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href ||
                (item.href !== '/admin' && pathname.startsWith(item.href))
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  prefetch={true}
                  className={`text-sm font-semibold transition flex items-center gap-1.5 ${
                    isActive ? 'text-blue-600' : 'text-gray-600 hover:text-blue-600'
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
          <Link
            href="/"
            className="text-sm text-gray-400 hover:text-gray-600 transition"
          >
            Back to Site
          </Link>
        </div>
      </nav>
      {children}
    </div>
  )
}
