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
    <div className="relative hidden lg:flex lg:w-2/5 flex-col justify-between p-10 xl:p-14 overflow-hidden bg-[#0F2356]">
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

      <div className="relative z-10 flex flex-col gap-10">
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

      <div className="relative z-10">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm">
          <div className="mb-3 flex gap-0.5">
            {Array.from({ length: 5 }).map((_, i) => (
              <svg
                key={i}
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="h-4 w-4 text-emerald-400"
                aria-hidden="true"
              >
                <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
              </svg>
            ))}
          </div>
          <blockquote>
            <p className="text-sm leading-relaxed text-white/80">
              &ldquo;I passed OET after 3 weeks of practice&rdquo;
            </p>
          </blockquote>
          <div className="mt-3 flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500/30 text-xs font-semibold text-emerald-300">
              PM
            </div>
            <div>
              <p className="text-xs font-semibold text-white">Priya M.</p>
              <p className="text-xs text-white/50">Kerala → Australia</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
