'use client'

import { useRouter } from 'next/navigation'
import { useSupabaseSession } from '@/lib/supabase'
import { useEffect, useState } from 'react'
import { CheckCircle2, Zap, Sparkles, Shield } from 'lucide-react'
import { RazorpayCheckout } from '@/components/RazorpayCheckout'
import { getPlans, type Plan } from '@/lib/api'
import { trackEvent } from '@/lib/analytics'

export default function UpgradePage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [paid, setPaid] = useState(false)
  const [plans, setPlans] = useState<Plan[] | null>(null)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
    }
  }, [status, router])

  useEffect(() => {
    getPlans().then(setPlans).catch(() => setPlans([]))
    trackEvent('upgrade_page_viewed')
  }, [])

  if (status === 'loading' || !plans) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-[#0F2356]">Upgrade Your Plan</h1>
          <p className="text-gray-500 mt-3 text-lg">
            Choose the plan that fits your OET preparation journey
          </p>
        </div>

        {paid && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-8 mb-10 text-center">
            <div className="text-4xl mb-3">&#10003;</div>
            <h2 className="text-2xl font-bold text-emerald-800 mb-2">Welcome to Pro!</h2>
            <p className="text-emerald-600 mb-4">
              Your payment was successful. You now have unlimited access.
            </p>
            <button
              onClick={() => router.push('/practice/speaking')}
              className="bg-emerald-600 text-white rounded-xl px-6 py-3 font-semibold hover:bg-emerald-700 transition"
            >
              Start Practicing
            </button>
          </div>
        )}

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {plans.map((plan) => (
            <div
              key={plan.id}
              className={`rounded-2xl bg-white shadow-sm border-2 flex flex-col ${
                plan.highlight ? 'border-[#0F2356] scale-105 shadow-lg' : 'border-gray-100'
              }`}
            >
              {plan.highlight && (
                <div className="bg-[#0F2356] text-white text-center text-xs font-semibold uppercase tracking-wider py-2 rounded-t-xl">
                  Most Popular
                </div>
              )}
              <div className="p-6 flex flex-col flex-1">
                <div className="flex items-center gap-2 mb-1">
                  {plan.id === 'free' && <Zap className="w-5 h-5 text-gray-400" />}
                  {plan.id === 'basic' && <Zap className="w-5 h-5 text-yellow-500" />}
                  {(plan.id === 'pro' || plan.id === 'elite') && <Sparkles className="w-5 h-5 text-[#0F2356]" />}
                  <h3 className="text-xl font-bold text-[#0F2356]">{plan.name}</h3>
                </div>
                <p className="text-sm text-gray-500 mb-4">{plan.description}</p>
                <div className="mb-3">
                  <span className="text-3xl font-black text-[#0F2356]">
                    {plan.price === 0 ? 'Free' : `\u20B9${plan.price}`}
                  </span>
                  {plan.price > 0 && (
                    <span className="text-gray-400 text-sm ml-1">/{plan.period}</span>
                  )}
                </div>
                {plan.badge && (
                  <div className="mb-4">
                    <span className="inline-block bg-emerald-100 text-emerald-700 text-xs font-bold px-2.5 py-1 rounded-full">
                      {plan.badge}
                    </span>
                  </div>
                )}

                <ul className="space-y-3 mb-8 flex-1">
                  {plan.features.map((f, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>

                {plan.disabled ? (
                  <button
                    disabled
                    className="w-full rounded-xl py-3 text-sm font-semibold bg-gray-100 text-gray-400 cursor-not-allowed"
                  >
                    {plan.cta}
                  </button>
                ) : (
                  <>
                    <RazorpayCheckout
                      amountPaise={plan.price * 100}
                      planId={plan.id}
                      planLabel={`${plan.name} Plan - \u20B9${plan.price}/${plan.period}`}
                      onSuccess={() => setPaid(true)}
                      buttonLabel={plan.cta}
                      className="bg-[#0F2356] text-white hover:bg-[#0F2356]/90"
                    />
                    <p className="text-xs text-gray-400 text-center mt-2">
                      Auto-renews monthly \u00B7 Cancel anytime in Settings
                    </p>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
