import { AlertCircle, Mic, MessageSquare, CheckCircle2 } from "lucide-react"

const cards = [
  {
    icon: AlertCircle,
    title: "Using Medical Jargon with Patients",
    problem:
      "Examiners mark you down when you say 'hypertension' instead of 'high blood pressure' or 'analgesic' instead of 'painkiller'. Patients don't understand medical terms.",
    fix: "Our AI patient interrupts you the moment you use medical jargon and asks: 'I'm sorry sister, what does that mean?' — forcing you to practice plain language every time.",
  },
  {
    icon: Mic,
    title: "Pronunciation Patterns Affecting Scores",
    problem:
      "Indian accents have specific patterns that affect OET Intelligibility scores — mixing V and W sounds, TH sounds, and word stress patterns that Australian and UK examiners notice.",
    fix: "After each session we flag the specific words where your pronunciation affected clarity — not a generic score, but the exact words to practice.",
  },
  {
    icon: MessageSquare,
    title: "Not Addressing Patient Concerns",
    problem:
      "OET examiners score heavily on Patient Perspective — did you acknowledge the patient's fears and emotions? Most nurses focus on information giving and forget to listen.",
    fix: "Our AI patient expresses real emotions — anxiety, confusion, fear — that you must respond to. Miss them and the AI will repeat the concern until you address it.",
  },
]

export default function FailureSection() {
  return (
    <section className="bg-white py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-[#0F2356] mb-3 text-balance">
            Why Indian Nurses Fail OET Speaking
          </h2>
          <p className="text-gray-500 text-lg">And how SpeakOET fixes each one</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {cards.map(({ icon: Icon, title, problem, fix }) => (
            <div
              key={title}
              className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden border-l-4 border-l-red-500"
            >
              <div className="p-6">
                <div className="flex items-start gap-4 mb-4">
                  <div className="shrink-0 w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
                    <Icon className="w-5 h-5 text-red-500" />
                  </div>
                  <span className="inline-flex items-center bg-red-100 text-red-700 text-xs font-semibold px-3 py-1 rounded-full mt-1">
                    Common Failure Reason
                  </span>
                </div>

                <h3 className="text-lg font-bold text-[#0F2356] mb-3 leading-snug">{title}</h3>
                <p className="text-gray-600 text-sm leading-relaxed mb-4">{problem}</p>

                <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle2 className="w-4 h-4 text-[#10B981] shrink-0" />
                    <span className="text-sm font-bold text-[#0F2356]">SpeakOET Fix:</span>
                  </div>
                  <p className="text-sm text-gray-700 leading-relaxed">{fix}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
