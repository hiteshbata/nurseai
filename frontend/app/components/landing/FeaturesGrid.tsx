"use client"

import { Bot, BarChart2, TrendingUp, Heart, Zap, Globe } from "lucide-react"
import { useInView } from "@/app/hooks/useInView"

const features = [
  {
    icon: Bot,
    title: "AI Patient That Interrupts",
    text: "Use a common medical term without explaining it and the AI patient stops to ask what it means — just like a real patient would.",
    accent: "emerald",
  },
  {
    icon: BarChart2,
    title: "Full 9-Criteria OET Scoring",
    text: "Scored on all 9 OET Speaking criteria — 5 Clinical Communication + 4 Linguistic, with a band letter and detailed feedback.",
    accent: "navy",
  },
  {
    icon: TrendingUp,
    title: "Band Score Progress Tracking",
    text: "Visual journey from your baseline grade to your target — see improvement across every session you complete.",
    accent: "emerald",
  },
  {
    icon: Heart,
    title: "Clinical Communication Training",
    text: "Practice relationship building, patient perspective, and information giving — the criteria most Indian nurses fail on.",
    accent: "navy",
  },
  {
    icon: Zap,
    title: "Instant Score Delivery",
    text: "No waiting on a tutor — your full examiner-style feedback appears as soon as you end the session.",
    accent: "emerald",
  },
  {
    icon: Globe,
    title: "No App Download Required",
    text: "Fully web-based. Open Chrome or Safari on any device and start practicing — phone, tablet, or laptop.",
    accent: "navy",
  },
]

export default function FeaturesGrid() {
  const { ref, inView } = useInView<HTMLDivElement>()

  return (
    <section id="features" className="bg-white py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-14">
          <h2 className="font-display text-3xl md:text-4xl font-semibold text-[#0F2356] text-balance">
            Everything You Need to Pass OET
          </h2>
        </div>

        {/* A plain divided list, not another grid of bordered cards -- the
            page already leans on the rounded-card-with-shadow container for
            things that need a boundary (comparisons, panels). Six identical
            icon-heading-text boxes here would just repeat that container as
            page structure. */}
        <div ref={ref} className="grid grid-cols-1 md:grid-cols-2 gap-x-14 gap-y-10">
          {features.map(({ icon: Icon, title, text, accent }, i) => {
            const isEmerald = accent === "emerald"
            return (
              <div
                key={title}
                className="flex gap-4 transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
                style={{
                  transitionDelay: `${i * 80}ms`,
                  opacity: inView ? 1 : 0,
                  transform: inView ? "translateY(0)" : "translateY(12px)",
                }}
              >
                <Icon
                  className={`w-6 h-6 shrink-0 mt-0.5 ${isEmerald ? "text-[#10B981]" : "text-[#0F2356]"}`}
                  strokeWidth={1.75}
                  aria-hidden="true"
                />
                <div>
                  <h3 className="text-base font-bold text-[#0F2356] mb-1.5">{title}</h3>
                  <p className="text-gray-500 text-sm leading-relaxed">{text}</p>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
