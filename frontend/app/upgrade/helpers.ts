// Pure helpers for app/upgrade/page.tsx -- deciding what each plan card
// should say/do, and what an institution member's access panel should show.
// Split out (same pattern as admin/institutions/[id]/helpers.ts) so this
// logic is testable without a DOM. page.tsx is the only caller.
import type { EffectiveAccess, PlanEntitlement } from '@/lib/plans'

export type CardAction = 'current' | 'included' | 'upgrade'

// Decides a plan card's action from the server-computed entitlement alone --
// never from plan.id === 'free' or any other client-side guess. Missing
// entitlement (summary not loaded yet, or a plan id the summary doesn't
// know about) fails closed to 'included': never renders a checkout button
// without the backend having said it's purchasable.
export function getCardAction(entitlement: PlanEntitlement | undefined): CardAction {
  if (!entitlement) return 'included'
  if (entitlement.is_current) return 'current'
  if (!entitlement.is_purchasable) return 'included'
  return 'upgrade'
}

export function getCardLabel(action: CardAction, cta: string): string {
  if (action === 'current') return 'Current Plan'
  if (action === 'included') return 'Included'
  return cta
}

export function isCheckoutAllowed(action: CardAction): boolean {
  return action === 'upgrade'
}

// Module rows for an institution student's plain access summary (see
// app/upgrade/page.tsx) -- keys match summary.institution.enabled_modules,
// never effective_access (which also reflects self-serve plan access).
export const INSTITUTION_MODULE_ROWS: { key: keyof EffectiveAccess; label: string }[] = [
  { key: 'speaking', label: 'Speaking' },
  { key: 'reading', label: 'Reading' },
  { key: 'listening', label: 'Listening' },
  { key: 'writing', label: 'Writing' },
  { key: 'mock', label: 'Mock Test' },
]
