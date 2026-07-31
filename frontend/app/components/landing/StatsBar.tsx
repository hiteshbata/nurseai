'use client'

import { useEffect, useState } from 'react'
import { getPlans, FALLBACK_PLANS, type Plan } from '@/lib/api'
import { useInView } from '@/app/hooks/useInView'

const fallbackProPrice = `₹${FALLBACK_PLANS.find((p) => p.id === 'pro')!.price}`

export default function StatsBar() {
  // Shows on first paint before getPlans() resolves, and stays if that call
  // fails — sourced from FALLBACK_PLANS so it can't drift from the backend
  // the way a hand-typed literal once did (shipped as ₹999 instead of ₹799).
  const [proPrice, setProPrice] = useState<string>(fallbackProPrice)
  const { ref, inView } = useInView<HTMLDivElement>()

  useEffect(() => {
    getPlans().then((plans: Plan[]) => {
      const pro = plans.find((p: Plan) => p.id === 'pro')
      if (pro) setProPrice(`₹${pro.price}`)
    }).catch(() => {})
  }, [])

  const stats = [
    { value: "9", label: "OET Criteria Scored", sub: "Every session, every time" },
    { value: proPrice, label: "Per Month", sub: "Less than one tutor hour" },
    // Value is rendered in a text-4xl/5xl tile shared with "9", "₹799", "Web" —
    // a 4-char token like these fits the 2-col mobile cell; a 7-char word like
    // "Instant" overflows it and forces horizontal scroll at 320px. "Auto"
    // keeps the no-duration benefit (feedback is automated, not timed).
    { value: "Auto", label: "Score Turnaround", sub: "No waiting on a tutor" },
    { value: "Web", label: "No App Needed", sub: "Practice in any browser" },
  ]

  return (
    <section className="bg-[#0F2356] py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div ref={ref} className="grid grid-cols-2 md:grid-cols-4 gap-0 divide-y-2 md:divide-y-0 md:divide-x divide-white/20">
          {stats.map((stat, i) => (
            <div
              key={stat.label}
              className="flex flex-col items-center text-center px-6 py-6 md:py-0 transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
              style={{
                transitionDelay: `${i * 80}ms`,
                opacity: inView ? 1 : 0,
                transform: inView ? "translateY(0)" : "translateY(12px)",
              }}
            >
              <span className="font-display text-4xl md:text-5xl font-semibold text-white mb-1">{stat.value}</span>
              <span className="text-white font-semibold text-sm mb-0.5">{stat.label}</span>
              <span className="text-white/50 text-xs">{stat.sub}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
