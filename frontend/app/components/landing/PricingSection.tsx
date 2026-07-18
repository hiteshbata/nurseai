'use client'

import { useEffect, useState } from 'react'
import { getPlans, FALLBACK_PLANS, type Plan } from '@/lib/api'

export default function PricingSection() {
  // Seeded with the known-current fallback rather than null -- so a slow or
  // failed /plans/ call shows real, correct pricing immediately instead of a
  // "Loading pricing..." placeholder that used to hang forever on failure.
  const [plans, setPlans] = useState<Plan[]>(FALLBACK_PLANS)

  useEffect(() => {
    getPlans().then(setPlans).catch(() => {})
  }, [])

  const free = plans.find((p) => p.id === 'free')
  const basic = plans.find((p) => p.id === 'basic')
  const pro = plans.find((p) => p.id === 'pro')
  const elite = plans.find((p) => p.id === 'elite')

  return (
    <section id="pricing" className="bg-[#F8FAFC] py-16 md:py-24">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-[#0F2356] mb-3 text-balance">
            Simple, Transparent Pricing
          </h2>
          <p className="text-gray-500 text-lg">Start free. Upgrade when you are ready.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[free, basic, pro, elite].filter(Boolean).map((plan) => (
            <div
              key={plan!.id}
              className={`rounded-2xl flex flex-col ${
                plan!.highlight
                  ? 'bg-white border-2 border-[#10B981] shadow-md'
                  : plan!.id === 'free'
                  ? 'bg-[#F8FAFC] border border-gray-200 shadow-sm'
                  : 'bg-white border border-gray-200 shadow-sm'
              }`}
            >
              {plan!.highlight && (
                <div className="bg-[#047857] text-white text-center text-xs font-bold px-4 py-1.5 rounded-t-xl">
                  Most Popular
                </div>
              )}
              <div className="p-6 flex flex-col flex-1">
                {plan!.badge && !plan!.highlight && (
                  <div className="mb-2">
                    <span className="inline-block bg-emerald-100 text-emerald-700 text-xs font-bold px-2.5 py-1 rounded-full">
                      {plan!.badge}
                    </span>
                  </div>
                )}
                <h3 className={`text-lg font-bold mb-1 ${
                  plan!.id === 'free' ? 'text-gray-500' : 'text-[#0F2356]'
                }`}>
                  {plan!.name}
                </h3>
                <p className="text-gray-500 text-sm mb-6">{plan!.description}</p>

                <div className="mb-4">
                  <span className={`text-4xl font-bold ${
                    plan!.id === 'free' ? 'text-gray-500' : 'text-[#0F2356]'
                  }`}>
                    {plan!.price === 0 ? '₹0' : `₹${plan!.price}`}
                  </span>
                  {plan!.price > 0 && (
                    <span className="text-gray-500 text-sm ml-1">/{plan!.period}</span>
                  )}
                </div>

                <ul className="flex flex-col gap-3 mb-8 flex-1">
                  {plan!.features.map((f: string) => (
                    <li key={f} className="flex items-start gap-3">
                      <span className="w-5 h-5 rounded-full bg-emerald-50 flex items-center justify-center shrink-0 mt-0.5">
                        <span className="text-[#047857] text-xs font-bold">✓</span>
                      </span>
                      <span className={`text-sm ${
                        plan!.id === 'free' ? 'text-gray-500' : 'text-gray-600'
                      }`}>{f}</span>
                    </li>
                  ))}
                </ul>

                {plan!.disabled ? (
                  <button
                    disabled
                    className="block w-full text-center bg-white text-gray-500 font-semibold px-6 py-3 rounded-lg border-2 border-gray-200 cursor-not-allowed"
                  >
                    {plan!.cta}
                  </button>
                ) : (
                  <a
                    href="/auth/register"
                    className={`block w-full text-center font-semibold px-6 py-3 rounded-lg transition-colors ${
                      plan!.highlight
                        ? 'bg-[#047857] text-white hover:bg-[#036546]'
                        : 'bg-[#0F2356] text-white hover:bg-[#0F2356]/90'
                    }`}
                  >
                    {plan!.cta}
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>

        <p className="text-sm text-gray-500 text-center mt-6">
          No contracts. Cancel anytime. Upgrade or downgrade instantly.
        </p>
      </div>
    </section>
  )
}
