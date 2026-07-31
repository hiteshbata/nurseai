'use client'

import { useEffect, useState } from "react"
import { ChevronDown } from "lucide-react"
import { getPlans, FALLBACK_PLANS, type Plan } from "@/lib/api"
import { useInView } from "@/app/hooks/useInView"

export default function FAQSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  const [plans, setPlans] = useState<Plan[]>(FALLBACK_PLANS)
  const { ref, inView } = useInView<HTMLDivElement>()

  useEffect(() => {
    getPlans().then(setPlans).catch(() => {})
  }, [])

  const pro = plans.find((p) => p.id === 'pro')!
  const free = plans.find((p) => p.id === 'free')!

  const faqs = [
    {
      q: "Is SpeakOET an official OET product?",
      a: "No. SpeakOET is an independent AI practice tool for nurses. OET is a registered trademark of Cambridge Boxhill Language Assessment. We are not affiliated with or endorsed by OET — we built our scoring around the official public rubric.",
    },
    {
      q: "How accurate is the AI scoring?",
      a: "SpeakOET evaluates your responses using all 9 public OET Speaking assessment criteria. It is designed as a study tool and cannot guarantee any exam result — it is not a substitute for the real exam.",
    },
    {
      q: "Do I need to download an app?",
      a: "No. SpeakOET is completely web-based. Open it in Chrome or Safari on any device and start practicing immediately. No App Store, no installation.",
    },
    {
      q: "What is included in the free plan?",
      a: `The free plan gives you ${free.sessions_limit} speaking sessions per month with full 9-criteria feedback. No credit card required to start.`,
    },
    {
      q: "How much does Pro cost?",
      a: `Pro is ₹${pro.price} per month — about US$${Math.round(pro.price / 83)}. That is significantly less than one hour with a human OET tutor. You get ${pro.sessions_limit} speaking scenarios per month, all scenarios, progress tracking, and compare attempts.`,
    },
    {
      q: "I am an Indian nurse going to Australia or UK — is this right for me?",
      a: "Yes. SpeakOET is built specifically for Indian nurses preparing for OET to work abroad. Our scenarios reflect real nursing situations in Australian, British, and New Zealand hospitals.",
    },
    {
      q: "Do you have plans for coaching institutes and academies?",
      a: `Contact us at support@speakoet.com for academy and bulk pricing. Your students each get the full Elite plan — 80 scenarios a month, 9-criteria scoring, pronunciation feedback, and mock tests.`,
    },
    {
      q: "Is SpeakOET available in Hindi or Gujarati?",
      a: "The platform is in English — because OET is an English exam. However our scenarios are designed keeping Indian nurses in mind, with patients who use familiar Indian-context situations.",
    },
    {
      q: "What happens after my free sessions run out?",
      a: `You can upgrade to Pro for ₹${pro.price}/month for ${pro.sessions_limit} sessions a month. We'll remind you before your sessions run out — no surprise charges.`,
    },
  ]

  return (
    <section className="bg-white py-16 md:py-24">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="font-display text-3xl md:text-4xl font-semibold text-[#0F2356] text-center mb-12">Common Questions</h2>

        <div
          ref={ref}
          className="rounded-2xl overflow-hidden border border-gray-100 shadow-premium transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
          style={{
            opacity: inView ? 1 : 0,
            transform: inView ? "translateY(0)" : "translateY(12px)",
          }}
        >
          {faqs.map((faq, i) => {
            const isOpen = openIndex === i
            return (
              <div key={i} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                <button
                  className="w-full flex items-center justify-between gap-4 px-6 py-5 text-left hover:bg-gray-50 transition-colors"
                  onClick={() => setOpenIndex(isOpen ? null : i)}
                  aria-expanded={isOpen}
                >
                  <span className="text-[#0F2356] font-semibold text-sm md:text-base leading-snug">{faq.q}</span>
                  <ChevronDown
                    className={`w-5 h-5 text-gray-400 shrink-0 transition-transform duration-200 ${
                      isOpen ? "rotate-180" : ""
                    }`}
                    aria-hidden="true"
                  />
                </button>
                <div
                  className={`grid transition-[grid-template-rows] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] ${
                    isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
                  }`}
                >
                  <div className="overflow-hidden">
                    <p className="px-6 pb-5 text-gray-600 text-sm leading-relaxed">{faq.a}</p>
                  </div>
                </div>
                {i < faqs.length - 1 && <div className="border-b border-gray-100" />}
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
