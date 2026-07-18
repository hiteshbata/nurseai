import { AlertCircle, Mic, MessageSquare, CheckCircle2 } from "lucide-react"

const cards = [
  {
    icon: AlertCircle,
    title: "Using Medical Jargon with Patients",
    problem:
      "Appropriateness of Language is one of the 9 OET criteria. Saying 'hypertension' instead of 'high blood pressure', or 'analgesic' instead of 'painkiller', is language a patient would not follow.",
    fix: "Use a common medical term without explaining it and the AI patient stops you: 'I'm sorry sister, what does that mean?' — so you practise plain language.",
  },
  {
    icon: Mic,
    title: "Pronunciation Patterns Affecting Scores",
    problem:
      "Intelligibility is one of the 9 OET criteria. It is not about having an accent — it is about whether individual sounds and word stress ever leave the listener unsure of what you said.",
    fix: "On the Elite plan, after each session we flag the specific words where your pronunciation affected clarity — not a generic score, but the exact words to practice.",
  },
  {
    icon: MessageSquare,
    title: "Not Addressing Patient Concerns",
    problem:
      "Understanding and incorporating the patient's perspective is one of the 9 OET criteria — did you acknowledge their fears and emotions? It is easy to focus on giving information and miss the feeling behind the question.",
    fix: "Our AI patient expresses real emotions — anxiety, confusion, fear — that you need to acknowledge, and raises its own concerns throughout the roleplay for you to pick up on.",
  },
]

export default function FailureSection() {
  return (
    <section className="bg-white py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-[#0F2356] mb-3 text-balance">
            Where Marks Go Missing in OET Speaking
          </h2>
          <p className="text-gray-500 text-lg">Three criteria worth practising — and how SpeakOET helps with each</p>
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
                    <Icon className="w-5 h-5 text-red-500" aria-hidden="true" />
                  </div>
                  <span className="inline-flex items-center bg-red-100 text-red-700 text-xs font-semibold px-3 py-1 rounded-full mt-1">
                    Where Marks Are Lost
                  </span>
                </div>

                <h3 className="text-lg font-bold text-[#0F2356] mb-3 leading-snug">{title}</h3>
                <p className="text-gray-600 text-sm leading-relaxed mb-4">{problem}</p>

                <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle2 className="w-4 h-4 text-[#10B981] shrink-0" aria-hidden="true" />
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
