'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { supabase, signOut, getCurrentSession } from '@/lib/supabase'
import type { Session } from '@supabase/supabase-js'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'

export function Navbar() {
  const [session, setSession] = useState<Session | null>(null)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const router = useRouter()

  useEffect(() => {
    getCurrentSession().then((s) => setSession(s))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s)
    })
    return () => subscription?.unsubscribe()
  }, [])

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 10)
    window.addEventListener('scroll', handler)
    return () => window.removeEventListener('scroll', handler)
  }, [])

  const navLinks = [
    { href: '/dashboard', label: 'Dashboard' },
    { href: '/practice/speaking', label: 'Speaking' },
    { href: '/practice/writing', label: 'Writing', disabled: true },
    { href: '/mock-test', label: 'Mock Test', disabled: true },
  ]

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
          {session && navLinks.map((link) =>
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
                className="text-gray-700 hover:text-blue-600 transition text-sm font-semibold"
              >
                {link.label}
              </Link>
            )
          )}
        </div>

        <div className="flex items-center gap-3">
          {session ? (
            <>
              <span className="hidden md:inline text-sm text-gray-700">
                {session.user?.user_metadata?.name || session.user?.email}
              </span>
              <button
                onClick={() => { signOut(); router.push('/') }}
                className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-semibold hover:bg-gray-800 hover:text-white hover:border-gray-800 transition"
              >
                Sign Out
              </button>
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
          {session && navLinks.map((link) =>
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
          {!session && (
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
