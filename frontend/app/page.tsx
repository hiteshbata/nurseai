'use client'
import { useSupabaseSession } from '@/lib/supabase'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import api from '@/lib/api'

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
  return (
    <div className="w-full">
      <section className="bg-gradient-to-br from-blue-600 via-blue-500 to-blue-700 text-white py-20 px-4">
        <div className="max-w-6xl mx-auto text-center">
          <h1 className="text-5xl md:text-6xl font-bold mb-6">SpeakOET - Your OET Coach</h1>
          <p className="text-xl opacity-90">AI-powered English coaching for OET</p>
          <div className="flex gap-4 justify-center flex-wrap">
            {status === 'authenticated' ? (
              <button onClick={() => router.push('/dashboard')} className="px-8 py-3 bg-white text-blue-600 rounded-lg">Dashboard</button>
            ) : (
              <>
                <Link href="/auth/register" className="px-8 py-3 bg-white text-blue-600 rounded-lg">Get Started</Link>
                <Link href="/auth/login" className="px-8 py-3 bg-blue-400 text-white rounded-lg">Sign In</Link>
              </>
            )}
          </div>
        </div>
      </section>
      <section className="py-16 px-4 bg-white text-center">
        <h2 className="text-4xl font-bold mb-8">Ready to Ace Your OET?</h2>
        {status !== 'authenticated' && (
          <Link href="/auth/register" className="inline-block px-8 py-3 bg-white text-blue-600 rounded-lg">Create Free Account</Link>
        )}
      </section>
    </div>
  )
}