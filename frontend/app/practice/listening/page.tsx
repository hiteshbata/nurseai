'use client'

import { useState, useEffect } from 'react'
import { useSupabaseSession } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

interface TestSummary {
  id: number
  title: string
  section_count: number
}

export default function ListeningPracticePage() {
  const { status } = useSupabaseSession()
  const router = useRouter()
  const [tests, setTests] = useState<TestSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/auth/login')
      return
    }
    if (status === 'authenticated') {
      api.get('/listening/tests')
        .then((res) => setTests(res.data || []))
        .catch(() => toast.error('Failed to load listening tests'))
        .finally(() => setIsLoading(false))
    }
  }, [status])

  if (status === 'loading' || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl text-gray-600">Loading listening practice...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-bold text-[#0F2356]">Listening Practice</h1>
            <p className="text-gray-500 mt-1">A full OET Listening paper — Part A, B and C in one session</p>
          </div>
          <Link href="/practice/listening/mistakes" className="text-sm font-semibold text-primary hover:underline">
            Review your mistakes →
          </Link>
        </div>

        {tests.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-lg shadow mt-8">
            <p className="text-xl text-gray-500 mb-2">No listening tests available yet</p>
            <p className="text-muted-foreground">Check back soon — new tests are added regularly.</p>
          </div>
        ) : (
          <div className="mt-8">
            <h2 className="text-lg font-bold text-[#0F2356] mb-1">Full Listening Tests</h2>
            <p className="text-sm text-gray-500 mb-4">42 questions across Part A, B and C — just like the real exam. Each extract plays once.</p>
            <div className="grid md:grid-cols-2 gap-6">
              {tests.map((t) => (
                <Card key={t.id} className="p-6 flex flex-col gap-3 hover:shadow-md transition-all border-primary/20">
                  <span className="px-3 py-1 rounded-full text-xs font-semibold w-fit bg-primary/10 text-primary">Full test</span>
                  <h3 className="text-xl font-bold text-primary">{t.title}</h3>
                  <p className="text-sm text-gray-500">Parts A + B + C · ~45 min</p>
                  <Button onClick={() => router.push(`/practice/listening/test/${t.id}`)} className="w-full mt-auto">
                    Start Full Test →
                  </Button>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
