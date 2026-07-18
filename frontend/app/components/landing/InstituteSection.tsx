'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { CheckCircle2 } from "lucide-react"
import api, { getPlans, FALLBACK_PLANS, type Plan } from "@/lib/api"

const fallbackElite = FALLBACK_PLANS.find((p) => p.id === 'elite')!

type FormStatus = 'idle' | 'submitting' | 'done' | 'error'

function InstituteLeadForm() {
  const [status, setStatus] = useState<FormStatus>('idle')

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    const data = new FormData(form)
    setStatus('submitting')
    try {
      await api.post('/leads/institute', {
        institute_name: data.get('institute_name'),
        contact_name: data.get('contact_name'),
        email: data.get('email'),
        phone: data.get('phone') || undefined,
        message: data.get('message') || undefined,
      })
      setStatus('done')
      form.reset()
    } catch {
      setStatus('error')
    }
  }

  if (status === 'done') {
    return (
      <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-5 text-center">
        <p className="text-sm font-semibold text-[#0F2356]">Thanks — we'll be in touch shortly.</p>
      </div>
    )
  }

  const inputClass =
    "w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-[#10B981] focus:border-transparent"

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <input name="institute_name" required placeholder="Institute name" className={inputClass} />
      <input name="contact_name" required placeholder="Your name" className={inputClass} />
      <input name="email" type="email" required placeholder="Email address" className={inputClass} />
      <input name="phone" placeholder="Phone (optional)" className={inputClass} />
      <textarea name="message" placeholder="Number of students, timeline, questions... (optional)" rows={2} className={inputClass} />
      {status === 'error' && (
        <p className="text-xs text-red-600">Something went wrong — please try again, or email support@speakoet.com.</p>
      )}
      <button
        type="submit"
        disabled={status === 'submitting'}
        className="w-full text-center bg-[#047857] text-white font-semibold px-6 py-3 rounded-lg hover:bg-[#036546] transition-colors disabled:opacity-60"
      >
        {status === 'submitting' ? 'Sending…' : 'Get Elite Pricing'}
      </button>
    </form>
  )
}

export default function InstituteSection() {
  // Sourced from the real elite plan (fetched, or the fallback until it
  // resolves) instead of a hand-typed feature list -- a separate literal list
  // here is exactly how a feature claim quietly drifts from what Elite
  // actually includes.
  const [elite, setElite] = useState<Plan>(fallbackElite)

  useEffect(() => {
    getPlans().then((plans: Plan[]) => {
      const found = plans.find((p: Plan) => p.id === 'elite')
      if (found) setElite(found)
    }).catch(() => {})
  }, [])

  const bullets = [
    "Students practice daily on any device, between classes",
    "Full 9-criteria OET scoring on every session",
    "80 speaking scenarios a month on the Elite plan",
    "Phoneme-level pronunciation scoring and mock test mode",
    "Bulk pricing for academies — get in touch",
  ]

  const eliteFeatures = [`₹${elite.price} per month`, ...elite.features]

  return (
    // A contained callout on the plain page background rather than another
    // full-bleed color band -- sitting between two full-bleed sections
    // (Founder navy above, FAQ white below), a same-toned band here reads as
    // a continuation of whichever neighbor it's closest to instead of its
    // own section. A bordered panel separates on shape, not on shade.
    <section className="bg-white py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="rounded-3xl border border-gray-200 shadow-xl bg-[#F8FAFC] p-8 md:p-14 overflow-hidden relative">
          <div className="absolute top-0 inset-x-0 h-1.5 bg-[#047857]" />
          <div className="flex flex-col lg:flex-row gap-12 lg:gap-16 items-center">
          <div className="flex-1">
            <span className="inline-block bg-[#0F2356]/10 text-[#0F2356] text-xs font-semibold px-4 py-1.5 rounded-full mb-5">
              For OET Coaching Academies
            </span>
            <h2 className="text-3xl md:text-4xl font-bold text-[#0F2356] mb-4 text-balance">
              Running an OET Coaching Institute?
            </h2>
            <p className="text-gray-500 text-lg leading-relaxed mb-8">
              Give your students unlimited daily AI speaking practice they can do on any device, between classes.
              Bulk pricing available for academies preparing nurses for OET.
            </p>
            <ul className="flex flex-col gap-3 mb-8">
              {bullets.map((b) => (
                <li key={b} className="flex items-start gap-3 text-[#0F2356]">
                  <CheckCircle2 className="w-5 h-5 text-[#10B981] shrink-0 mt-0.5" aria-hidden="true" />
                  <span className="text-sm leading-relaxed">{b}</span>
                </li>
              ))}
            </ul>
            <a
              href="#institute-lead-form"
              className="inline-flex items-center bg-[#0F2356] text-white font-semibold px-6 py-3 rounded-lg hover:bg-[#0F2356]/90 transition-colors"
            >
              Contact Us for Elite Pricing →
            </a>
          </div>

          <div className="w-full lg:w-[420px] shrink-0" id="institute-lead-form">
            <div className="bg-white rounded-2xl p-8 shadow-xl border border-gray-100">
              <h3 className="text-2xl font-bold text-[#0F2356] mb-1">Elite Plan</h3>
              <p className="text-gray-500 text-sm mb-6">For academies — maximum preparation</p>

              <ul className="flex flex-col gap-3 mb-6">
                {eliteFeatures.map((f) => (
                  <li key={f} className="flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-[#10B981] shrink-0" aria-hidden="true" />
                    <span className="text-gray-700 text-sm font-medium">{f}</span>
                  </li>
                ))}
              </ul>

              <InstituteLeadForm />

              <p className="text-gray-500 text-xs text-center mt-4">
                Web-based, so your students can practise anywhere in India. Get in touch for bulk academy pricing.
              </p>
            </div>
          </div>
          </div>
        </div>
      </div>
    </section>
  )
}
