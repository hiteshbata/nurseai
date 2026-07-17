'use client'

import { useEffect, useState } from 'react'
import { getPlans, type Plan } from '@/lib/api'

export default function StatsBar() {
  // Fallback must match the real Pro price in backend core/plans.py (₹799) —
  // it shows on first paint before getPlans() resolves, and stays if that call
  // fails. A stale fallback silently advertises the wrong price.
  const [proPrice, setProPrice] = useState<string>('₹799')

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
        <div className="grid grid-cols-2 md:grid-cols-4 gap-0 divide-y-2 md:divide-y-0 md:divide-x divide-white/20">
          {stats.map((stat) => (
            <div key={stat.label} className="flex flex-col items-center text-center px-6 py-6 md:py-0">
              <span className="text-4xl md:text-5xl font-bold text-white mb-1">{stat.value}</span>
              <span className="text-white font-semibold text-sm mb-0.5">{stat.label}</span>
              <span className="text-white/50 text-xs">{stat.sub}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
