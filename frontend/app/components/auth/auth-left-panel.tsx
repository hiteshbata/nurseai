'use client'

import { Check } from 'lucide-react'
import SpeakOETLogo from '@/components/ui/SpeakOETLogo'

const features = [
  'AI-powered roleplay scenarios',
  'Scored on 9 OET criteria',
  'Track your band score progress',
]

export function AuthLeftPanel() {
  return (
    <div className="relative hidden lg:flex lg:w-2/5 flex-col p-10 xl:p-14 overflow-hidden bg-[#0F2356]">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, white 1px, transparent 0)',
          backgroundSize: '32px 32px',
        }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-32 -right-32 h-96 w-96 rounded-full bg-emerald-500/10 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-32 -left-32 h-96 w-96 rounded-full bg-blue-400/10 blur-3xl"
      />

      <div className="relative z-10">
        <SpeakOETLogo height={32} variant="full" theme="light" priority />
      </div>

      <div className="relative z-10 flex flex-1 flex-col justify-center gap-10">
        <div>
          <h1 className="text-3xl xl:text-4xl font-bold leading-tight text-white text-balance">
            Practice OET Speaking{' '}
            <span className="text-emerald-400">with confidence</span>
          </h1>
        </div>

        <ul className="flex flex-col gap-4" aria-label="Key features">
          {features.map((feature) => (
            <li key={feature} className="flex items-center gap-3">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 ring-1 ring-emerald-500/40">
                <Check className="h-3.5 w-3.5 text-emerald-400" aria-hidden="true" />
              </div>
              <span className="text-sm font-medium text-white/85">{feature}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
