'use client'

import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter, usePathname } from 'next/navigation'
import { supabase, signOut, useSupabaseSession } from '@/lib/supabase'
import { LayoutDashboard, Settings, LogOut } from 'lucide-react'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'
import api from '@/lib/api'

const landingNavLinks = [
  { href: '#how-it-works', label: 'How It Works' },
  { href: '#features', label: 'Features' },
  { href: '#pricing', label: 'Pricing' },
]

const appNavLinks = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/practice/speaking', label: 'Speaking' },
]

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
  const router = useRouter()
  const pathname = usePathname()
  const isLanding = pathname === '/'

  const getInitials = (name: string) => {
    const parts = name.trim().split(' ')
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    }
    return parts[0].slice(0, 2).toUpperCase()
  }

  const userName = session?.user?.user_metadata?.full_name || session?.user?.email || ''
  const userEmail = session?.user?.email || ''

  const [usage, setUsage] = useState<SessionUsage | null>(null)

  useEffect(() => {
    if (status !== 'authenticated') {
      setUsage(null)
      return
    }
    let cancelled = false
    api.get('/sessions/usage').then((res) => {
      if (!cancelled) setUsage(res.data)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [status])

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

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 10)
    window.addEventListener('scroll', handler)
    return () => window.removeEventListener('scroll', handler)
  }, [])

  const navLinks = [
    { href: '/dashboard', label: 'Dashboard' },
    { href: '/practice/speaking', label: 'Speaking' },
  ]

  const PlanUsagePill = ({ onNavigate }: { onNavigate?: () => void }) => {
    if (!usage) return null
    return (
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center whitespace-nowrap rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
          {planLabel} &middot; {usage.sessions_used}/{usage.sessions_limit} sessions
        </span>
        {showUpgrade && (
          <Link
            href="/upgrade"
            onClick={onNavigate}
            className="rounded-full bg-[#10B981] px-3 py-1 text-xs font-semibold text-white hover:opacity-90 transition whitespace-nowrap"
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
      className={`sticky top-0 z-50 bg-white border-b border-gray-100 transition-shadow duration-200 ${scrolled ? 'shadow-md' : ''}`}
    >
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <Link href="/">
          <SpeakOETLogo height={28} variant="full" theme="dark" />
        </Link>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-6">
          {(isLanding && !session ? landingNavLinks : appNavLinks).map((link: any) =>
            link.disabled ? (
              <span
                key={link.href}
                className="text-gray-400 cursor-not-allowed text-sm font-semibold transition"
                title="Coming Soon"
              >
                {link.label}
              </span>
            ) : (
              <Link
                key={link.href}
                href={link.href}
                prefetch={true}
                className="text-gray-700 hover:text-blue-600 transition text-sm font-semibold"
              >
                {link.label}
              </Link>
            )
          )}
        </div>

        <div className="flex items-center gap-3">
          {status === 'loading' ? (
            <div className="w-24 h-9" />
          ) : status === 'authenticated' ? (
            <>
              <div className="hidden sm:flex">
                <PlanUsagePill />
              </div>
              <div className="relative" ref={avatarRef}>
              <button
                onClick={() => setAvatarOpen(!avatarOpen)}
                className="w-9 h-9 rounded-full bg-[#0F2356] text-white text-sm font-semibold flex items-center justify-center hover:opacity-90 transition-opacity focus:outline-none focus:ring-2 focus:ring-[#10B981] focus:ring-offset-2"
              >
                {getInitials(userName)}
              </button>
              {avatarOpen && (
                <div className="absolute right-0 top-12 z-50 w-48 bg-white rounded-xl shadow-lg border border-gray-100 py-2">
                  <div className="px-4 py-2 font-semibold text-sm text-gray-900 truncate">
                    {userName}
                  </div>
                  <div className="px-4 pb-2 text-xs text-gray-500 truncate">
                    {userEmail}
                  </div>
                  {usage && (
                    <div className="px-4 pb-2 flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-gray-600">
                        {planLabel} plan &middot; {usage.sessions_used}/{usage.sessions_limit} sessions
                      </span>
                      {showUpgrade && (
                        <Link
                          href="/upgrade"
                          onClick={() => setAvatarOpen(false)}
                          className="text-xs font-semibold text-[#10B981] hover:underline whitespace-nowrap"
                        >
                          Upgrade
                        </Link>
                      )}
                    </div>
                  )}
                  <div className="border-t border-gray-100 my-1" />
                  <Link
                    href="/dashboard"
                    onClick={() => setAvatarOpen(false)}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    <LayoutDashboard className="h-4 w-4" />
                    Dashboard
                  </Link>
                  <Link
                    href="/profile"
                    onClick={() => setAvatarOpen(false)}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    <Settings className="h-4 w-4" />
                    Settings
                  </Link>
                  <div className="border-t border-gray-100 my-1" />
                  <button
                    onClick={() => { setAvatarOpen(false); signOut(); router.push('/') }}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-rose-600 hover:bg-rose-50 w-full text-left"
                  >
                    <LogOut className="h-4 w-4" />
                    Sign Out
                  </button>
                </div>
              )}
              </div>
            </>
          ) : isLanding ? (
            <>
              <Link
                href="/auth/register"
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition"
                style={{ backgroundColor: "#10B981" }}
              >
                Get Started
              </Link>
              <Link
                href="/auth/login"
                className="text-sm font-semibold px-3 py-2 rounded transition"
                style={{ color: "#0F2356" }}
              >
                Sign In
              </Link>
            </>
          ) : (
            <>
              <Link href="/auth/login" className="text-sm text-blue-600 font-semibold hover:bg-blue-50 px-3 py-2 rounded transition">
                Sign In
              </Link>
              <Link href="/auth/register" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 transition">
                Sign Up
              </Link>
            </>
          )}

          {/* Hamburger */}
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden p-2 text-gray-700 hover:bg-gray-100 rounded-lg"
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
          mobileOpen ? 'max-h-96 border-b border-gray-100 shadow-sm' : 'max-h-0'
        }`}
      >
        <div className="px-4 py-2 bg-white">
          {session && usage && (
            <div className="sm:hidden flex items-center justify-between gap-2 py-3 border-b border-gray-100 mb-1">
              <span className="inline-flex items-center whitespace-nowrap rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">
                {planLabel} &middot; {usage.sessions_used}/{usage.sessions_limit} sessions
              </span>
              {showUpgrade && (
                <Link
                  href="/upgrade"
                  onClick={() => setMobileOpen(false)}
                  className="rounded-full bg-[#10B981] px-3 py-1 text-xs font-semibold text-white hover:opacity-90 transition whitespace-nowrap"
                >
                  Upgrade
                </Link>
              )}
            </div>
          )}
          {(isLanding && !session ? landingNavLinks : appNavLinks).map((link: any) =>
            link.disabled ? (
              <span
                key={link.href}
                className="block py-2 text-gray-400 cursor-not-allowed text-sm"
                title="Coming Soon"
              >
                {link.label} <span className="text-xs text-amber-500">(Coming Soon)</span>
              </span>
            ) : (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className="block py-2 text-gray-700 hover:text-blue-600 transition text-sm"
              >
                {link.label}
              </Link>
            )
          )}
          {status !== 'loading' && !session && (
            <>
              <Link href="/auth/login" onClick={() => setMobileOpen(false)} className="block py-2 text-gray-700 hover:text-blue-600 transition text-sm">
                Sign In
              </Link>
              <Link href="/auth/register" onClick={() => setMobileOpen(false)} className="block py-2 text-blue-600 font-semibold text-sm">
                Sign Up
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  )
}
