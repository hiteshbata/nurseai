// Pure plan data -- no axios, no supabase. Kept separate from api.ts so
// server components (e.g. app/pricing, app/tools/oet-score-calculator) can
// import plan data without pulling in api.ts's supabase.ts -> useState/
// useEffect chain, which breaks the server/client component boundary.
export interface Plan {
  id: string
  name: string
  price: number
  period: string
  description: string
  features: string[]
  cta: string
  highlight: boolean
  disabled: boolean
  badge?: string
  profile_plan: string
  sessions_limit: number
}

// Mirrors backend/app/core/plans.py PLANS. Used as the offline/error fallback
// everywhere a landing component needs a price or session count before (or
// instead of) a resolved /plans/ call, so there's one place to update instead
// of five components independently drifting out of sync with the backend --
// which is exactly how a stale ₹999 Pro-price fallback once shipped.
export const FALLBACK_PLANS: Plan[] = [
  {
    id: 'free',
    name: 'Free Trial',
    price: 0,
    period: 'forever',
    description: 'Try the full 9-criteria examiner report',
    features: [
      '3 speaking scenarios per month',
      'Full 9-criteria OET scoring',
      'AI patient conversation',
      'Standard voice',
      'Last 3 attempts',
    ],
    cta: 'Current Plan',
    highlight: false,
    disabled: true,
    profile_plan: 'free',
    sessions_limit: 3,
  },
  {
    id: 'basic',
    name: 'Basic',
    price: 299,
    period: 'month',
    description: 'Speaking practice with the full examiner report',
    features: [
      '20 speaking scenarios per month',
      'Full 9-criteria OET scoring',
      'AI patient conversation',
      'Standard voice',
      'Last 10 attempts',
      'Per-session report',
      'Email support',
    ],
    cta: 'Subscribe Basic',
    highlight: false,
    disabled: false,
    profile_plan: 'basic',
    sessions_limit: 20,
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 799,
    period: 'month',
    description: 'Complete OET preparation and performance tracking',
    features: [
      '40 speaking scenarios per month',
      'Full 9-criteria OET scoring with richer, more detailed feedback',
      'Premium British patient voice',
      'Writing practice and scoring',
      'Unlimited attempt history',
      'Unlimited attempt comparison over time',
      'Priority email support',
    ],
    cta: 'Subscribe Pro',
    highlight: true,
    disabled: false,
    profile_plan: 'pro',
    sessions_limit: 40,
  },
  {
    id: 'elite',
    name: 'Elite',
    price: 1499,
    period: 'month',
    description: 'Maximum preparation',
    features: [
      '80 speaking scenarios per month',
      'Full 9-criteria OET scoring with richer, more detailed feedback',
      'Phoneme-level pronunciation scoring',
      'Premium British patient voice',
      'AI generated study plan',
      'Writing practice and scoring',
      'Unlimited attempt history',
      'Unlimited attempt comparison over time',
      'Advanced weak area detection',
      'WhatsApp priority support',
    ],
    cta: 'Subscribe Elite',
    highlight: false,
    disabled: false,
    profile_plan: 'elite',
    sessions_limit: 80,
  },
]
