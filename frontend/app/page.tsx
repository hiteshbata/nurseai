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
import PricingSection from '@/components/landing/PricingSection'
import InstituteSection from '@/components/landing/InstituteSection'
import TestimonialsSection from '@/components/landing/TestimonialsSection'
import FAQSection from '@/components/landing/FAQSection'
import CTASection from '@/components/landing/CTASection'

export default function Home() {
  const { session, status } = useSupabaseSession()
  const router = useRouter()
  const [onboardingChecked, setOnboardingChecked] = useState(false)

  useEffect(() => {
    if (status === 'authenticated' && !onboardingChecked) {
      api.get('/onboarding/status').then((res) => {
        const complete = res.data?.onboarding_completed === true
        router.push(complete ? '/dashboard' : '/onboarding')
      }).catch(() => {
        router.push('/dashboard')
      }).finally(() => {
        setOnboardingChecked(true)
      })
    }
  }, [status, onboardingChecked, router])

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F8FAFC]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#0F2356]" />
      </div>
    )
  }

  if (status === 'authenticated') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F8FAFC]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#0F2356]" />
      </div>
    )
  }

  return (
    <>
      <HeroSection />
      <StatsBar />
      <FailureSection />
      <HowItWorks />
      <FeaturesGrid />
      <PricingSection />
      <InstituteSection />
      <TestimonialsSection />
      <FAQSection />
      <CTASection />
    </>
  )
}
