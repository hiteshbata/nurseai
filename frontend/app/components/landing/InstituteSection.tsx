'use client'

import { useEffect, useState } from 'react'
import { CheckCircle2 } from "lucide-react"
import { getPlans, type Plan } from "@/lib/api"

export default function InstituteSection() {
  const [elitePrice, setElitePrice] = useState('₹1,499')

  useEffect(() => {
    getPlans().then((plans: Plan[]) => {
      const elite = plans.find((p: Plan) => p.id === 'elite')
      if (elite) setElitePrice(`₹${elite.price}`)
    }).catch(() => {})
  }, [])

  const bullets = [
    "Students practice daily on any device, between classes",
    "Full 9-criteria OET scoring on every session",
    "80 speaking scenarios a month on the Elite plan",
    "Phoneme-level pronunciation scoring and mock test mode",
    "Bulk pricing for academies — get in touch",
  ]

  const eliteFeatures = [
    `${elitePrice} per month`,
    "80 speaking scenarios per month",
    "Phoneme-level pronunciation scoring",
    "Mock test mode",
    "AI generated study plan",
    "Writing practice and scoring",
    "Advanced weak area detection",
  ]

  return (
    <section className="bg-[#0F2356] py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col lg:flex-row gap-12 lg:gap-16 items-center">
          <div className="flex-1">
            <span className="inline-block bg-white/20 text-white text-xs font-semibold px-4 py-1.5 rounded-full mb-5">
              For OET Coaching Academies
            </span>
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4 text-balance">
              Running an OET Coaching Institute?
            </h2>
            <p className="text-white/70 text-lg leading-relaxed mb-8">
              Give your students unlimited daily AI speaking practice they can do on any device, between classes.
              Bulk pricing available for academies preparing nurses for OET.
            </p>
            <ul className="flex flex-col gap-3 mb-8">
              {bullets.map((b) => (
                <li key={b} className="flex items-start gap-3 text-white">
                  <CheckCircle2 className="w-5 h-5 text-[#10B981] shrink-0 mt-0.5" />
                  <span className="text-sm leading-relaxed">{b}</span>
                </li>
              ))}
            </ul>
            <a
              href="mailto:support@speakoet.com"
              className="inline-flex items-center bg-white text-[#0F2356] font-semibold px-6 py-3 rounded-lg hover:bg-gray-100 transition-colors"
            >
              Contact Us for Elite Pricing →
            </a>
          </div>

          <div className="w-full lg:w-[420px] shrink-0">
            <div className="bg-white rounded-2xl p-8 shadow-2xl">
              <h3 className="text-2xl font-bold text-[#0F2356] mb-1">Elite Plan</h3>
              <p className="text-gray-500 text-sm mb-6">For academies — maximum preparation</p>

              <ul className="flex flex-col gap-3 mb-6">
                {eliteFeatures.map((f) => (
                  <li key={f} className="flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-[#10B981] shrink-0" />
                    <span className="text-gray-700 text-sm font-medium">{f}</span>
                  </li>
                ))}
              </ul>

              <a
                href="mailto:support@speakoet.com"
                className="block w-full text-center bg-[#047857] text-white font-semibold px-6 py-3 rounded-lg hover:bg-[#036546] transition-colors mb-4"
              >
                Get Elite Pricing
              </a>

              <p className="text-gray-500 text-xs text-center">
                Web-based, so your students can practise anywhere in India. Get in touch for bulk academy pricing.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
