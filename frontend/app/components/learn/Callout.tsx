import type { ReactNode } from 'react'

const STYLES = {
  tip: { wrap: 'border-emerald-200 bg-emerald-50', label: 'text-emerald-700', icon: '✓' },
  warning: { wrap: 'border-amber-200 bg-amber-50', label: 'text-amber-700', icon: '⚠' },
  good: { wrap: 'border-emerald-200 bg-emerald-50', label: 'text-emerald-700', icon: '✓ Good' },
  bad: { wrap: 'border-red-200 bg-red-50', label: 'text-red-700', icon: '✗ Weak' },
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
      {title && <p className={`text-sm font-semibold ${s.label} mb-1.5`}>{s.icon} {title}</p>}
      {!title && <p className={`text-sm font-semibold ${s.label} mb-1.5`}>{s.icon}</p>}
      <div className="text-sm text-gray-700 leading-relaxed [&_p]:mb-2 [&_p:last-child]:mb-0">{children}</div>
    </div>
  )
}
