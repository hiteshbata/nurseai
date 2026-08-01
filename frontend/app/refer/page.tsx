'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useSupabaseSession } from '@/lib/supabase'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Gift, Copy, Check, Users, Sparkles, Loader2 } from 'lucide-react'
import { RevealOnScroll } from '@/components/RevealOnScroll'

interface ReferralInfo {
  referral_code: string
  referral_link: string
  bonus_sessions: number
  referred_count: number
  rewarded_count: number
}

export default function ReferPage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [info, setInfo] = useState<ReferralInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      api.get('/referrals/me')
        .then((res) => setInfo(res.data))
        .catch(() => toast.error('Could not load your referral link'))
        .finally(() => setLoading(false))
    }
  }, [status, router])

  const handleCopy = async () => {
    if (!info) return
    await navigator.clipboard.writeText(info.referral_link)
    setCopied(true)
    toast.success('Link copied')
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mb-8 motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
          Refer &amp; Earn
        </h1>

        {loading || !info ? (
          <div className="flex items-center justify-center gap-2 bg-white rounded-2xl border border-gray-100 shadow-premium p-10 text-center text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
            Loading your referral link…
          </div>
        ) : (
          <>
            <RevealOnScroll>
              <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#0F2356] to-[#1A3A73] shadow-premium-lg p-8 mb-6">
                <div
                  className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-emerald-400/20 blur-2xl"
                  aria-hidden="true"
                />
                <div className="relative flex flex-col items-center text-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white/10">
                    <Gift className="h-6 w-6 text-emerald-300" aria-hidden="true" />
                  </div>
                  <h2 className="font-display text-2xl font-semibold text-white text-balance">
                    Give 1 free session. Get 1 free session.
                  </h2>
                  <p className="max-w-sm text-sm leading-relaxed text-white/70">
                    Share your link. Once a friend joins and completes their first speaking
                    session, you both get a bonus session — no code needed, it happens
                    automatically.
                  </p>

                  <div className="mt-3 w-full rounded-xl bg-white/10 px-4 py-3 text-center font-mono text-xl font-semibold tracking-[0.3em] text-white">
                    {info.referral_code}
                  </div>

                  <div className="mt-2 flex w-full items-center gap-2">
                    <input
                      readOnly
                      value={info.referral_link}
                      aria-label="Your referral link"
                      className="h-11 flex-1 truncate rounded-xl border border-white/10 bg-white/5 px-3.5 text-sm text-white/90 outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
                    />
                    <button
                      onClick={handleCopy}
                      className="flex h-11 shrink-0 items-center gap-1.5 rounded-xl bg-emerald-500 px-4 text-sm font-semibold text-white shadow-sm motion-safe:transition-all motion-safe:duration-150 hover:bg-emerald-600 active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0F2356]"
                    >
                      {copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
                      {copied ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                </div>
              </div>
            </RevealOnScroll>

            <RevealOnScroll delayMs={80}>
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-white rounded-2xl border border-gray-100 shadow-premium p-5 text-center">
                  <Sparkles className="mx-auto mb-2 h-5 w-5 text-emerald-500" aria-hidden="true" />
                  <p className="text-2xl font-bold text-[#0F2356]">{info.bonus_sessions}</p>
                  <p className="text-xs font-medium text-gray-500">Bonus sessions</p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-100 shadow-premium p-5 text-center">
                  <Users className="mx-auto mb-2 h-5 w-5 text-blue-500" aria-hidden="true" />
                  <p className="text-2xl font-bold text-[#0F2356]">{info.referred_count}</p>
                  <p className="text-xs font-medium text-gray-500">Friends joined</p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-100 shadow-premium p-5 text-center">
                  <Gift className="mx-auto mb-2 h-5 w-5 text-amber-500" aria-hidden="true" />
                  <p className="text-2xl font-bold text-[#0F2356]">{info.rewarded_count}</p>
                  <p className="text-xs font-medium text-gray-500">Rewarded</p>
                </div>
              </div>
            </RevealOnScroll>
          </>
        )}
      </div>
    </div>
  )
}
