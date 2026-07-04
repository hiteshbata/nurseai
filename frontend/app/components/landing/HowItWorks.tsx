import { Search, Mic, BarChart2 } from "lucide-react"

const steps = [
  {
    number: "01",
    icon: Search,
    title: "Pick a Scenario",
    text: "Browse nursing roleplays by difficulty, or let AI recommend the case that targets your two weakest OET criteria today.",
    color: "navy" as const,
  },
  {
    number: "02",
    icon: Mic,
    title: "Speak with the AI Patient",
    text: "A 5-minute roleplay where the AI patient responds to what you actually say. No scripts. No awkward hold-to-speak buttons.",
    color: "emerald" as const,
  },
  {
    number: "03",
    icon: BarChart2,
    title: "Get Your Full OET Score",
    text: "All 9 criteria scored within 30 seconds. Specific feedback on what you said, what to improve, and which scenario to try next.",
    color: "navy" as const,
  },
]

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="bg-[#F8FAFC] py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-14">
          <h2 className="text-3xl md:text-4xl font-bold text-[#0F2356] mb-3 text-balance">
            One 5-Minute Roleplay, Three Layers of Feedback
          </h2>
          <p className="text-gray-500 text-lg">The same loop every time — pick, practice, get scored</p>
        </div>

        <div className="relative flex flex-col md:flex-row items-start gap-8 md:gap-0">
          {/* Connecting line on desktop */}
          <div className="hidden md:block absolute top-12 left-1/6 right-1/6 h-0.5 bg-gray-200 z-0" style={{ left: "16.67%", right: "16.67%" }} />

          {steps.map((step, i) => {
            const Icon = step.icon
            const isEmerald = step.color === "emerald"
            return (
              <div key={step.number} className="relative flex-1 flex flex-col items-center text-center px-4 z-10">
                {/* Circle number */}
                <div
                  className={`w-20 h-20 rounded-full flex items-center justify-center text-xl font-bold mb-5 shadow-lg ${
                    isEmerald
                      ? "bg-[#10B981] text-white"
                      : "bg-[#0F2356] text-white"
                  }`}
                >
                  {step.number}
                </div>

                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center mb-4 ${
                    isEmerald ? "bg-emerald-50" : "bg-blue-50"
                  }`}
                >
                  <Icon className={`w-6 h-6 ${isEmerald ? "text-[#10B981]" : "text-[#0F2356]"}`} />
                </div>

                <h3 className="text-lg font-bold text-[#0F2356] mb-2">{step.title}</h3>
                <p className="text-gray-500 text-sm leading-relaxed max-w-xs">{step.text}</p>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
