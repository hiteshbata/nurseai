"use client"

import { useEffect, useState } from "react"
import { TrendingUp } from "lucide-react"
import { getPlans } from "@/lib/api"

export default function HeroSection() {
  const [freeSessions, setFreeSessions] = useState(3)

  useEffect(() => {
    getPlans()
      .then((plans) => {
        const free = plans.find((p) => p.id === 'free')
        if (free) setFreeSessions(free.sessions_limit)
      })
      .catch(() => {})
  }, [])

  return (
    <section className="bg-[#F8FAFC] py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col lg:flex-row items-center gap-12 lg:gap-16">
          {/* Left Side */}
          <div className="flex-1 lg:w-[55%] flex flex-col gap-6">
            {/* Badge */}
            <div className="inline-flex">
              <span className="bg-[#047857] text-white text-sm font-medium px-4 py-1.5 rounded-full">
                🌏 Built for Indian Nurses
              </span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl md:text-5xl font-bold text-[#0F2356] leading-tight text-balance">
              Practice OET Speaking
              <br />
              with an AI patient that responds
            </h1>

            {/* Subtext */}
            <p className="text-lg text-gray-500 leading-relaxed max-w-xl">
              Real-time roleplay, instant 9-criteria feedback, and AI coaching designed for Indian nurses going to
              Australia, UK, and New Zealand.
            </p>

            {/* Buttons */}
            <div className="flex flex-col sm:flex-row gap-3">
              <a
                href="/auth/register"
                className="inline-flex items-center justify-center bg-[#047857] text-white font-semibold px-6 py-3 rounded-lg hover:bg-[#036546] transition-colors"
              >
                Start Free — {freeSessions} Sessions on Us
              </a>
              <a
                href="#how-it-works"
                className="inline-flex items-center justify-center bg-white text-[#0F2356] font-semibold px-6 py-3 rounded-lg border-2 border-[#0F2356] hover:bg-[#0F2356] hover:text-white transition-colors"
              >
                See How It Works
              </a>
            </div>

            {/* Trust badges */}
            <div className="flex flex-col sm:flex-row gap-3 sm:gap-6 mt-2">
              {["No app download", "No credit card", "Web-based, practice anywhere"].map((badge) => (
                <span key={badge} className="flex items-center gap-1.5 text-sm text-gray-500">
                  <span className="text-[#047857] font-bold">✓</span>
                  {badge}
                </span>
              ))}
            </div>

            {/* Social proof */}
            <p className="text-sm text-gray-500 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#10B981] inline-block animate-pulse" />
              Join <span className="font-bold text-[#0F2356]">847</span> Indian nurses already practicing daily
            </p>
          </div>

          {/* Right Side — Score Card */}
          <div className="w-full lg:w-[45%] max-w-sm mx-auto lg:mx-0">
            <div className="bg-[#0F2356] rounded-2xl shadow-2xl p-7 text-white">
              {/* Top */}
              <div className="flex items-start justify-between mb-2">
                <span className="text-white/60 text-xs font-medium uppercase tracking-widest">Your OET Band</span>
                <TrendingUp className="w-5 h-5 text-[#10B981]" />
              </div>

              <div className="text-7xl font-bold mb-6">B</div>

              {/* Progress */}
              <div className="mb-5">
                <div className="flex items-center justify-between text-xs text-white/60 mb-2">
                  <span>Start C</span>
                  <span className="text-[#10B981] font-semibold text-sm">Now B</span>
                  <span>Target A</span>
                </div>
                <div className="w-full bg-white/20 rounded-full h-2.5">
                  <div
                    className="h-2.5 rounded-full bg-[#10B981]"
                    style={{ width: "70%" }}
                  />
                </div>
              </div>

              {/* Stats pills */}
              <div className="flex gap-2 mb-5">
                {[
                  { label: "Speaking", value: "4.6" },
                  { label: "Writing", value: "4.2" },
                  { label: "Sessions", value: "24" },
                ].map((stat) => (
                  <div key={stat.label} className="flex-1 bg-white/10 rounded-xl px-3 py-2 text-center">
                    <div className="text-lg font-bold">{stat.value}</div>
                    <div className="text-white/60 text-xs">{stat.label}</div>
                  </div>
                ))}
              </div>

              {/* Last session */}
              <p className="text-white/50 text-xs text-center">Last session: 2 hours ago</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
