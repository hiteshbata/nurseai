"use client"

import { useEffect, useState } from "react"
import { getPlans, FALLBACK_PLANS } from "@/lib/api"
import { useInView } from "@/app/hooks/useInView"

const fallbackFreeSessions = FALLBACK_PLANS.find((p) => p.id === 'free')!.sessions_limit

export default function CTASection() {
  const [freeSessions, setFreeSessions] = useState(fallbackFreeSessions)
  const { ref, inView } = useInView<HTMLDivElement>()

  useEffect(() => {
    getPlans()
      .then((plans) => {
        const free = plans.find((p) => p.id === 'free')
        if (free) setFreeSessions(free.sessions_limit)
      })
      .catch(() => {})
  }, [])

  return (
    <section className="bg-[#047857] py-16 md:py-24">
      <div
        ref={ref}
        className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
        style={{
          opacity: inView ? 1 : 0,
          transform: inView ? "translateY(0)" : "translateY(12px)",
        }}
      >
        <h2 className="font-display text-4xl md:text-5xl font-semibold text-white mb-4 text-balance">Start with {freeSessions} Free Sessions</h2>
        <p className="text-white/95 text-lg mb-8 leading-relaxed">
          No credit card. No app download. Open, speak, and get scored in minutes.
        </p>
        <a
          href="/auth/register"
          className="inline-flex items-center bg-white text-[#047857] font-bold px-8 py-4 rounded-lg text-lg hover:bg-gray-50 transition-colors shadow-lg"
        >
          Start Practicing Free — No Card Needed →
        </a>
        <p className="text-white/90 text-sm mt-5">{freeSessions} free sessions. Cancel anytime. Takes 2 minutes to set up.</p>
      </div>
    </section>
  )
}
