'use client'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import api from '@/lib/api'
import HeroSection from '@/components/landing/HeroSection'
import StatsBar from '@/components/landing/StatsBar'
import FailureSection from '@/components/landing/FailureSection'
import HowItWorks from '@/components/landing/HowItWorks'
import FeaturesGrid from '@/components/landing/FeaturesGrid'
import ModulesSection from '@/components/landing/ModulesSection'
import PricingSection from '@/components/landing/PricingSection'
import ToolsSection from '@/components/landing/ToolsSection'
import InstituteSection from '@/components/landing/InstituteSection'
import DemoSection from '@/components/landing/DemoSection'
import FounderSection from '@/components/landing/FounderSection'
import FAQSection from '@/components/landing/FAQSection'

// Mirrors the questions/answers rendered by FAQSection -- Google's structured-data
// guidelines require this to match visible page content, so keep the two in sync
// if the FAQ copy changes. Prices are the real current values (not FAQSection's
// pre-fetch fallback text, which goes stale when pricing changes).
const faqJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: [
    {
      q: 'Is SpeakOET an official OET product?',
      a: 'No. SpeakOET is an independent AI practice tool for nurses. OET is a registered trademark of Cambridge Boxhill Language Assessment. We are not affiliated with or endorsed by OET — we built our scoring around the official public rubric.',
    },
    {
      q: 'How accurate is the AI scoring?',
      a: 'SpeakOET evaluates your responses using all 9 public OET Speaking assessment criteria. It is designed as a study tool and cannot guarantee any exam result — it is not a substitute for the real exam.',
    },
    {
      q: 'Do I need to download an app?',
      a: 'No. SpeakOET is completely web-based. Open it in Chrome or Safari on any device and start practicing immediately. No App Store, no installation.',
    },
    {
      q: 'What is included in the free plan?',
      a: 'The free plan gives you 3 speaking sessions per month with full 9-criteria feedback. No credit card required to start.',
    },
    {
      q: 'How much does Pro cost?',
      a: 'Pro is ₹799 per month, about US$10. That is significantly less than one hour with a human OET tutor. You get 40 speaking sessions per month plus Reading, Listening and Writing practice, progress tracking, and compare attempts.',
    },
    {
      q: 'I am an Indian nurse going to Australia or UK — is this right for me?',
      a: 'Yes. SpeakOET is built specifically for Indian nurses preparing for OET to work abroad. Our scenarios reflect real nursing situations in Australian, British, and New Zealand hospitals.',
    },
    {
      q: 'Do you have plans for coaching institutes and academies?',
      a: 'Contact us at support@speakoet.com for academy and bulk pricing. Your students each get the full Elite plan — 80 scenarios a month, 9-criteria scoring, pronunciation feedback, and mock tests.',
    },
    {
      q: 'Is SpeakOET available in Hindi or Gujarati?',
      a: 'The platform is in English — because OET is an English exam. However our scenarios are designed keeping Indian nurses in mind, with patients who use familiar Indian-context situations.',
    },
    {
      q: 'What happens after my free sessions run out?',
      a: 'You can upgrade to Pro for ₹799/month for 40 sessions a month. We will remind you before your sessions run out — no surprise charges.',
    },
  ].map(({ q, a }) => ({
    '@type': 'Question',
    name: q,
    acceptedAnswer: { '@type': 'Answer', text: a },
  })),
}

export default function Home() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [onboardingChecked, setOnboardingChecked] = useState(false)

  useEffect(() => {
    if (status === 'authenticated' && session?.user?.is_anonymous) {
      router.push('/tools/oet-mock-test-free')
      return
    }
    if (status === 'authenticated' && !session?.user?.is_anonymous && !onboardingChecked) {
      api.get('/onboarding/status').then((res) => {
        const complete = res.data?.onboarding_completed === true
        router.push(complete ? '/dashboard' : '/onboarding')
      }).catch(() => {
        router.push('/dashboard')
      }).finally(() => {
        setOnboardingChecked(true)
      })
    }
  }, [status, session, onboardingChecked, router])

  if (status === 'authenticated') {
    return null
  }

  return (
    <>
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
      />
      <HeroSection />
      <StatsBar />
      <FailureSection />
      <HowItWorks />
      <FeaturesGrid />
      <ModulesSection />
      <PricingSection />
      <ToolsSection />
      <DemoSection />
      <FounderSection />
      <InstituteSection />
      <FAQSection />
    </>
  )
}
