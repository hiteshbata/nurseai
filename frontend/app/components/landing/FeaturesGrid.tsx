import { Bot, BarChart2, TrendingUp, Heart, Zap, Globe } from "lucide-react"

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
    title: "30-Second Score Delivery",
    text: "No waiting. Full examiner-style feedback appears within 30 seconds of ending your session.",
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
  return (
    <section id="features" className="bg-white py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-[#0F2356] text-balance">
            Everything You Need to Pass OET
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map(({ icon: Icon, title, text, accent }) => {
            const isEmerald = accent === "emerald"
            return (
              <div
                key={title}
                className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 hover:shadow-md transition-shadow"
              >
                <div
                  className={`w-11 h-11 rounded-xl flex items-center justify-center mb-4 ${
                    isEmerald ? "bg-emerald-50" : "bg-[#0F2356]/5"
                  }`}
                >
                  <Icon className={`w-5 h-5 ${isEmerald ? "text-[#10B981]" : "text-[#0F2356]"}`} />
                </div>
                <h3 className="text-base font-bold text-[#0F2356] mb-2">{title}</h3>
                <p className="text-gray-500 text-sm leading-relaxed">{text}</p>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
