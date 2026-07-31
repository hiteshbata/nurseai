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
    description: "Try SpeakOET's AI examiner, free",
    features: [
      '3 speaking sessions / month',
      'Full 9-criteria AI scoring',
      'AI patient conversation',
      'Standard British voice',
      'Last 3 attempts + progress tracking',
    ],
    cta: 'Start Free',
    highlight: false,
    disabled: false,
    profile_plan: 'free',
    sessions_limit: 3,
  },
  {
    id: 'basic',
    name: 'Basic',
    price: 299,
    period: 'month',
    description: 'Build confidence with Speaking, Reading & Listening',
    features: [
      '20 speaking sessions / month',
      'Reading & Listening practice',
      'Full 9-criteria AI scoring',
      'AI patient conversation',
      'Standard British voice',
      'Last 10 attempts + progress tracking',
      'Email support',
    ],
    cta: 'Start Practicing',
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
    description: 'Complete OET preparation, including Writing',
    features: [
      '40 speaking sessions / month',
      'Reading, Listening & Writing practice',
      'Advanced AI feedback & premium conversation',
      'Natural British voice',
      'Handwriting OCR for Writing',
      'Unlimited attempt history',
      'Priority email support',
    ],
    cta: 'Get Pro',
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
    description: 'Everything you need for exam-day success',
    features: [
      '80 speaking sessions / month',
      'Full Mock Tests (all 4 parts)',
      'Reading, Listening & Writing practice',
      'Pronunciation analysis + AI study plan',
      'Advanced AI feedback & premium conversation',
      'Natural British voice + Handwriting OCR',
      'Unlimited attempt history',
      'WhatsApp priority support',
    ],
    cta: 'Become Exam Ready',
    highlight: false,
    disabled: false,
    profile_plan: 'elite',
    sessions_limit: 80,
  },
]
