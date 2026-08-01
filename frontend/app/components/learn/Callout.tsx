import type { ReactNode } from 'react'
import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react'

const STYLES = {
  tip: { wrap: 'border-emerald-200 bg-emerald-50', label: 'text-emerald-700', Icon: CheckCircle2, text: null },
  warning: { wrap: 'border-amber-200 bg-amber-50', label: 'text-amber-700', Icon: AlertTriangle, text: null },
  good: { wrap: 'border-emerald-200 bg-emerald-50', label: 'text-emerald-700', Icon: CheckCircle2, text: 'Good' },
  bad: { wrap: 'border-red-200 bg-red-50', label: 'text-red-700', Icon: XCircle, text: 'Weak' },
} as const

export function Callout({
  variant,
  title,
  children,
}: {
  variant: keyof typeof STYLES
  title?: string
  children: ReactNode
}) {
  const s = STYLES[variant]
  return (
    <div className={`rounded-xl border ${s.wrap} px-5 py-4 mb-4`}>
      <p className={`flex items-center gap-1.5 text-sm font-semibold ${s.label} mb-1.5`}>
        <s.Icon className="w-4 h-4 shrink-0" strokeWidth={2} aria-hidden="true" />
        {[s.text, title].filter(Boolean).join(' ')}
      </p>
      <div className="text-sm text-gray-700 leading-relaxed [&_p]:mb-2 [&_p:last-child]:mb-0">{children}</div>
    </div>
  )
}
