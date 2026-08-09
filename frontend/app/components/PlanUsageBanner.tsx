'use client'

import { Progress } from '@/components/ui/progress'
import { useSessionUsage } from '@/components/AppShell'

const PLAN_LABELS: Record<string, string> = {
  free: 'Free',
  basic: 'Basic',
  pro: 'Pro',
  elite: 'Elite',
}

// Upgrade CTAs live in the single contextual upsell banner elsewhere on the Results
// page (see `activeUpsell` in practice/speaking/page.tsx) — this banner is usage
// info only, so the page never stacks more than one upgrade prompt.
//
// Usage data comes from AppShell (this always renders nested inside it, via
// SpeakingSession -> practice/speaking/page.tsx) instead of fetching
// /sessions/usage itself -- that was a confirmed duplicate request whenever
// this banner mounted.
export default function PlanUsageBanner() {
  const { usage } = useSessionUsage()

  if (!usage) return null

  const planLabel = PLAN_LABELS[usage.plan] ?? usage.plan
  const pct = usage.sessions_limit > 0 ? (usage.sessions_used / usage.sessions_limit) * 100 : 0
  const isAtLimit = usage.sessions_remaining <= 0

  return (
    <div
      className={`rounded-2xl border p-5 mb-6 ${
        isAtLimit ? 'bg-amber-50 border-amber-200' : 'bg-white border-gray-100 shadow-sm'
      }`}
    >
      <p className={`text-sm font-bold ${isAtLimit ? 'text-amber-700' : 'text-[#0F2356]'}`}>
        {isAtLimit && <span className="mr-1">⚠</span>}
        {planLabel} Plan
      </p>
      <p className="text-xs text-gray-500 mt-0.5">
        {usage.sessions_used} / {usage.sessions_limit} sessions used this month
        {' · '}
        {usage.sessions_remaining} remaining
      </p>

      <div className="mt-2.5 flex items-center gap-3 max-w-[220px]">
        <Progress
          value={Math.min(pct, 100)}
          label="Sessions used this period"
          className={`h-1.5 ${isAtLimit ? '[&>div]:bg-amber-500' : '[&>div]:bg-[#10B981]'}`}
        />
      </div>

      {isAtLimit && (
        <p className="text-xs text-amber-700 mt-2">
          You&apos;ve used all your {planLabel.toLowerCase()} sessions this month.
        </p>
      )}
    </div>
  )
}
