"use client"

import { useEffect, useState } from "react"
import { TrendingUp, Globe2, Check } from "lucide-react"
import { getPlans, FALLBACK_PLANS } from "@/lib/api"

const fallbackFreeSessions = FALLBACK_PLANS.find((p) => p.id === 'free')!.sessions_limit

// Real pass requirement is Grade B in all four sub-tests for nurses in every
// country below -- the regulator name is what actually varies, not the grade.
const COUNTRIES = [
  { code: "uk", label: "UK", regulator: "NMC (UK)" },
  { code: "au", label: "Australia", regulator: "NMBA (Australia)" },
  { code: "nz", label: "New Zealand", regulator: "Nursing Council (NZ)" },
] as const

export default function HeroSection() {
  const [freeSessions, setFreeSessions] = useState(fallbackFreeSessions)
  const [country, setCountry] = useState<(typeof COUNTRIES)[number]["code"]>("uk")
  // Drives the score card's one authored entrance: the progress bar fills to
  // its real value and the stat pills settle in on load, instead of sitting
  // static -- the single motion moment on the page, not a scroll-fade
  // repeated on every section below.
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    getPlans()
      .then((plans) => {
        const free = plans.find((p) => p.id === 'free')
        if (free) setFreeSessions(free.sessions_limit)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setRevealed(true)
      return
    }
    const id = requestAnimationFrame(() => setRevealed(true))
    return () => cancelAnimationFrame(id)
  }, [])

  return (
    <section className="bg-[#F8FAFC] py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col lg:flex-row items-center gap-12 lg:gap-16">
          {/* Left Side */}
          <div className="flex-1 lg:w-[55%] flex flex-col gap-6">
            {/* Badge */}
            <div className="inline-flex">
              <span className="inline-flex items-center gap-1.5 bg-[#047857] text-white text-sm font-medium px-4 py-1.5 rounded-full">
                <Globe2 className="w-3.5 h-3.5" aria-hidden="true" />
                Built for Indian Nurses
              </span>
            </div>

            {/* Headline */}
            <h1 className="font-display text-4xl md:text-5xl font-semibold text-[#0F2356] leading-tight text-balance">
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
                  <Check className="w-4 h-4 text-[#047857]" strokeWidth={3} aria-hidden="true" />
                  {badge}
                </span>
              ))}
            </div>
          </div>

          {/* Right Side — Score Card */}
          <div className="relative w-full lg:w-[45%] max-w-sm mx-auto lg:mx-0">
            {/* Ambient glow borrowed from the practice-session orb (same
                keyframe, same easing) -- ties the first thing a visitor sees
                to what the product actually feels like mid-session. */}
            <div
              aria-hidden="true"
              className="hero-orb-glow pointer-events-none absolute -inset-8 -z-10 rounded-full bg-[#10B981]/25 blur-3xl"
            />
            <div className="bg-[#0F2356] rounded-2xl shadow-premium-lg p-7 text-white">
              {/* Top */}
              <div className="flex items-start justify-between mb-3">
                <span className="inline-flex items-center gap-1.5 bg-amber-400/20 text-amber-300 text-xs font-semibold uppercase tracking-widest px-2.5 py-1 rounded-full">
                  Your Path to Band B
                </span>
                <TrendingUp className="w-5 h-5 text-[#10B981]" />
              </div>

              <p className="text-white/50 text-[11px] font-medium uppercase tracking-wide mb-1">
                Current OET Band
              </p>
              <div className="font-display text-7xl font-semibold mb-4">B</div>

              {/* Destination selector — changes the regulator/requirement below, not the band */}
              <p className="text-white/50 text-[11px] font-medium uppercase tracking-wide mb-1.5">Practising For</p>
              <div className="flex gap-1.5 mb-3" role="group" aria-label="Destination country">
                {COUNTRIES.map((c) => (
                  <button
                    key={c.code}
                    type="button"
                    onClick={() => setCountry(c.code)}
                    aria-pressed={country === c.code}
                    className={`flex-1 text-xs font-medium px-2 py-1.5 rounded-lg transition-colors ${
                      country === c.code
                        ? "bg-[#10B981] text-white"
                        : "bg-white/10 text-white/60 hover:bg-white/20"
                    }`}
                  >
                    {c.label}
                  </button>
                ))}
              </div>

              {/* Requirement — real, changes with destination */}
              <p className="text-white/50 text-[11px] font-medium uppercase tracking-wide mb-1.5">Requirement</p>
              <div className="flex items-center gap-2 mb-4">
                <Check className="w-4 h-4 text-[#10B981] shrink-0" strokeWidth={3} aria-hidden="true" />
                <span className="text-sm font-semibold">
                  {COUNTRIES.find((c) => c.code === country)!.regulator}: Band B in all four skills
                </span>
              </div>

              {/* Progress */}
              <div className="mb-5">
                <p className="text-white/50 text-[11px] font-medium uppercase tracking-wide mb-1.5">
                  Learning Progress
                </p>
                <div className="flex items-center gap-1.5 text-xs mb-2">
                  <span className="text-white/60">Start C</span>
                  <span className="text-white/30">→</span>
                  <span className="text-[#10B981] font-semibold">Current B</span>
                </div>
                <div className="w-full bg-white/20 rounded-full h-2.5">
                  <div
                    className="h-2.5 rounded-full bg-[#10B981] transition-[width] duration-[1100ms] ease-[cubic-bezier(0.16,1,0.3,1)]"
                    style={{ width: revealed ? "100%" : "0%" }}
                  />
                </div>
              </div>

              {/* Stats pills */}
              <div className="flex gap-2 mb-5">
                {[
                  { label: "Speaking", value: "4.6" },
                  { label: "Writing", value: "4.2" },
                  { label: "Sessions", value: "24" },
                ].map((stat, i) => (
                  <div
                    key={stat.label}
                    className="flex-1 bg-white/10 rounded-xl px-3 py-2 text-center transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
                    style={{
                      transitionDelay: `${300 + i * 90}ms`,
                      opacity: revealed ? 1 : 0,
                      transform: revealed ? "translateY(0)" : "translateY(6px)",
                    }}
                  >
                    <div className="text-lg font-bold">{stat.value}</div>
                    <div className="text-white/60 text-xs">{stat.label}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
